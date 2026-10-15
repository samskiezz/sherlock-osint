//! Seeded, constrained pivot heuristic for a partial candidate graph. No
//! approximation guarantee is claimed for this constrained sparse setting.
use crate::{
    similarity::{decide, Decision},
    Mention, Polynomial,
};
use anyhow::{ensure, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use uuid::Uuid;
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Pair {
    pub a: usize,
    pub b: usize,
    pub score: f64,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Constraint {
    pub a: Uuid,
    pub b: Uuid,
    pub must_link: bool,
}
struct UnionFind(Vec<usize>);
impl UnionFind {
    fn root(&mut self, x: usize) -> usize {
        if self.0[x] != x {
            self.0[x] = self.root(self.0[x]);
        }
        self.0[x]
    }
    fn union(&mut self, a: usize, b: usize) {
        let a = self.root(a);
        let b = self.root(b);
        if a != b {
            self.0[b] = a.min(b);
            self.0[a] = a.min(b);
        }
    }
}
pub fn pivot_cluster(
    ms: &[Mention],
    pairs: &[Pair],
    constraints: &[Constraint],
    seed: u64,
) -> Result<Vec<Vec<usize>>> {
    let n = ms.len();
    let mut uf = UnionFind((0..n).collect());
    let ids: BTreeMap<_, _> = ms.iter().enumerate().map(|(i, m)| (m.id, i)).collect();
    let mut cannot = BTreeSet::new();
    for c in constraints {
        let a = *ids
            .get(&c.a)
            .ok_or_else(|| anyhow::anyhow!("constraint mention missing"))?;
        let b = *ids
            .get(&c.b)
            .ok_or_else(|| anyhow::anyhow!("constraint mention missing"))?;
        if c.must_link {
            uf.union(a, b)
        } else {
            cannot.insert((a.min(b), a.max(b)));
        }
    }
    let mut groups: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
    for i in 0..n {
        groups.entry(uf.root(i)).or_default().push(i);
    }
    let compatible =
        |a: usize, b: usize| !ms[a].conflict(&ms[b]) && !cannot.contains(&(a.min(b), a.max(b)));
    for g in groups.values() {
        for &a in g {
            for &b in g {
                ensure!(
                    compatible(a, b),
                    "must-link contradicts type, temporal identifiers, or cannot-link"
                );
            }
        }
    }
    let mut positive = BTreeMap::<usize, BTreeSet<usize>>::new();
    let mut negative = BTreeSet::new();
    for p in pairs {
        ensure!(
            p.a < n && p.b < n && p.score.is_finite() && (0.0..=1.0).contains(&p.score),
            "invalid scored pair"
        );
        let a = uf.root(p.a);
        let b = uf.root(p.b);
        match decide(p.score) {
            Decision::Merge => {
                positive.entry(a).or_default().insert(b);
                positive.entry(b).or_default().insert(a);
            }
            Decision::New => {
                negative.insert((p.a.min(p.b), p.a.max(p.b)));
            }
            Decision::Review => {}
        }
    }
    // Seeded deterministic priorities make retry/reordered ingestion reproducible.
    let mut order: Vec<_> = groups.keys().copied().collect();
    order.sort_by_key(|&g| {
        let id = ms[groups[&g][0]].id.as_u128();
        let mut x = (id as u64) ^ (id >> 64) as u64 ^ seed;
        x = (x ^ (x >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        x ^ (x >> 27)
    });
    let mut assigned = BTreeSet::new();
    let mut out = vec![];
    for pivot in order {
        if !assigned.insert(pivot) {
            continue;
        }
        let mut cluster = groups[&pivot].clone();
        for neighbor in positive.get(&pivot).into_iter().flatten() {
            if assigned.contains(neighbor) {
                continue;
            }
            let group = &groups[neighbor];
            if cluster.iter().all(|&a| {
                group
                    .iter()
                    .all(|&b| compatible(a, b) && !negative.contains(&(a.min(b), a.max(b))))
            }) {
                assigned.insert(*neighbor);
                cluster.extend(group);
            }
        }
        cluster.sort_unstable();
        out.push(cluster);
    }
    out.sort_by_key(|g| g[0]);
    Ok(out)
}
pub fn annotation(ms: &[Mention], cluster: &[usize]) -> Result<Polynomial> {
    cluster
        .iter()
        .try_fold(Polynomial::zero(), |p, &i| p.add(&ms[i].annotation()))
}
pub fn canonical(ms: &[Mention], cluster: &[usize]) -> String {
    let mut counts = BTreeMap::<&str, usize>::new();
    for &i in cluster {
        *counts.entry(&ms[i].surface).or_default() += 1;
    }
    counts
        .into_iter()
        .max_by(|(a, ca), (b, cb)| ca.cmp(cb).then(a.len().cmp(&b.len())).then(b.cmp(a)))
        .map(|(s, _)| s.to_owned())
        .unwrap_or_default()
}
