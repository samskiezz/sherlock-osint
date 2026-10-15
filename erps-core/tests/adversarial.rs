//! Bounded exhaustive checks over finite input families, not production-scale claims.
use erps_core::{
    cluster::{pivot_cluster, Constraint, Pair},
    provenance::why_multiply,
    Mention, Polynomial,
};
use serde_json::json;
use uuid::Uuid;

#[test]
fn exhaustive_small_polynomials_preserve_semiring_and_deletion_homomorphisms() {
    let x = Polynomial::variable("x");
    let y = Polynomial::variable("y");
    let basis = [
        Polynomial::one(),
        x.clone(),
        y.clone(),
        x.multiply(&y).unwrap(),
    ];
    let polynomials: Vec<_> = (0..16)
        .map(|mask| {
            basis
                .iter()
                .enumerate()
                .fold(Polynomial::zero(), |p, (i, term)| {
                    if mask & (1 << i) != 0 {
                        p.add(term).unwrap()
                    } else {
                        p
                    }
                })
        })
        .collect();
    for a in &polynomials {
        assert_eq!(
            serde_json::from_value::<Polynomial>(serde_json::to_value(a).unwrap()).unwrap(),
            *a
        );
        for b in &polynomials {
            let sum = a.add(b).unwrap();
            let product = a.multiply(b).unwrap();
            assert_eq!(sum, b.add(a).unwrap());
            assert_eq!(product, b.multiply(a).unwrap());
            assert_eq!(
                sum.count().unwrap(),
                a.count().unwrap() + b.count().unwrap()
            );
            assert_eq!(
                product.count().unwrap(),
                a.count().unwrap() * b.count().unwrap()
            );
            assert_eq!(product.why(), why_multiply(&a.why(), &b.why()));
            assert_eq!(sum.boolean(), a.boolean() || b.boolean());
            assert_eq!(product.boolean(), a.boolean() && b.boolean());
            for source in ["x", "y"] {
                assert_eq!(
                    sum.retract(source),
                    a.retract(source).add(&b.retract(source)).unwrap()
                );
                assert_eq!(
                    product.retract(source),
                    a.retract(source).multiply(&b.retract(source)).unwrap()
                );
            }
            for c in &polynomials {
                assert_eq!(sum.add(c).unwrap(), a.add(&b.add(c).unwrap()).unwrap());
                assert_eq!(
                    product.multiply(c).unwrap(),
                    a.multiply(&b.multiply(c).unwrap()).unwrap()
                );
                assert_eq!(
                    a.multiply(&b.add(c).unwrap()).unwrap(),
                    a.multiply(b).unwrap().add(&a.multiply(c).unwrap()).unwrap()
                );
            }
        }
    }
}

#[test]
fn mutated_provenance_wire_never_panics_and_accepted_values_round_trip() {
    let seed = br#"{"monomials":[{"vars":["x","y"],"coeff":2},{"vars":["z"],"coeff":1}]}"#;
    let mut state = 0x6c35_13f2_d83a_77b1_u64;
    for iteration in 0..20_000 {
        let mut bytes = seed.to_vec();
        for _ in 0..1 + iteration % 5 {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            let index = (state as usize) % bytes.len();
            bytes[index] ^= (state >> 32) as u8;
        }
        let parsed = std::panic::catch_unwind(|| serde_json::from_slice::<Polynomial>(&bytes));
        assert!(
            parsed.is_ok(),
            "wire decoder panicked at mutation {iteration}"
        );
        if let Ok(value) = parsed.unwrap() {
            let round_trip = serde_json::to_vec(&value).unwrap();
            assert_eq!(
                serde_json::from_slice::<Polynomial>(&round_trip).unwrap(),
                value
            );
            assert_eq!(value.retract("x").retract("x"), value.retract("x"));
        }
    }
}

#[test]
fn exhaustive_four_node_hard_constraints_are_respected_or_rejected() {
    let mentions: Vec<Mention> = (1..=4)
        .map(|i| {
            serde_json::from_value(json!({"id":Uuid::from_u128(i),
            "evidence_id":Uuid::from_u128(i+100),"byte_offset":0,
            "surface":"Owned Fixture","kind":"Person","valid_from":0,"valid_to":10}))
            .unwrap()
        })
        .collect();
    let pairs: Vec<_> = (0..4)
        .flat_map(|a| (a + 1..4).map(move |b| Pair { a, b, score: 1.0 }))
        .collect();
    // Three choices per pair: absent, must-link, cannot-link; 3^6 = 729 graphs.
    for graph in 0..729 {
        let mut remaining = graph;
        let mut constraints = Vec::new();
        let mut closure = [[false; 4]; 4];
        for (i, row) in closure.iter_mut().enumerate() {
            row[i] = true;
        }
        for pair in &pairs {
            let kind = remaining % 3;
            remaining /= 3;
            if kind != 0 {
                constraints.push(Constraint {
                    a: mentions[pair.a].id,
                    b: mentions[pair.b].id,
                    must_link: kind == 1,
                });
                if kind == 1 {
                    closure[pair.a][pair.b] = true;
                    closure[pair.b][pair.a] = true;
                }
            }
        }
        for k in 0..4 {
            for i in 0..4 {
                for j in 0..4 {
                    closure[i][j] |= closure[i][k] && closure[k][j];
                }
            }
        }
        let inconsistent = constraints.iter().any(|constraint| {
            let a = mentions.iter().position(|m| m.id == constraint.a).unwrap();
            let b = mentions.iter().position(|m| m.id == constraint.b).unwrap();
            !constraint.must_link && closure[a][b]
        });
        for seed in 0..4 {
            let result = pivot_cluster(&mentions, &pairs, &constraints, seed);
            if inconsistent {
                assert!(result.is_err());
                continue;
            }
            let groups = result.unwrap();
            let mut membership = [usize::MAX; 4];
            for (group, members) in groups.iter().enumerate() {
                for &member in members {
                    assert_eq!(membership[member], usize::MAX);
                    membership[member] = group;
                }
            }
            assert!(membership.iter().all(|&group| group != usize::MAX));
            for constraint in &constraints {
                let a = mentions.iter().position(|m| m.id == constraint.a).unwrap();
                let b = mentions.iter().position(|m| m.id == constraint.b).unwrap();
                assert_eq!(membership[a] == membership[b], constraint.must_link);
            }
        }
    }
}
