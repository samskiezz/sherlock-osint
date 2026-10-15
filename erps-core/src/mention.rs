use crate::Polynomial;
use anyhow::{ensure, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use unicode_normalization::UnicodeNormalization;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MentionKind {
    Person,
    Organisation,
    Location,
    Handle,
    Email,
    Phone,
    Doi,
    Patent,
    Document,
    Date,
}
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum OffsetSpace {
    #[default]
    SourceBytes,
    ExtractedTextUtf8,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Mention {
    pub id: Uuid,
    pub evidence_id: Uuid,
    pub byte_offset: u64,
    #[serde(default)]
    pub offset_space: OffsetSpace,
    pub surface: String,
    pub kind: MentionKind,
    #[serde(default)]
    pub context: String,
    pub valid_from: i64,
    pub valid_to: i64,
    #[serde(default)]
    pub attributes: BTreeMap<String, String>,
    #[serde(default)]
    pub provenance: Option<Polynomial>,
}
pub const STRONG: &[&str] = &["passport", "national_id", "registration_id", "doi"];
impl Mention {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            !self.id.is_nil() && !self.evidence_id.is_nil(),
            "nil identifiers are forbidden"
        );
        ensure!(
            self.valid_from < self.valid_to,
            "valid_from must precede valid_to"
        );
        ensure!(
            !normalize(&self.surface).is_empty() && self.surface.len() <= 1024,
            "surface must contain 1..1024 bytes"
        );
        ensure!(
            self.context.len() <= 8192 && self.attributes.len() <= 32,
            "mention size limit exceeded"
        );
        ensure!(
            self.attributes
                .iter()
                .all(|(k, v)| STRONG.contains(&k.as_str()) && !v.is_empty() && v.len() <= 256),
            "unknown or invalid strong identifier"
        );
        ensure!(
            self.annotation().boolean(),
            "zero-provenance mention is not a fact"
        );
        // All source variables are UUIDs; provenance is supplied only through trusted writes.
        for var in self.annotation().support() {
            ensure!(
                Uuid::parse_str(&var).is_ok(),
                "source variables must be UUIDs"
            );
        }
        Ok(())
    }
    pub fn annotation(&self) -> Polynomial {
        self.provenance
            .clone()
            .unwrap_or_else(|| Polynomial::variable(self.evidence_id.to_string()))
    }
    pub fn overlaps(&self, b: &Self) -> bool {
        self.valid_from < b.valid_to && b.valid_from < self.valid_to
    }
    pub fn conflict(&self, b: &Self) -> bool {
        self.kind != b.kind
            || (self.overlaps(b)
                && self
                    .attributes
                    .iter()
                    .any(|(k, v)| b.attributes.get(k).is_some_and(|w| v != w)))
    }
    pub fn strong_match(&self, b: &Self) -> bool {
        self.kind == b.kind
            && self
                .attributes
                .iter()
                .any(|(k, v)| b.attributes.get(k) == Some(v))
    }
}
pub fn normalize(s: &str) -> String {
    s.nfkc()
        .flat_map(char::to_lowercase)
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}
pub fn tokens(s: &str) -> std::collections::BTreeSet<String> {
    normalize(s)
        .split(|c: char| !c.is_alphanumeric())
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .collect()
}
