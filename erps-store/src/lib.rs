pub mod index;
use anyhow::{ensure, Result};
use chrono::{DateTime, Utc};
use erps_core::{cluster::Constraint, Mention, Polynomial};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sqlx::{PgPool, Postgres, Row, Transaction};
use std::collections::BTreeMap;
use uuid::Uuid;
pub type Tx<'a> = Transaction<'a, Postgres>;
pub fn digest(bytes: impl AsRef<[u8]>) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub async fn connect(url: &str) -> Result<PgPool> {
    let pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(8)
        .connect(url)
        .await?;
    sqlx::migrate!("./migrations").run(&pool).await?;
    Ok(pool)
}
#[derive(Debug, Clone)]
pub struct Policy {
    pub workspace: Uuid,
    pub actor: String,
    pub purpose: String,
    pub write: bool,
    pub delete: bool,
    pub properties: Option<Vec<String>>,
    pub sources: Option<Vec<Uuid>>,
    pub kinds: Option<Vec<String>>,
}
impl Policy {
    pub fn full(&self) -> bool {
        self.properties.is_none() && self.sources.is_none() && self.kinds.is_none()
    }
    pub fn visible(&self, e: &Value) -> bool {
        let sources = e["provenance"].clone();
        let Ok(p) = serde_json::from_value::<Polynomial>(sources) else {
            return false;
        };
        let mut referenced = p.support();
        if let Some(mentions) = e["mentions"].as_array() {
            for m in mentions {
                if let Some(source) = m["evidence_id"].as_str() {
                    referenced.insert(source.to_owned());
                }
            }
        }
        self.sources.as_ref().is_none_or(|allowed| {
            referenced
                .iter()
                .all(|s| Uuid::parse_str(s).is_ok_and(|id| allowed.contains(&id)))
        }) && self
            .kinds
            .as_ref()
            .is_none_or(|k| e["kind"].as_str().is_some_and(|s| k.iter().any(|x| x == s)))
    }
    pub fn project(&self, mut value: Value) -> Value {
        if let Some(props) = &self.properties {
            if let Some(obj) = value.as_object_mut() {
                obj.retain(|k, _| k == "id" || props.contains(k));
                obj.insert("properties_withheld".into(), json!(true));
            }
        }
        value
    }
}
pub async fn authenticate(pool: &PgPool, token: &str, purpose: &str) -> Result<Option<Policy>> {
    let row =
        sqlx::query("SELECT * FROM erps.policies WHERE token_hash=$1 AND enabled AND purpose=$2")
            .bind(digest(token))
            .bind(purpose)
            .fetch_optional(pool)
            .await?;
    row.map(|r| {
        Ok(Policy {
            workspace: r.try_get("workspace")?,
            actor: r.try_get("actor")?,
            purpose: r.try_get("purpose")?,
            write: r.try_get("can_write")?,
            delete: r.try_get("can_delete")?,
            properties: r.try_get("properties")?,
            sources: r.try_get("visible_sources")?,
            kinds: r.try_get("kinds")?,
        })
    })
    .transpose()
}
pub async fn bootstrap(pool: &PgPool, token: &str, workspace: Uuid) -> Result<()> {
    ensure!(
        token.len() >= 32,
        "ERPS_TOKEN must contain at least 32 characters"
    );
    sqlx::query("INSERT INTO erps.policies(token_hash,workspace,actor,can_write,can_delete) VALUES($1,$2,'sherlock-service',true,true) ON CONFLICT(token_hash) DO NOTHING").bind(digest(token)).bind(workspace).execute(pool).await?;
    Ok(())
}
pub async fn lock(tx: &mut Tx<'_>, workspace: Uuid) -> Result<()> {
    sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))")
        .bind(workspace.to_string())
        .execute(&mut **tx)
        .await?;
    Ok(())
}
pub async fn mentions(tx: &mut Tx<'_>, workspace: Uuid) -> Result<Vec<Mention>> {
    let values: Vec<Value> = sqlx::query_scalar(
        "SELECT payload FROM erps.mentions WHERE workspace=$1 ORDER BY id LIMIT 10001",
    )
    .bind(workspace)
    .fetch_all(&mut **tx)
    .await?;
    ensure!(
        values.len() <= 10_000,
        "workspace mention limit exceeded (10000)"
    );
    values
        .into_iter()
        .map(|v| Ok(serde_json::from_value(v)?))
        .collect()
}
pub async fn constraints(tx: &mut Tx<'_>, workspace: Uuid) -> Result<Vec<Constraint>> {
    let rows =
        sqlx::query("SELECT a,b,must_link FROM erps.constraints WHERE workspace=$1 ORDER BY a,b")
            .bind(workspace)
            .fetch_all(&mut **tx)
            .await?;
    rows.into_iter()
        .map(|r| {
            Ok(Constraint {
                a: r.try_get("a")?,
                b: r.try_get("b")?,
                must_link: r.try_get("must_link")?,
            })
        })
        .collect()
}
pub fn sources(p: &Polynomial) -> Result<Vec<Uuid>> {
    p.support()
        .iter()
        .map(|v| Ok(Uuid::parse_str(v)?))
        .collect()
}
pub async fn insert_mention(tx: &mut Tx<'_>, w: Uuid, m: &Mention) -> Result<()> {
    m.validate()?;
    let allowed: Vec<String> =
        sqlx::query_scalar("SELECT strong_attributes FROM erps.ontology_types WHERE kind=$1")
            .bind(format!("{:?}", m.kind))
            .fetch_one(&mut **tx)
            .await?;
    ensure!(
        m.attributes.keys().all(|k| allowed.contains(k)),
        "identifier is not permitted by the ontology type"
    );
    let p = m.annotation();
    p.count()?;
    let src = sources(&p)?;
    let deleted: bool = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM erps.deleted_sources WHERE workspace=$1 AND source=ANY($2))",
    )
    .bind(w)
    .bind(&src)
    .fetch_one(&mut **tx)
    .await?;
    ensure!(!deleted, "source has been retracted");
    let payload = serde_json::to_value(m)?;
    let existing: Option<Value> =
        sqlx::query_scalar("SELECT payload FROM erps.mentions WHERE workspace=$1 AND id=$2")
            .bind(w)
            .bind(m.id)
            .fetch_optional(&mut **tx)
            .await?;
    if let Some(prior) = existing {
        let previous: Mention = serde_json::from_value(prior)?;
        ensure!(
            previous == *m,
            "mention ID already exists with different content"
        );
        return Ok(());
    }
    sqlx::query("INSERT INTO erps.mentions(workspace,id,payload,sources) VALUES($1,$2,$3,$4)")
        .bind(w)
        .bind(m.id)
        .bind(payload)
        .bind(src)
        .execute(&mut **tx)
        .await?;
    Ok(())
}
pub async fn add_constraint(tx: &mut Tx<'_>, w: Uuid, c: &Constraint) -> Result<()> {
    ensure!(c.a != c.b, "self constraints are forbidden");
    let (a, b) = (c.a.min(c.b), c.a.max(c.b));
    let prior: Option<bool> = sqlx::query_scalar(
        "SELECT must_link FROM erps.constraints WHERE workspace=$1 AND a=$2 AND b=$3",
    )
    .bind(w)
    .bind(a)
    .bind(b)
    .fetch_optional(&mut **tx)
    .await?;
    ensure!(
        prior.is_none_or(|p| p == c.must_link),
        "contradictory constraint already exists"
    );
    sqlx::query("INSERT INTO erps.constraints VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING")
        .bind(w)
        .bind(a)
        .bind(b)
        .bind(c.must_link)
        .execute(&mut **tx)
        .await?;
    Ok(())
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entity {
    pub id: Uuid,
    pub canonical_name: String,
    pub kind: String,
    pub mention_ids: Vec<Uuid>,
    pub aliases: Vec<String>,
    pub provenance: Polynomial,
    pub mentions: Vec<Mention>,
    pub attributes: BTreeMap<String, Vec<AttributeValue>>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttributeValue {
    pub value: String,
    pub valid_from: i64,
    pub valid_to: i64,
    pub mention_id: Uuid,
}
pub async fn save_entities(tx: &mut Tx<'_>, w: Uuid, entities: &[Entity]) -> Result<()> {
    let stamp: DateTime<Utc> = sqlx::query_scalar("SELECT clock_timestamp()")
        .fetch_one(&mut **tx)
        .await?;
    let old: Vec<(Uuid, Value)> =
        sqlx::query_as("SELECT id,payload FROM erps.entities WHERE workspace=$1")
            .bind(w)
            .fetch_all(&mut **tx)
            .await?;
    let old: BTreeMap<_, _> = old.into_iter().collect();
    let new: BTreeMap<_, _> = entities
        .iter()
        .map(|e| Ok((e.id, serde_json::to_value(e)?)))
        .collect::<Result<_>>()?;
    for (id, payload) in &old {
        if new.get(id) != Some(payload) {
            sqlx::query("UPDATE erps.entity_versions SET recorded_to=$3 WHERE workspace=$1 AND id=$2 AND recorded_to IS NULL").bind(w).bind(id).bind(stamp).execute(&mut **tx).await?;
        }
    }
    sqlx::query("DELETE FROM erps.entity_mentions WHERE workspace=$1")
        .bind(w)
        .execute(&mut **tx)
        .await?;
    sqlx::query("DELETE FROM erps.entities WHERE workspace=$1")
        .bind(w)
        .execute(&mut **tx)
        .await?;
    for e in entities {
        let value = serde_json::to_value(e)?;
        e.provenance.count()?;
        if old.get(&e.id) != Some(&value) {
            sqlx::query("INSERT INTO erps.entity_versions(workspace,id,payload,recorded_from) VALUES($1,$2,$3,$4)").bind(w).bind(e.id).bind(&value).bind(stamp).execute(&mut **tx).await?;
        }
        sqlx::query("INSERT INTO erps.entities VALUES($1,$2,$3,$4,$5,$6)")
            .bind(w)
            .bind(e.id)
            .bind(&e.canonical_name)
            .bind(&e.kind)
            .bind(value)
            .bind(sources(&e.provenance)?)
            .execute(&mut **tx)
            .await?;
        for id in &e.mention_ids {
            sqlx::query("INSERT INTO erps.entity_mentions VALUES($1,$2,$3)")
                .bind(w)
                .bind(id)
                .bind(e.id)
                .execute(&mut **tx)
                .await?;
        }
    }
    Ok(())
}
/// Locks the per-workspace sequence. The chain detects accidental/tampered rows;
/// an external checkpoint is needed against a malicious database administrator.
pub async fn audit(tx: &mut Tx<'_>, p: &Policy, action: &str, details: Value) -> Result<String> {
    lock(tx, p.workspace).await?;
    let last: Option<(i64, String)> = sqlx::query_as(
        "SELECT sequence,hash FROM erps.audit WHERE workspace=$1 ORDER BY sequence DESC LIMIT 1",
    )
    .bind(p.workspace)
    .fetch_optional(&mut **tx)
    .await?;
    let (seq, previous) = last.map(|(n, h)| (n + 1, h)).unwrap_or((1, "0".repeat(64)));
    let event = json!({"actor":p.actor,"purpose":p.purpose,"action":action,"details":details,"recorded_at":Utc::now().to_rfc3339()});
    let hash = digest(format!(
        "{}\n{}\n{}\n{}",
        p.workspace,
        seq,
        previous,
        serde_json::to_string(&event)?
    ));
    sqlx::query("INSERT INTO erps.audit VALUES($1,$2,$3,$4,$5)")
        .bind(p.workspace)
        .bind(seq)
        .bind(previous)
        .bind(&hash)
        .bind(event)
        .execute(&mut **tx)
        .await?;
    Ok(hash)
}
pub async fn verify_audit(tx: &mut Tx<'_>, w: Uuid) -> Result<Value> {
    let rows = sqlx::query("SELECT * FROM erps.audit WHERE workspace=$1 ORDER BY sequence")
        .bind(w)
        .fetch_all(&mut **tx)
        .await?;
    let mut prev = "0".repeat(64);
    for (i, r) in rows.iter().enumerate() {
        let seq: i64 = r.try_get("sequence")?;
        let stored: String = r.try_get("hash")?;
        let event: Value = r.try_get("event")?;
        let prior: String = r.try_get("previous_hash")?;
        ensure!(
            seq == i as i64 + 1
                && prior == prev
                && digest(format!(
                    "{w}\n{seq}\n{prev}\n{}",
                    serde_json::to_string(&event)?
                )) == stored,
            "audit chain mismatch"
        );
        prev = stored;
    }
    Ok(json!({"valid":true,"events":rows.len(),"head":prev}))
}
