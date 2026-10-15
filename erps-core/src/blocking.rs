use crate::{
    mention::{normalize, tokens},
    Mention,
};
use std::collections::BTreeSet;
pub fn keys(m: &Mention) -> Vec<String> {
    let prefix = format!("{:?}:", m.kind);
    let s = normalize(&m.surface);
    let t = tokens(&s);
    let mut keys = BTreeSet::from([
        format!("{prefix}exact:{s}"),
        format!(
            "{prefix}tokens:{}",
            t.iter().cloned().collect::<Vec<_>>().join("|")
        ),
    ]);
    let chars: Vec<_> = s.chars().collect();
    for w in chars.windows(3) {
        keys.insert(format!("{prefix}tri:{}", w.iter().collect::<String>()));
    }
    for (k, v) in &m.attributes {
        keys.insert(format!("{prefix}id:{k}:{v}"));
    }
    keys.into_iter().collect()
}
/// Deterministic hash family for optional MinHash band blocking. The classical
/// probability formula assumes independent ideal permutations; this is an approximation.
pub fn minhash_bands(s: &str, bands: usize, rows: usize) -> Vec<(usize, Vec<u64>)> {
    let t = tokens(s);
    if t.is_empty() || rows == 0 || bands == 0 || bands.saturating_mul(rows) > 512 {
        return vec![];
    }
    let sig: Vec<u64> = (0..bands * rows)
        .map(|row| {
            t.iter()
                .map(|t| {
                    let mut h =
                        14695981039346656037u64 ^ (row as u64).wrapping_mul(0x9e3779b97f4a7c15);
                    for b in t.bytes() {
                        h = (h ^ u64::from(b)).wrapping_mul(1099511628211);
                    }
                    h ^= h >> 30;
                    h = h.wrapping_mul(0xbf58476d1ce4e5b9);
                    h ^= h >> 27;
                    h = h.wrapping_mul(0x94d049bb133111eb);
                    h ^ (h >> 31)
                })
                .min()
                .unwrap()
        })
        .collect();
    sig.chunks(rows)
        .enumerate()
        .map(|(i, v)| (i, v.to_vec()))
        .collect()
}
pub fn collision_probability(j: f64, b: u32, r: i32) -> f64 {
    1.0 - (1.0 - j.powi(r)).powi(b as i32)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bands_and_probability() {
        assert_eq!(
            minhash_bands("John Smith", 16, 4),
            minhash_bands("smith JOHN", 16, 4)
        );
        assert!(minhash_bands("", 16, 4).is_empty());
        assert!((collision_probability(0.5, 32, 4) - 0.873211).abs() < 0.00001);
    }
}
