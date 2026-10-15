//! Exact N[X]. The JSON representation uses an array because JSON object keys
//! cannot represent monomials. Resource limits reject operations atomically.
use anyhow::{bail, ensure, Result};
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use std::collections::{BTreeMap, BTreeSet};

pub const MAX_MONOMIALS: usize = 4096;
pub const MAX_FACTORS: usize = 256;
pub type Witnesses = BTreeSet<BTreeSet<String>>;
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Polynomial(BTreeMap<Vec<String>, u64>);
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Term {
    vars: Vec<String>,
    coeff: u64,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Wire {
    monomials: Vec<Term>,
}
impl Serialize for Polynomial {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        Wire {
            monomials: self
                .0
                .iter()
                .map(|(v, c)| Term {
                    vars: v.clone(),
                    coeff: *c,
                })
                .collect(),
        }
        .serialize(serializer)
    }
}
impl<'de> Deserialize<'de> for Polynomial {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let wire = Wire::deserialize(d)?;
        let mut p = Self::zero();
        for term in wire.monomials {
            p.insert(term.vars, term.coeff)
                .map_err(serde::de::Error::custom)?;
        }
        Ok(p)
    }
}
impl Polynomial {
    pub fn zero() -> Self {
        Self::default()
    }
    pub fn one() -> Self {
        Self(BTreeMap::from([(vec![], 1)]))
    }
    pub fn variable(var: impl Into<String>) -> Self {
        Self(BTreeMap::from([(vec![var.into()], 1)]))
    }
    fn insert(&mut self, mut vars: Vec<String>, coeff: u64) -> Result<()> {
        if coeff == 0 {
            return Ok(());
        }
        ensure!(
            vars.len() <= MAX_FACTORS,
            "provenance factor limit exceeded"
        );
        ensure!(
            vars.iter().all(|v| !v.is_empty() && v.len() <= 128),
            "invalid provenance variable"
        );
        vars.sort();
        let n = self
            .0
            .get(&vars)
            .unwrap_or(&0)
            .checked_add(coeff)
            .ok_or_else(|| anyhow::anyhow!("provenance coefficient overflow"))?;
        if !self.0.contains_key(&vars) && self.0.len() >= MAX_MONOMIALS {
            bail!("provenance monomial limit exceeded");
        }
        self.0.insert(vars, n);
        Ok(())
    }
    pub fn add(&self, other: &Self) -> Result<Self> {
        let mut p = self.clone();
        for (v, c) in &other.0 {
            p.insert(v.clone(), *c)?;
        }
        Ok(p)
    }
    pub fn multiply(&self, other: &Self) -> Result<Self> {
        let mut p = Self::zero();
        for (a, ca) in &self.0 {
            for (b, cb) in &other.0 {
                let c = ca
                    .checked_mul(*cb)
                    .ok_or_else(|| anyhow::anyhow!("provenance coefficient overflow"))?;
                p.insert(a.iter().chain(b).cloned().collect(), c)?;
            }
        }
        Ok(p)
    }
    pub fn support(&self) -> BTreeSet<String> {
        self.0.keys().flatten().cloned().collect()
    }
    pub fn why(&self) -> Witnesses {
        self.0.keys().map(|v| v.iter().cloned().collect()).collect()
    }
    /// Optional absorptive view, distinct from the nonabsorptive Why semiring.
    pub fn minimal_witnesses(&self) -> Witnesses {
        let w = self.why();
        w.iter()
            .filter(|a| !w.iter().any(|b| b != *a && b.is_subset(a)))
            .cloned()
            .collect()
    }
    pub fn boolean(&self) -> bool {
        !self.0.is_empty()
    }
    pub fn count(&self) -> Result<u64> {
        self.0.values().try_fold(0u64, |a, c| {
            a.checked_add(*c)
                .ok_or_else(|| anyhow::anyhow!("provenance count overflow"))
        })
    }
    pub fn retract(&self, var: &str) -> Self {
        Self(
            self.0
                .iter()
                .filter(|(v, _)| !v.iter().any(|x| x == var))
                .map(|(v, c)| (v.clone(), *c))
                .collect(),
        )
    }
}
pub fn why_multiply(a: &Witnesses, b: &Witnesses) -> Witnesses {
    a.iter()
        .flat_map(|x| b.iter().map(move |y| x.union(y).cloned().collect()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn distinct_views_and_retraction() -> Result<()> {
        let x = Polynomial::variable("x");
        let y = Polynomial::variable("y");
        let z = Polynomial::variable("z");
        let p = x.multiply(&y)?.add(&z)?;
        assert_eq!(p.support().len(), 3);
        assert_eq!(p.why().len(), 2);
        assert_eq!(p.retract("x"), z);
        assert_eq!(p.count()?, 2);
        assert!(Polynomial::one().boolean());
        assert!(Polynomial::one().support().is_empty());
        assert_eq!(Polynomial::one().why(), BTreeSet::from([BTreeSet::new()]));
        let q = x.add(&x.multiply(&y)?)?;
        assert_eq!(q.why().len(), 2);
        assert_eq!(q.minimal_witnesses().len(), 1);
        assert_eq!(why_multiply(&x.why(), &y.why()), x.multiply(&y)?.why());
        assert_eq!(
            serde_json::from_value::<Polynomial>(serde_json::to_value(&p)?)?,
            p
        );
        Ok(())
    }
    #[test]
    fn semiring_laws() -> Result<()> {
        let ps = [
            Polynomial::zero(),
            Polynomial::one(),
            Polynomial::variable("a"),
            Polynomial::variable("b").add(&Polynomial::variable("a"))?,
        ];
        for a in &ps {
            for b in &ps {
                for c in &ps {
                    assert_eq!(a.add(b)?, b.add(a)?);
                    assert_eq!(a.multiply(b)?, b.multiply(a)?);
                    assert_eq!(a.add(&b.add(c)?)?, a.add(b)?.add(c)?);
                    assert_eq!(a.multiply(&b.multiply(c)?)?, a.multiply(b)?.multiply(c)?);
                    assert_eq!(
                        a.multiply(&b.add(c)?)?,
                        a.multiply(b)?.add(&a.multiply(c)?)?
                    );
                    assert_eq!(a.multiply(&Polynomial::zero())?, Polynomial::zero());
                    assert_eq!(
                        a.retract("a").multiply(&b.retract("a"))?,
                        a.multiply(b)?.retract("a")
                    );
                }
            }
        }
        Ok(())
    }
    #[test]
    fn reject_overflow_and_invalid_wire() {
        let p: Polynomial =
            serde_json::from_str(r#"{"monomials":[{"vars":["x"],"coeff":18446744073709551615}]}"#)
                .unwrap();
        assert!(p.add(&p).is_err());
        assert!(p.multiply(&p).is_err());
        let zero: Polynomial =
            serde_json::from_str(r#"{"monomials":[{"vars":["x"],"coeff":0}]}"#).unwrap();
        assert!(!zero.boolean());
        assert!(
            serde_json::from_str::<Polynomial>(r#"{"monomials":[{"vars":[""],"coeff":1}]}"#)
                .is_err()
        );
    }
}
