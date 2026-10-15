use erps_core::{
    cluster::{self, Constraint, Pair},
    Mention, Polynomial,
};
use serde_json::json;
use uuid::Uuid;
fn mention(n: u128) -> Mention {
    serde_json::from_value(json!({"id":Uuid::from_u128(n),"evidence_id":Uuid::from_u128(n+100),"byte_offset":0,"surface":"John Smith","kind":"Person","valid_from":0,"valid_to":10})).unwrap()
}
#[test]
fn cannot_links_are_checked_against_entire_cluster() {
    let ms = vec![mention(1), mention(2), mention(3)];
    let pairs = vec![
        Pair {
            a: 0,
            b: 1,
            score: 1.0,
        },
        Pair {
            a: 1,
            b: 2,
            score: 1.0,
        },
        Pair {
            a: 0,
            b: 2,
            score: 1.0,
        },
    ];
    let c = Constraint {
        a: ms[0].id,
        b: ms[2].id,
        must_link: false,
    };
    for seed in 0..100 {
        let groups = cluster::pivot_cluster(&ms, &pairs, std::slice::from_ref(&c), seed).unwrap();
        assert!(groups.iter().all(|g| !(g.contains(&0) && g.contains(&2))));
        assert_eq!(groups.iter().map(Vec::len).sum::<usize>(), 3);
    }
}
#[test]
fn isolated_nodes_and_hard_constraint_conflict() {
    let ms = vec![mention(1), mention(2)];
    assert_eq!(cluster::pivot_cluster(&ms, &[], &[], 42).unwrap().len(), 2);
    let cs = vec![
        Constraint {
            a: ms[0].id,
            b: ms[1].id,
            must_link: true,
        },
        Constraint {
            a: ms[0].id,
            b: ms[1].id,
            must_link: false,
        },
    ];
    assert!(cluster::pivot_cluster(&ms, &[], &cs, 42).is_err());
}
#[test]
fn temporal_identifier_handoff() {
    let mut a = mention(1);
    let mut b = mention(2);
    a.attributes.insert("passport".into(), "A".into());
    b.attributes.insert("passport".into(), "B".into());
    assert!(a.conflict(&b));
    b.valid_from = 10;
    b.valid_to = 20;
    assert!(!a.conflict(&b));
    let pairs = vec![Pair {
        a: 0,
        b: 1,
        score: 1.0,
    }];
    assert_eq!(
        cluster::pivot_cluster(&[a, b], &pairs, &[], 42)
            .unwrap()
            .len(),
        1
    );
}
#[test]
fn exact_provenance_limits_do_not_change_semantics() {
    let p = Polynomial::variable("x");
    let mut product = Polynomial::one();
    for _ in 0..256 {
        product = product.multiply(&p).unwrap();
    }
    assert!(product.multiply(&p).is_err());
    let terms: Vec<_> = (0..4097)
        .map(|i| json!({"vars":[format!("v{i}")],"coeff":1}))
        .collect();
    assert!(serde_json::from_value::<Polynomial>(json!({"monomials":terms})).is_err());
}
