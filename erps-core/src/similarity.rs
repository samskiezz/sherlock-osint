use crate::mention::{normalize, tokens};
use crate::Mention;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
pub const MERGE_THRESHOLD: f64 = 0.92;
pub const REVIEW_THRESHOLD: f64 = 0.80;
pub fn jaccard(a: &BTreeSet<String>, b: &BTreeSet<String>) -> f64 {
    let n = a.union(b).count();
    if n == 0 {
        0.0
    } else {
        a.intersection(b).count() as f64 / n as f64
    }
}
pub fn name_similarity(a: &str, b: &str) -> f64 {
    let a = normalize(a);
    let b = normalize(b);
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    0.4 * strsim::jaro_winkler(&a, &b)
        + 0.3 * strsim::normalized_levenshtein(&a, &b)
        + 0.3 * jaccard(&tokens(&a), &tokens(&b))
}
pub fn context_similarity(a: &str, b: &str) -> f64 {
    jaccard(&tokens(a), &tokens(b))
}
pub fn score(a: &Mention, b: &Mention) -> f64 {
    // Missing context is not contradictory evidence. Use name-only if either is absent.
    let n = name_similarity(&a.surface, &b.surface);
    if tokens(&a.context).is_empty() || tokens(&b.context).is_empty() {
        n
    } else {
        0.75 * n + 0.25 * context_similarity(&a.context, &b.context)
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Decision {
    Merge,
    Review,
    New,
}
pub fn decide(s: f64) -> Decision {
    if s >= MERGE_THRESHOLD {
        Decision::Merge
    } else if s >= REVIEW_THRESHOLD {
        Decision::Review
    } else {
        Decision::New
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unicode_empty_and_thresholds() {
        assert_eq!(name_similarity("ＪＯＨＮ Smith", "john smith"), 1.0);
        assert_eq!(name_similarity("", ""), 0.0);
        assert_eq!(decide(0.92), Decision::Merge);
        assert_eq!(decide(0.8), Decision::Review);
    }
}
