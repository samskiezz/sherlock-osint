use anyhow::Result;
use erps_core::{
    cluster::{self, Constraint, Pair},
    similarity,
};
use erps_store::{self as store, Entity, Policy, Tx};
use serde_json::json;
use std::collections::{BTreeMap, BTreeSet};
use uuid::Uuid;
pub async fn rebuild(
    tx: &mut Tx<'_>,
    p: &Policy,
    use_lsh: bool,
    batch_threshold: usize,
) -> Result<(Vec<Entity>, usize, &'static str)> {
    let ms = store::mentions(tx, p.workspace).await?;
    let mut constraints = store::constraints(tx, p.workspace).await?;
    let input = ms.clone();
    let candidates =
        tokio::task::spawn_blocking(move || store::index::candidates(&input, use_lsh)).await??;
    // Exact strong identifiers are must-links, including blocks dropped for skew.
    let mut strong = BTreeMap::<(String, String, String), Vec<usize>>::new();
    for (i, m) in ms.iter().enumerate() {
        for (k, v) in &m.attributes {
            strong
                .entry((format!("{:?}", m.kind), k.clone(), v.clone()))
                .or_default()
                .push(i);
        }
    }
    for group in strong.values() {
        for &i in group.iter().skip(1) {
            constraints.push(Constraint {
                a: ms[group[0]].id,
                b: ms[i].id,
                must_link: true,
            });
        }
    }
    let mut engine = "rayon";
    let mut pairs: Vec<Pair> = if candidates.len() >= batch_threshold {
        match erps_core::udf::batch_score(&ms, &candidates).await {
            Ok(v) => {
                engine = "datafusion";
                v
            }
            Err(e) => {
                tracing::warn!(error=%e,"batch scoring failed; using scalar scorer");
                vec![]
            }
        }
    } else {
        vec![]
    };
    if pairs.is_empty() && !candidates.is_empty() {
        let input = ms.clone();
        let cs = candidates.clone();
        pairs = tokio::task::spawn_blocking(move || {
            use erps_core::similarity::score;
            use rayon::prelude::*;
            cs.par_iter()
                .map(|&(a, b)| Pair {
                    a,
                    b,
                    score: score(&input[a], &input[b]),
                })
                .collect()
        })
        .await?;
    }
    let clusters = cluster::pivot_cluster(&ms, &pairs, &constraints, 42)?;
    let mut entities = vec![];
    let mut membership = BTreeMap::new();
    for c in clusters {
        let mention_ids: Vec<_> = c.iter().map(|&i| ms[i].id).collect();
        let key = mention_ids
            .iter()
            .map(Uuid::to_string)
            .collect::<Vec<_>>()
            .join(",");
        let id = Uuid::new_v5(&p.workspace, key.as_bytes());
        for &i in &c {
            membership.insert(i, id);
        }
        entities.push(Entity {
            id,
            canonical_name: cluster::canonical(&ms, &c),
            kind: format!("{:?}", ms[c[0]].kind),
            mention_ids,
            aliases: c
                .iter()
                .map(|&i| ms[i].surface.clone())
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect(),
            provenance: cluster::annotation(&ms, &c)?,
            mentions: c.iter().map(|&i| ms[i].clone()).collect(),
            attributes: {
                let mut fields = BTreeMap::<String, Vec<store::AttributeValue>>::new();
                for &i in &c {
                    for (k, v) in &ms[i].attributes {
                        fields
                            .entry(k.clone())
                            .or_default()
                            .push(store::AttributeValue {
                                value: v.clone(),
                                valid_from: ms[i].valid_from,
                                valid_to: ms[i].valid_to,
                                mention_id: ms[i].id,
                            });
                    }
                }
                fields
            },
        });
    }
    store::save_entities(tx, p.workspace, &entities).await?;
    sqlx::query("DELETE FROM erps.pair_decisions WHERE workspace=$1")
        .bind(p.workspace)
        .execute(&mut **tx)
        .await?;
    for chunk in pairs.chunks(1000) {
        let prepared: Vec<_> = chunk
            .iter()
            .map(|pair| {
                Ok((
                    pair,
                    ms[pair.a].annotation().multiply(&ms[pair.b].annotation())?,
                ))
            })
            .collect::<Result<_>>()?;
        let mut insert=sqlx::QueryBuilder::<sqlx::Postgres>::new("INSERT INTO erps.pair_decisions(workspace,a,b,entity_a,entity_b,score,decision,provenance) ");
        insert.push_values(prepared, |mut row, (pair, prov)| {
            row.push_bind(p.workspace)
                .push_bind(ms[pair.a].id)
                .push_bind(ms[pair.b].id)
                .push_bind(membership[&pair.a])
                .push_bind(membership[&pair.b])
                .push_bind(pair.score)
                .push_bind(format!("{:?}", similarity::decide(pair.score)))
                .push_bind(json!(prov));
        });
        insert.build().execute(&mut **tx).await?;
    }
    Ok((entities, pairs.len(), engine))
}
