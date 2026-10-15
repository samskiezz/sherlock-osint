use anyhow::{ensure, Result};
use erps_core::{blocking, Mention};
use std::collections::{BTreeMap, BTreeSet};
use tantivy::{collector::DocSetCollector, doc, query::TermQuery, schema::*, Index, Term};
pub const MAX_CANDIDATES: usize = 500_000;
/// An authoritative snapshot is committed and reloaded *before* queries. This
/// disposable index cannot outlive its database snapshot or become stale.
pub fn candidates(mentions: &[Mention], use_lsh: bool) -> Result<Vec<(usize, usize)>> {
    let mut builder = Schema::builder();
    let id = builder.add_u64_field("id", STORED);
    let key = builder.add_text_field("blocking_keys", STRING);
    let schema = builder.build();
    let index = Index::create_in_ram(schema);
    let all_keys: Vec<_> = mentions.iter().map(blocking::keys).collect();
    let mut freq = BTreeMap::<&String, usize>::new();
    for keys in &all_keys {
        for k in keys {
            *freq.entry(k).or_default() += 1;
        }
    }
    let mut writer = index.writer(50_000_000)?;
    for (i, keys) in all_keys.iter().enumerate() {
        let mut d = doc!(id=>i as u64);
        for k in keys {
            if freq[k] <= 256 || k.contains(":id:") {
                d.add_text(key, k);
            }
        }
        writer.add_document(d)?;
    }
    writer.commit()?;
    let reader = index.reader()?;
    reader.reload()?;
    let searcher = reader.searcher();
    let mut pairs = BTreeSet::new();
    let mut document_ids = std::collections::HashMap::new();
    for (k, frequency) in &freq {
        if *frequency > 256 && !k.contains(":id:") {
            continue;
        }
        let q = TermQuery::new(Term::from_field_text(key, k), IndexRecordOption::Basic);
        let mut ids = Vec::new();
        for addr in searcher.search(&q, &DocSetCollector)? {
            let mention_id = if let Some(&i) = document_ids.get(&addr) {
                i
            } else {
                let d: TantivyDocument = searcher.doc(addr)?;
                let i = d
                    .get_first(id)
                    .and_then(|v| v.as_u64())
                    .ok_or_else(|| anyhow::anyhow!("index document has no ID"))?
                    as usize;
                document_ids.insert(addr, i);
                i
            };
            ids.push(mention_id);
        }
        ids.sort_unstable();
        for (position, &a) in ids.iter().enumerate() {
            for &b in &ids[position + 1..] {
                pairs.insert((a, b));
                ensure!(
                    pairs.len() <= MAX_CANDIDATES,
                    "candidate limit exceeded; use a smaller workspace or narrower blocking"
                );
            }
        }
    }
    if use_lsh {
        let mut bands = BTreeMap::new();
        for (i, m) in mentions.iter().enumerate() {
            for (band, signature) in blocking::minhash_bands(&m.surface, 32, 4) {
                bands
                    .entry((format!("{:?}", m.kind), band, signature))
                    .or_insert_with(Vec::new)
                    .push(i);
            }
        }
        for ids in bands.values() {
            if ids.len() > 256 {
                continue;
            }
            for (p, &a) in ids.iter().enumerate() {
                for &b in &ids[p + 1..] {
                    pairs.insert((a, b));
                    ensure!(pairs.len() <= MAX_CANDIDATES, "candidate limit exceeded");
                }
            }
        }
    }
    Ok(pairs.into_iter().collect())
}
