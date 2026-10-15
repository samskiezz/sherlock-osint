pub mod blocking;
pub mod cluster;
pub mod mention;
pub mod provenance;
pub mod similarity;
pub mod temporal;
#[cfg(feature = "batch")]
pub mod udf;

pub use mention::{Mention, MentionKind};
pub use provenance::Polynomial;
