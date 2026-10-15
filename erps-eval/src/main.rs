use anyhow::{ensure, Result};
use erps_core::{cluster, mention::OffsetSpace, similarity, Mention, MentionKind};
use std::{collections::BTreeMap, time::Instant};
use uuid::Uuid;
fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|s| s == "--help") {
        println!("eval --entities 100 --mentions-per 3 --noise 0.1 --seed 42 --repeats 3 --output report.json");
        return Ok(());
    }
    ensure!(
        args.len().is_multiple_of(2),
        "arguments must be --name value pairs"
    );
    let options: BTreeMap<_, _> = args
        .chunks(2)
        .map(|a| (a[0].as_str(), a[1].as_str()))
        .collect();
    ensure!(
        options.keys().all(|k| [
            "--dataset",
            "--entities",
            "--mentions-per",
            "--noise",
            "--seed",
            "--repeats",
            "--output"
        ]
        .contains(k)),
        "unknown evaluation argument"
    );
    ensure!(
        options.get("--dataset").is_none_or(|v| *v == "synthetic"),
        "only synthetic data is bundled"
    );
    let entities = options
        .get("--entities")
        .unwrap_or(&"100")
        .parse::<usize>()?;
    let per = options
        .get("--mentions-per")
        .unwrap_or(&"3")
        .parse::<usize>()?;
    let noise = options.get("--noise").unwrap_or(&"0.1").parse::<f64>()?;
    let seed = options.get("--seed").unwrap_or(&"42").parse::<u64>()?;
    let repeats = options.get("--repeats").unwrap_or(&"3").parse::<usize>()?;
    ensure!(
        entities > 0
            && per > 0
            && entities.saturating_mul(per) <= 10000
            && (0.0..=1.0).contains(&noise)
            && (1..=100).contains(&repeats),
        "evaluation limits: 1..10000 mentions; 1..100 repeats; noise 0..1"
    );
    let mut ms = vec![];
    let mut truth = vec![];
    let mut rng = seed;
    for entity in 0..entities {
        let mut code = String::new();
        let mut x = entity + 1;
        for _ in 0..6 {
            code.push((b'a' + (x % 26) as u8) as char);
            x /= 26;
        }
        let name = format!("Subject {code}");
        for mention in 0..per {
            rng = rng.wrapping_mul(6364136223846793005).wrapping_add(1);
            let mut surface = name.clone();
            if mention > 0 && (rng >> 11) as f64 / ((1u64 << 53) as f64) < noise {
                surface.push('x');
            }
            let label = format!("{seed}:{entity}:{mention}");
            ms.push(Mention {
                id: Uuid::new_v5(&Uuid::NAMESPACE_OID, label.as_bytes()),
                evidence_id: Uuid::new_v5(&Uuid::NAMESPACE_URL, label.as_bytes()),
                byte_offset: 0,
                offset_space: OffsetSpace::SourceBytes,
                surface,
                kind: MentionKind::Person,
                context: format!("research group {code}"),
                valid_from: 0,
                valid_to: 100,
                attributes: BTreeMap::new(),
                provenance: None,
            });
            truth.push(entity);
        }
    }
    let mut latencies = vec![];
    let mut report = serde_json::Value::Null;
    for _ in 0..repeats {
        let start = Instant::now();
        let candidates = erps_store::index::candidates(&ms, false)?;
        let pairs: Vec<_> = candidates
            .iter()
            .map(|&(a, b)| cluster::Pair {
                a,
                b,
                score: similarity::score(&ms[a], &ms[b]),
            })
            .collect();
        let clusters = cluster::pivot_cluster(&ms, &pairs, &[], seed)?;
        let mut predicted = vec![0; ms.len()];
        for (i, c) in clusters.iter().enumerate() {
            for &j in c {
                predicted[j] = i;
            }
        }
        latencies.push(start.elapsed().as_secs_f64() * 1000.0);
        report = erps_eval::metrics(&truth, &predicted)?;
        let true_candidates = candidates
            .iter()
            .filter(|&&(a, b)| truth[a] == truth[b])
            .count();
        let true_pairs = entities * per * (per - 1) / 2;
        let total = ms.len() * (ms.len() - 1) / 2;
        report["blocking_recall"] = serde_json::json!(if true_pairs == 0 {
            1.0
        } else {
            true_candidates as f64 / true_pairs as f64
        });
        report["blocking_quality"] = serde_json::json!(if candidates.is_empty() {
            0.0
        } else {
            true_candidates as f64 / candidates.len() as f64
        });
        report["blocking_reduction"] = serde_json::json!(if total == 0 {
            0.0
        } else {
            1.0 - candidates.len() as f64 / total as f64
        });
        report["candidate_pairs"] = serde_json::json!(candidates.len());
    }
    latencies.sort_by(f64::total_cmp);
    for (key, q) in [
        ("latency_p50_ms", 0.5),
        ("latency_p95_ms", 0.95),
        ("latency_p99_ms", 0.99),
    ] {
        report[key] = serde_json::json!(
            latencies[((q * latencies.len() as f64).ceil() as usize).saturating_sub(1)]
        );
    }
    report["dataset"] = serde_json::json!({"type":"synthetic","entities":entities,"mentions_per_entity":per,"noise":noise,"seed":seed,"repeats":repeats,"timing_scope":"in-process blocking, scoring, clustering; excludes HTTP and persistence"});
    let output = serde_json::to_string_pretty(&report)?;
    if let Some(path) = options.get("--output") {
        std::fs::write(path, &output)?;
    }
    println!("{output}");
    Ok(())
}
