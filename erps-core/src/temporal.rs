use anyhow::{ensure, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Allen {
    Before,
    Meets,
    Overlaps,
    Starts,
    During,
    Finishes,
    Equals,
    After,
    MetBy,
    OverlappedBy,
    StartedBy,
    Contains,
    FinishedBy,
}
pub fn relation(a: (i64, i64), b: (i64, i64)) -> Result<Allen> {
    ensure!(a.0 < a.1 && b.0 < b.1, "intervals must be nonempty");
    use Allen::*;
    Ok(if a == b {
        Equals
    } else if a.1 < b.0 {
        Before
    } else if a.1 == b.0 {
        Meets
    } else if a.0 > b.1 {
        After
    } else if a.0 == b.1 {
        MetBy
    } else if a.0 == b.0 {
        if a.1 < b.1 {
            Starts
        } else {
            StartedBy
        }
    } else if a.1 == b.1 {
        if a.0 > b.0 {
            Finishes
        } else {
            FinishedBy
        }
    } else if a.0 > b.0 && a.1 < b.1 {
        During
    } else if a.0 < b.0 && a.1 > b.1 {
        Contains
    } else if a.0 < b.0 {
        Overlaps
    } else {
        OverlappedBy
    })
}
/// Enumerate endpoint order types: six distinct endpoints suffice for three
/// intervals, including equalities. This avoids an incomplete hand-copied table.
pub fn compose(a: Allen, b: Allen) -> BTreeSet<Allen> {
    let intervals: Vec<_> = (0..6)
        .flat_map(|i| (i + 1..6).map(move |j| (i, j)))
        .collect();
    let mut result = BTreeSet::new();
    for &x in &intervals {
        for &y in &intervals {
            if relation(x, y).unwrap() != a {
                continue;
            }
            for &z in &intervals {
                if relation(y, z).unwrap() == b {
                    result.insert(relation(x, z).unwrap());
                }
            }
        }
    }
    result
}
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Bitemporal {
    pub valid_from: i64,
    pub valid_to: i64,
    pub recorded_from: i64,
    pub recorded_to: Option<i64>,
}
impl Bitemporal {
    pub fn visible(&self, valid: i64, recorded: i64) -> bool {
        self.valid_from <= valid
            && valid < self.valid_to
            && self.recorded_from <= recorded
            && self.recorded_to.is_none_or(|end| recorded < end)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn all_13_exclusive() {
        let mut seen = BTreeSet::new();
        for a in 0..5 {
            for b in a + 1..6 {
                for c in 0..5 {
                    for d in c + 1..6 {
                        seen.insert(relation((a, b), (c, d)).unwrap());
                    }
                }
            }
        }
        assert_eq!(seen.len(), 13);
        assert_eq!(relation((0, 1), (1, 2)).unwrap(), Allen::Meets);
        assert_eq!(
            compose(Allen::Before, Allen::Before),
            BTreeSet::from([Allen::Before])
        );
    }
}
