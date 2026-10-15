mod pipeline;
use axum::{
    extract::{DefaultBodyLimit, Path, Query, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use erps_core::{cluster::Constraint, Mention, Polynomial};
use erps_store::{self as store, Policy};
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::{PgPool, Row};
use std::{
    collections::BTreeSet,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
    time::Instant,
};
use tokio::sync::Semaphore;
use uuid::Uuid;
#[derive(Clone)]
struct App {
    pool: PgPool,
    lsh: bool,
    batch_threshold: usize,
    gate: Arc<Semaphore>,
    requests: Arc<AtomicU64>,
    pairs: Arc<AtomicU64>,
    micros: Arc<AtomicU64>,
}
struct Error(StatusCode, String);
impl From<anyhow::Error> for Error {
    fn from(e: anyhow::Error) -> Self {
        if e.downcast_ref::<sqlx::Error>().is_some() {
            tracing::error!(error=%e,"database operation failed");
            Self(
                StatusCode::SERVICE_UNAVAILABLE,
                "Database operation failed; transaction rolled back".into(),
            )
        } else {
            Self(StatusCode::UNPROCESSABLE_ENTITY, e.to_string())
        }
    }
}
impl From<sqlx::Error> for Error {
    fn from(e: sqlx::Error) -> Self {
        anyhow::Error::from(e).into()
    }
}
impl IntoResponse for Error {
    fn into_response(self) -> Response {
        (self.0, Json(json!({"detail":self.1}))).into_response()
    }
}
type Result<T> = std::result::Result<T, Error>;
async fn policy(a: &App, h: &HeaderMap) -> Result<Policy> {
    let token = h
        .get("authorization")
        .and_then(|h| h.to_str().ok())
        .and_then(|s| s.strip_prefix("Bearer "))
        .ok_or_else(|| Error(StatusCode::UNAUTHORIZED, "Bearer token required".into()))?;
    let purpose = h
        .get("x-erps-purpose")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    store::authenticate(&a.pool, token, purpose)
        .await?
        .ok_or_else(|| Error(StatusCode::FORBIDDEN, "Policy denied".into()))
}
fn write(p: &Policy, delete: bool) -> Result<()> {
    if p.full() && p.write && (!delete || p.delete) {
        Ok(())
    } else {
        Err(Error(
            StatusCode::FORBIDDEN,
            "Full workspace write policy required".into(),
        ))
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Resolve {
    mentions: Vec<Mention>,
    #[serde(default)]
    constraints: Vec<Constraint>,
}
async fn resolve(
    State(a): State<App>,
    h: HeaderMap,
    Json(r): Json<Resolve>,
) -> Result<Json<Value>> {
    let p = policy(&a, &h).await?;
    write(&p, false)?;
    if r.mentions.len() > 1000
        || r.constraints.len() > 1000
        || (r.mentions.is_empty() && r.constraints.is_empty())
    {
        return Err(Error(
            StatusCode::BAD_REQUEST,
            "Submit 1..1000 mentions or constraints".into(),
        ));
    }
    let _permit = a.gate.try_acquire().map_err(|_| {
        Error(
            StatusCode::TOO_MANY_REQUESTS,
            "Resolution capacity reached; retry later".into(),
        )
    })?;
    let started = Instant::now();
    let mut tx = a.pool.begin().await?;
    store::lock(&mut tx, p.workspace).await?;
    for m in &r.mentions {
        store::insert_mention(&mut tx, p.workspace, m).await?;
    }
    for c in &r.constraints {
        store::add_constraint(&mut tx, p.workspace, c).await?;
    }
    let (entities, n, engine) = pipeline::rebuild(&mut tx, &p, a.lsh, a.batch_threshold).await?;
    let hash=store::audit(&mut tx,&p,"resolve",json!({"mention_ids":r.mentions.iter().map(|m|m.id).collect::<Vec<_>>(),"constraints":r.constraints,"entities":entities.iter().map(|e|e.id).collect::<Vec<_>>(),"candidate_pairs":n,"scoring_engine":engine})).await?;
    tx.commit().await?;
    a.requests.fetch_add(1, Ordering::Relaxed);
    a.pairs.fetch_add(n as u64, Ordering::Relaxed);
    a.micros
        .fetch_add(started.elapsed().as_micros() as u64, Ordering::Relaxed);
    Ok(Json(
        json!({"entities":entities,"candidate_pairs":n,"scoring_engine":engine,"scores_calibrated":false,"clustering":"constrained_seeded_pivot","audit_head":hash,"duration_ms":started.elapsed().as_millis()}),
    ))
}
#[derive(Deserialize)]
struct List {
    #[serde(default)]
    after: Option<Uuid>,
    #[serde(default)]
    limit: Option<usize>,
    #[serde(default)]
    q: Option<String>,
    #[serde(default)]
    kind: Option<String>,
    #[serde(default)]
    valid_at: Option<i64>,
}
async fn list(State(a): State<App>, h: HeaderMap, Query(q): Query<List>) -> Result<Json<Value>> {
    let p = policy(&a, &h).await?;
    if p.properties.as_ref().is_some_and(|props| {
        (q.q.as_ref().is_some_and(|s| !s.is_empty())
            && !props.iter().any(|s| s == "canonical_name"))
            || (q.kind.is_some() && !props.iter().any(|s| s == "kind"))
            || (q.valid_at.is_some() && !props.iter().any(|s| s == "mentions"))
    }) {
        return Err(Error(
            StatusCode::FORBIDDEN,
            "Filtering a withheld property is prohibited".into(),
        ));
    }
    let limit = q.limit.unwrap_or(50).clamp(1, 100);
    let mut tx = a.pool.begin().await?;
    store::lock(&mut tx, p.workspace).await?;
    let rows:Vec<Value>=sqlx::query_scalar("SELECT payload FROM erps.entities WHERE workspace=$1 AND ($2::uuid IS NULL OR id>$2) AND ($3::text IS NULL OR strpos(lower(name),lower($3))>0) AND ($4::text IS NULL OR kind=$4) ORDER BY id LIMIT 10001").bind(p.workspace).bind(q.after).bind(&q.q).bind(&q.kind).fetch_all(&mut *tx).await?;
    let visible: Vec<_> = rows
        .into_iter()
        .filter(|e| {
            p.visible(e)
                && q.valid_at.is_none_or(|t| {
                    e["mentions"].as_array().is_some_and(|ms| {
                        ms.iter().any(|m| {
                            m["valid_from"].as_i64().unwrap_or(i64::MAX) <= t
                                && t < m["valid_to"].as_i64().unwrap_or(i64::MIN)
                        })
                    })
                })
        })
        .collect();
    let next = if visible.len() > limit {
        visible.get(limit - 1).map(|v| v["id"].clone())
    } else {
        None
    };
    let ids: Vec<_> = visible
        .iter()
        .take(limit)
        .map(|e| e["id"].clone())
        .collect();
    let items: Vec<_> = visible
        .into_iter()
        .take(limit)
        .map(|mut e| {
            e.as_object_mut().unwrap().remove("mentions");
            p.project(e)
        })
        .collect();
    store::audit(
        &mut tx,
        &p,
        "list_entities",
        json!({"ids":ids,"properties":p.properties}),
    )
    .await?;
    tx.commit().await?;
    Ok(Json(json!({"entities":items,"next":next})))
}
async fn entity_value(
    tx: &mut store::Tx<'_>,
    p: &Policy,
    id: Uuid,
    asof: Option<chrono::DateTime<chrono::Utc>>,
) -> Result<Value> {
    let v: Option<Value> = if let Some(t) = asof {
        sqlx::query_scalar("SELECT payload FROM erps.entity_versions WHERE workspace=$1 AND id=$2 AND recorded_from<=$3 AND (recorded_to IS NULL OR $3<recorded_to) ORDER BY recorded_from DESC LIMIT 1").bind(p.workspace).bind(id).bind(t).fetch_optional(&mut **tx).await?
    } else {
        sqlx::query_scalar("SELECT payload FROM erps.entities WHERE workspace=$1 AND id=$2")
            .bind(p.workspace)
            .bind(id)
            .fetch_optional(&mut **tx)
            .await?
    };
    v.filter(|e| p.visible(e))
        .ok_or_else(|| Error(StatusCode::NOT_FOUND, "Entity not found".into()))
}
#[derive(Deserialize)]
struct AsOf {
    as_of: Option<chrono::DateTime<chrono::Utc>>,
}
async fn entity(
    State(a): State<App>,
    h: HeaderMap,
    Path(id): Path<Uuid>,
    Query(q): Query<AsOf>,
) -> Result<Json<Value>> {
    let p = policy(&a, &h).await?;
    let mut tx = a.pool.begin().await?;
    store::lock(&mut tx, p.workspace).await?;
    let e = entity_value(&mut tx, &p, id, q.as_of).await?;
    store::audit(
        &mut tx,
        &p,
        "get_entity",
        json!({"id":id,"as_of":q.as_of,"properties":p.properties}),
    )
    .await?;
    tx.commit().await?;
    Ok(Json(p.project(e)))
}
async fn lineage(State(a): State<App>, h: HeaderMap, Path(id): Path<Uuid>) -> Result<Json<Value>> {
    let p = policy(&a, &h).await?;
    let mut tx = a.pool.begin().await?;
    store::lock(&mut tx, p.workspace).await?;
    let e = entity_value(&mut tx, &p, id, None).await?;
    if p.properties
        .as_ref()
        .is_some_and(|props| !props.iter().any(|s| s == "provenance"))
    {
        return Err(Error(
            StatusCode::FORBIDDEN,
            "Provenance property denied".into(),
        ));
    }
    let poly: Polynomial =
        serde_json::from_value(e["provenance"].clone()).map_err(anyhow::Error::from)?;
    let decisions=sqlx::query("SELECT a,b,score,decision,provenance FROM erps.pair_decisions WHERE workspace=$1 AND (entity_a=$2 OR entity_b=$2) ORDER BY a,b").bind(p.workspace).bind(id).fetch_all(&mut *tx).await?;
    // Pair provenance involving other entities may expose their hidden sources.
    let mut edges = vec![];
    for r in decisions {
        let pv: Value = r.try_get("provenance")?;
        let test = json!({"provenance":pv,"kind":e["kind"]});
        if p.visible(&test)
            && p.properties
                .as_ref()
                .is_none_or(|props| props.iter().any(|s| s == "decisions"))
        {
            edges.push(json!({"a":r.try_get::<Uuid,_>("a")?,"b":r.try_get::<Uuid,_>("b")?,"score":r.try_get::<f64,_>("score")?,"decision":r.try_get::<String,_>("decision")?,"provenance":pv}));
        }
    }
    store::audit(
        &mut tx,
        &p,
        "get_lineage",
        json!({"id":id,"properties":["provenance"]}),
    )
    .await?;
    tx.commit().await?;
    Ok(Json(
        json!({"entity_id":id,"how":poly,"support":poly.support(),"why":poly.why(),"minimal_witnesses":poly.minimal_witnesses(),"boolean":poly.boolean(),"count":poly.count()?,"semantics":"membership evidence; clustering decisions are listed separately","decisions":edges}),
    ))
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Deletion {
    source_var: Uuid,
}
async fn deletion(
    State(a): State<App>,
    h: HeaderMap,
    Json(r): Json<Deletion>,
) -> Result<Json<Value>> {
    let p = policy(&a, &h).await?;
    write(&p, true)?;
    let _permit = a.gate.try_acquire().map_err(|_| {
        Error(
            StatusCode::TOO_MANY_REQUESTS,
            "Resolution capacity reached".into(),
        )
    })?;
    let started = Instant::now();
    let mut tx = a.pool.begin().await?;
    store::lock(&mut tx, p.workspace).await?;
    let before: Vec<Uuid> = sqlx::query_scalar(
        "SELECT id FROM erps.entities WHERE workspace=$1 AND sources @> ARRAY[$2]::uuid[]",
    )
    .bind(p.workspace)
    .bind(r.source_var)
    .fetch_all(&mut *tx)
    .await?;
    let all_before: std::collections::BTreeMap<Uuid, Value> = sqlx::query_as::<_, (Uuid, Value)>(
        "SELECT id,payload FROM erps.entities WHERE workspace=$1",
    )
    .bind(p.workspace)
    .fetch_all(&mut *tx)
    .await?
    .into_iter()
    .collect();
    let all = store::mentions(&mut tx, p.workspace).await?;
    let mut removed = vec![];
    let mut changed = 0;
    for mut m in all {
        let old = m.annotation();
        let poly = old.retract(&r.source_var.to_string());
        if poly == old {
            continue;
        }
        changed += 1;
        if !poly.boolean() {
            sqlx::query("DELETE FROM erps.mentions WHERE workspace=$1 AND id=$2")
                .bind(p.workspace)
                .bind(m.id)
                .execute(&mut *tx)
                .await?;
            removed.push(m.id);
        } else {
            m.provenance = Some(poly.clone());
            sqlx::query(
                "UPDATE erps.mentions SET payload=$3,sources=$4 WHERE workspace=$1 AND id=$2",
            )
            .bind(p.workspace)
            .bind(m.id)
            .bind(json!(m))
            .bind(store::sources(&poly)?)
            .execute(&mut *tx)
            .await?;
        }
    }
    sqlx::query("DELETE FROM erps.constraints WHERE workspace=$1 AND (a=ANY($2) OR b=ANY($2))")
        .bind(p.workspace)
        .bind(&removed)
        .execute(&mut *tx)
        .await?;
    sqlx::query(
        "INSERT INTO erps.deleted_sources(workspace,source) VALUES($1,$2) ON CONFLICT DO NOTHING",
    )
    .bind(p.workspace)
    .bind(r.source_var)
    .execute(&mut *tx)
    .await?;
    let (entities, _, _) = pipeline::rebuild(&mut tx, &p, a.lsh, a.batch_threshold).await?;
    let deleted: Vec<_> = all_before
        .keys()
        .filter(|id| !entities.iter().any(|e| e.id == **id))
        .collect();
    let modified: Vec<_> = entities
        .iter()
        .filter(|e| {
            all_before
                .get(&e.id)
                .is_some_and(|old| serde_json::to_value(e).ok().as_ref() != Some(old))
        })
        .map(|e| e.id)
        .collect();
    let head=store::audit(&mut tx,&p,"retract_source",json!({"source":r.source_var,"removed_mentions":removed,"affected_entities":before,"result_entities":entities.iter().map(|e|e.id).collect::<Vec<_>>()})).await?;
    tx.commit().await?;
    Ok(Json(
        json!({"deleted_entities":deleted,"modified_entities":modified,"entities":entities,"affected_mentions":changed,"removed_mentions":removed,"audit_head":head,"duration_ms":started.elapsed().as_millis()}),
    ))
}
#[derive(Deserialize)]
struct Neighborhood {
    depth: Option<usize>,
    limit: Option<usize>,
}
async fn neighbors(
    State(a): State<App>,
    h: HeaderMap,
    Path(id): Path<Uuid>,
    Query(q): Query<Neighborhood>,
) -> Result<Json<Value>> {
    let p = policy(&a, &h).await?;
    if p.properties
        .as_ref()
        .is_some_and(|props| !props.iter().any(|s| s == "relationships"))
    {
        return Err(Error(
            StatusCode::FORBIDDEN,
            "Relationship property denied".into(),
        ));
    }
    let mut tx = a.pool.begin().await?;
    store::lock(&mut tx, p.workspace).await?;
    let root = entity_value(&mut tx, &p, id, None).await?;
    let mut nodes = vec![p.project(root)];
    let mut edges = vec![];
    let mut seen = BTreeSet::from([id]);
    let mut frontier = vec![id];
    let limit = q.limit.unwrap_or(50).clamp(1, 100);
    let mut truncated = false;
    for _ in 0..q.depth.unwrap_or(1).clamp(1, 3) {
        let rows=sqlx::query("SELECT entity_a,entity_b,max(score) AS score FROM erps.pair_decisions WHERE workspace=$1 AND entity_a<>entity_b AND decision IN ('Review','Merge') AND (entity_a=ANY($2) OR entity_b=ANY($2)) GROUP BY entity_a,entity_b ORDER BY entity_a,entity_b LIMIT 1001").bind(p.workspace).bind(&frontier).fetch_all(&mut *tx).await?;
        let mut next = vec![];
        if rows.len() > 1000 {
            truncated = true;
        }
        for r in rows.into_iter().take(1000) {
            let x: Uuid = r.try_get("entity_a")?;
            let y: Uuid = r.try_get("entity_b")?;
            let ex = entity_value(&mut tx, &p, x, None).await;
            let ey = entity_value(&mut tx, &p, y, None).await;
            if let (Ok(ex), Ok(ey)) = (ex, ey) {
                for (v, e) in [(x, ex), (y, ey)] {
                    if !seen.contains(&v) {
                        if nodes.len() >= limit {
                            truncated = true;
                            continue;
                        }
                        seen.insert(v);
                        next.push(v);
                        nodes.push(p.project(e));
                    }
                }
                if seen.contains(&x) && seen.contains(&y) {
                    let edge = json!({"a":x,"b":y,"kind":"candidate_review","score":r.try_get::<f64,_>("score")?});
                    if !edges.contains(&edge) {
                        edges.push(edge);
                    }
                }
            }
        }
        frontier = next;
        if frontier.is_empty() {
            break;
        }
    }
    store::audit(
        &mut tx,
        &p,
        "neighbors",
        json!({"id":id,"returned_ids":seen}),
    )
    .await?;
    tx.commit().await?;
    Ok(Json(
        json!({"entities":nodes,"edges":edges,"truncated":truncated}),
    ))
}
async fn audit_verify(State(a): State<App>, h: HeaderMap) -> Result<Json<Value>> {
    let p = policy(&a, &h).await?;
    write(&p, false)?;
    let mut tx = a.pool.begin().await?;
    store::lock(&mut tx, p.workspace).await?;
    let result = store::verify_audit(&mut tx, p.workspace).await?;
    store::audit(&mut tx, &p, "verify_audit", json!({})).await?;
    tx.commit().await?;
    Ok(Json(result))
}
async fn health(State(a): State<App>) -> Result<Json<Value>> {
    sqlx::query("SELECT 1").execute(&a.pool).await?;
    Ok(Json(
        json!({"status":"ok","version":env!("CARGO_PKG_VERSION"),"authoritative_store":"postgres","index":"tantivy_snapshot","lsh":a.lsh,"scores_calibrated":false,"max_workspace_mentions":10000}),
    ))
}
async fn ontology(State(a): State<App>, h: HeaderMap) -> Result<Json<Value>> {
    let p = policy(&a, &h).await?;
    let mut tx = a.pool.begin().await?;
    store::lock(&mut tx, p.workspace).await?;
    let rows = sqlx::query(
        "SELECT kind,strong_attributes,description FROM erps.ontology_types ORDER BY kind",
    )
    .fetch_all(&mut *tx)
    .await?;
    let mut types = vec![];
    for r in rows {
        let kind: String = r.try_get("kind")?;
        if p.kinds.as_ref().is_none_or(|ks| ks.contains(&kind)) {
            types.push(json!({"kind":kind,"strong_attributes":r.try_get::<Vec<String>,_>("strong_attributes")?,"description":r.try_get::<String,_>("description")?}));
        }
    }
    store::audit(&mut tx, &p, "get_ontology", json!({})).await?;
    tx.commit().await?;
    Ok(Json(json!({"types":types,"logical_entailment":false})))
}
async fn metrics(State(a): State<App>, h: HeaderMap) -> Result<String> {
    let p = policy(&a, &h).await?;
    write(&p, false)?;
    Ok(format!("# TYPE erps_resolve_requests_total counter\nerps_resolve_requests_total {}\n# TYPE erps_candidates_total counter\nerps_candidates_total {}\n# TYPE erps_resolve_duration_seconds_total counter\nerps_resolve_duration_seconds_total {}\n# TYPE erps_postgres_pool_connections gauge\nerps_postgres_pool_connections {}\n",a.requests.load(Ordering::Relaxed),a.pairs.load(Ordering::Relaxed),a.micros.load(Ordering::Relaxed) as f64/1_000_000.0,a.pool.size()))
}
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()),
        )
        .init();
    let url = std::env::var("ERPS_DATABASE_URL")?;
    let token = std::env::var("ERPS_TOKEN")?;
    let workspace = Uuid::parse_str(&std::env::var("ERPS_WORKSPACE")?)?;
    let pool = store::connect(&url).await?;
    store::bootstrap(&pool, &token, workspace).await?;
    let mut role_tokens = BTreeSet::from([store::digest(&token)]);
    for (env, actor, can_write) in [
        ("ERPS_READER_TOKEN", "gateway-viewer", false),
        ("ERPS_WRITER_TOKEN", "gateway-analyst", true),
    ] {
        if let Ok(token) = std::env::var(env) {
            anyhow::ensure!(token.len() >= 32, "role token is too short");
            anyhow::ensure!(
                role_tokens.insert(store::digest(&token)),
                "role tokens must be distinct"
            );
            sqlx::query("INSERT INTO erps.policies(token_hash,workspace,actor,can_write) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING").bind(store::digest(token)).bind(workspace).bind(actor).bind(can_write).execute(&pool).await?;
        }
    }
    let a = App {
        pool,
        lsh: std::env::var("ERPS_LSH").is_ok_and(|v| v == "1"),
        batch_threshold: std::env::var("ERPS_BATCH_THRESHOLD")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(10000),
        gate: Arc::new(Semaphore::new(2)),
        requests: Arc::new(AtomicU64::new(0)),
        pairs: Arc::new(AtomicU64::new(0)),
        micros: Arc::new(AtomicU64::new(0)),
    };
    let router = Router::new()
        .route("/resolve", post(resolve))
        .route("/entities", get(list))
        .route("/entities/:id", get(entity))
        .route("/entities/:id/neighbors", get(neighbors))
        .route("/lineage/:id", get(lineage))
        .route("/deletion", post(deletion))
        .route("/audit/verify", get(audit_verify))
        .route("/health", get(health))
        .route("/ontology", get(ontology))
        .route("/metrics", get(metrics))
        .layer(DefaultBodyLimit::max(8 * 1024 * 1024))
        .with_state(a);
    let bind = std::env::var("ERPS_BIND").unwrap_or_else(|_| "127.0.0.1:3000".into());
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    tracing::info!(bind, "ERPS listening");
    axum::serve(listener, router)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}
