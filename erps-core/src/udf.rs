//! Arrow arrays provide the batch contract. String similarity itself remains a
//! scalar algorithm; columnar transport does not imply SIMD acceleration.
use crate::{cluster::Pair, similarity, Mention};
use datafusion::{
    arrow::{
        array::{Array, Float64Array, StringArray, UInt64Array},
        datatypes::{DataType, Field, Schema},
        record_batch::RecordBatch,
    },
    error::{DataFusionError, Result},
    logical_expr::{create_udf, ColumnarValue, Volatility},
    prelude::{SessionConfig, SessionContext},
};
use std::sync::Arc;
pub fn similarity_udf(name: &str, f: fn(&str, &str) -> f64) -> datafusion::logical_expr::ScalarUDF {
    create_udf(
        name,
        vec![DataType::Utf8, DataType::Utf8],
        DataType::Float64,
        Volatility::Immutable,
        Arc::new(move |args| {
            let arrays = ColumnarValue::values_to_arrays(args)?;
            if arrays.len() != 2 {
                return Err(DataFusionError::Execution(
                    "two string arguments required".into(),
                ));
            }
            let a = arrays[0]
                .as_any()
                .downcast_ref::<StringArray>()
                .ok_or_else(|| DataFusionError::Execution("expected Utf8".into()))?;
            let b = arrays[1]
                .as_any()
                .downcast_ref::<StringArray>()
                .ok_or_else(|| DataFusionError::Execution("expected Utf8".into()))?;
            if a.len() != b.len() {
                return Err(DataFusionError::Execution("array length mismatch".into()));
            }
            let out: Float64Array = (0..a.len())
                .map(|i| {
                    if a.is_null(i) || b.is_null(i) {
                        None
                    } else {
                        Some(f(a.value(i), b.value(i)))
                    }
                })
                .collect();
            Ok(ColumnarValue::Array(Arc::new(out)))
        }),
    )
}
pub async fn batch_score(ms: &[Mention], pairs: &[(usize, usize)]) -> Result<Vec<Pair>> {
    let ctx = SessionContext::new_with_config(SessionConfig::new().with_target_partitions(2));
    ctx.register_udf(similarity_udf(
        "name_similarity",
        similarity::name_similarity,
    ));
    ctx.register_udf(similarity_udf(
        "context_similarity",
        similarity::context_similarity,
    ));
    let schema = Arc::new(Schema::new(vec![
        Field::new("a", DataType::UInt64, false),
        Field::new("b", DataType::UInt64, false),
        Field::new("sa", DataType::Utf8, false),
        Field::new("sb", DataType::Utf8, false),
        Field::new("ca", DataType::Utf8, false),
        Field::new("cb", DataType::Utf8, false),
    ]));
    let mut out = Vec::with_capacity(pairs.len());
    for chunk in pairs.chunks(8192) {
        let batch = RecordBatch::try_new(
            schema.clone(),
            vec![
                Arc::new(UInt64Array::from_iter_values(
                    chunk.iter().map(|p| p.0 as u64),
                )),
                Arc::new(UInt64Array::from_iter_values(
                    chunk.iter().map(|p| p.1 as u64),
                )),
                Arc::new(StringArray::from_iter_values(
                    chunk.iter().map(|p| ms[p.0].surface.as_str()),
                )),
                Arc::new(StringArray::from_iter_values(
                    chunk.iter().map(|p| ms[p.1].surface.as_str()),
                )),
                Arc::new(StringArray::from_iter_values(
                    chunk.iter().map(|p| ms[p.0].context.as_str()),
                )),
                Arc::new(StringArray::from_iter_values(
                    chunk.iter().map(|p| ms[p.1].context.as_str()),
                )),
            ],
        )?;
        ctx.register_batch("pairs", batch)?;
        let batches=ctx.sql("SELECT a,b,name_similarity(sa,sb) AS name,context_similarity(ca,cb) AS context FROM pairs").await?.collect().await?;
        for b in batches {
            let a = b.column(0).as_any().downcast_ref::<UInt64Array>().unwrap();
            let bs = b.column(1).as_any().downcast_ref::<UInt64Array>().unwrap();
            let name = b.column(2).as_any().downcast_ref::<Float64Array>().unwrap();
            let context = b.column(3).as_any().downcast_ref::<Float64Array>().unwrap();
            for i in 0..b.num_rows() {
                let x = a.value(i) as usize;
                let y = bs.value(i) as usize;
                let missing = crate::mention::tokens(&ms[x].context).is_empty()
                    || crate::mention::tokens(&ms[y].context).is_empty();
                out.push(Pair {
                    a: x,
                    b: y,
                    score: if missing {
                        name.value(i)
                    } else {
                        0.75 * name.value(i) + 0.25 * context.value(i)
                    },
                });
            }
        }
        ctx.deregister_table("pairs")?;
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn multiple_batches_preserve_pairs_and_scalar_scores() -> Result<()> {
        let mentions: Vec<Mention> = (0u128..130)
            .map(|i| {
                serde_json::from_value(serde_json::json!({
                    "id":uuid::Uuid::from_u128(i+1),"evidence_id":uuid::Uuid::from_u128(i+1000),
                    "byte_offset":0,"surface":format!("Ｐｅｒｓｏｎ {i}"),"kind":"Person",
                    "context":if i%2==0 {"shared ünicode context"} else {""},
                    "valid_from":0,"valid_to":100
                }))
                .unwrap()
            })
            .collect();
        let pairs: Vec<_> = (0..mentions.len())
            .flat_map(|a| (a + 1..mentions.len()).map(move |b| (a, b)))
            .collect();
        assert!(pairs.len() > 8192);
        let scored = batch_score(&mentions, &pairs).await?;
        assert_eq!(scored.len(), pairs.len());
        assert_eq!(
            scored
                .iter()
                .map(|p| (p.a, p.b))
                .collect::<std::collections::BTreeSet<_>>(),
            pairs.into_iter().collect()
        );
        for p in scored {
            assert!((p.score - similarity::score(&mentions[p.a], &mentions[p.b])).abs() < 1e-12);
        }
        Ok(())
    }
    #[tokio::test]
    async fn scalar_arrays_and_nulls() -> Result<()> {
        let ctx = SessionContext::new();
        ctx.register_udf(similarity_udf(
            "name_similarity",
            similarity::name_similarity,
        ));
        let rows=ctx.sql("SELECT name_similarity('ＪＯＨＮ Smith','john smith') AS score, name_similarity(CAST(NULL AS VARCHAR),'john') AS missing").await?.collect().await?;
        let scores = rows[0]
            .column(0)
            .as_any()
            .downcast_ref::<Float64Array>()
            .unwrap();
        assert_eq!(scores.value(0), 1.0);
        assert!(rows[0].column(1).is_null(0));
        let batch = RecordBatch::try_from_iter(vec![
            (
                "a",
                Arc::new(StringArray::from(vec![Some("A"), None, Some("same")])) as _,
            ),
            (
                "b",
                Arc::new(StringArray::from(vec![Some("A"), Some("b"), Some("same")])) as _,
            ),
        ])?;
        ctx.register_batch("strings", batch)?;
        let rows = ctx
            .sql("SELECT name_similarity(a,b) FROM strings")
            .await?
            .collect()
            .await?;
        let values = rows[0]
            .column(0)
            .as_any()
            .downcast_ref::<Float64Array>()
            .unwrap();
        assert_eq!(values.len(), 3);
        assert_eq!(values.value(0), 1.0);
        assert!(values.is_null(1));
        assert_eq!(values.value(2), 1.0);
        Ok(())
    }
}
