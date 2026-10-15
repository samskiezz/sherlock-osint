use anyhow::{ensure, Result};
use serde_json::{json, Value};
use std::collections::BTreeMap;
pub fn metrics(truth: &[usize], predicted: &[usize]) -> Result<Value> {
    ensure!(
        truth.len() == predicted.len(),
        "label arrays must have equal lengths"
    );
    let mut gt = BTreeMap::<usize, u64>::new();
    let mut pr = BTreeMap::<usize, u64>::new();
    let mut cells = BTreeMap::<(usize, usize), u64>::new();
    for (&g, &p) in truth.iter().zip(predicted) {
        *gt.entry(g).or_default() += 1;
        *pr.entry(p).or_default() += 1;
        *cells.entry((g, p)).or_default() += 1;
    }
    let choose = |n: u64| n.saturating_mul(n.saturating_sub(1)) / 2;
    let tp: u64 = cells.values().map(|&n| choose(n)).sum();
    let actual: u64 = gt.values().map(|&n| choose(n)).sum();
    let positive: u64 = pr.values().map(|&n| choose(n)).sum();
    let precision = if positive == 0 {
        if actual == 0 {
            1.0
        } else {
            0.0
        }
    } else {
        tp as f64 / positive as f64
    };
    let recall = if actual == 0 {
        1.0
    } else {
        tp as f64 / actual as f64
    };
    let f1 = |p: f64, r: f64| {
        if p + r == 0.0 {
            0.0
        } else {
            2.0 * p * r / (p + r)
        }
    };
    let n = truth.len() as f64;
    let bp = if n == 0.0 {
        1.0
    } else {
        cells
            .iter()
            .map(|((_, p), &c)| (c * c) as f64 / pr[p] as f64)
            .sum::<f64>()
            / n
    };
    let br = if n == 0.0 {
        1.0
    } else {
        cells
            .iter()
            .map(|((g, _), &c)| (c * c) as f64 / gt[g] as f64)
            .sum::<f64>()
            / n
    };
    let exact = cells
        .iter()
        .filter(|((g, p), c)| **c == gt[g] && **c == pr[p])
        .count() as f64;
    let cp = if pr.is_empty() {
        1.0
    } else {
        exact / pr.len() as f64
    };
    let cr = if gt.is_empty() {
        1.0
    } else {
        exact / gt.len() as f64
    };
    Ok(
        json!({"pairwise_precision":precision,"pairwise_recall":recall,"pairwise_f1":f1(precision,recall),"b_cubed_precision":bp,"b_cubed_recall":br,"b_cubed_f1":f1(bp,br),"cluster_f1":f1(cp,cr),"true_pairs":actual}),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn known_partition() {
        let p = metrics(&[0, 0, 1, 1], &[0, 0, 0, 1]).unwrap();
        assert!((p["pairwise_f1"].as_f64().unwrap() - 0.4).abs() < 1e-12);
        assert!((p["b_cubed_precision"].as_f64().unwrap() - 2.0 / 3.0).abs() < 1e-12);
        assert_eq!(p["b_cubed_recall"], 0.75);
    }
    #[test]
    fn perfect_and_empty() {
        for x in [vec![], vec![0], vec![0, 0, 1]] {
            assert_eq!(metrics(&x, &x).unwrap()["pairwise_f1"], 1.0);
        }
        assert!(metrics(&[0], &[]).is_err());
    }
}
