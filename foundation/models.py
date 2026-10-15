"""Versioned SQLAlchemy case records; the immutable originals remain in the vault."""

from datetime import datetime, timezone
from typing import Any
from sqlalchemy import (
    String,
    Text,
    JSON,
    DateTime,
    Boolean,
    ForeignKey,
    Integer,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import DATABASE_URL


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative schema root."""


class Case(Base):
    """Investigation identity and scope."""

    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Entity(Base):
    """Source-specific entity record; names never automatically merge identities."""

    __tablename__ = "entities"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    kind: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(500))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Evidence(Base):
    """Acquisition metadata and original-file reference, never an AI summary as original."""

    __tablename__ = "evidence_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str | None] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text, default="")
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class User(Base):
    """Argon2 password and encrypted TOTP seed; current role checked on every request."""

    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    totp_seed: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_last_counter: Mapped[int] = mapped_column(Integer, default=-1)
    token_version: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    """Chained gateway events with a separately exportable head."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON)
    previous_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))


class AuditHead(Base):
    """Singleton row lock serialises the hash chain across API and Celery processes."""

    __tablename__ = "audit_head"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))


class CollectionJob(Base):
    """Transactional outbox and execution checkpoint for bounded public-profile checks."""

    __tablename__ = "collection_jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    username: Mapped[str] = mapped_column(String(64))
    authorisation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="QUEUED")
    updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class SchemaVersion(Base):
    """Applied initial schema migration."""

    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)


def migrate() -> None:
    """Apply the additive initial foundation schema without modifying the existing vault."""
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        from sqlalchemy import text

        with engine.begin() as c:
            c.execute(
                text(
                    "CREATE OR REPLACE FUNCTION protect_sherlock_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audit events are append-only'; END; $$"
                )
            )
            c.execute(
                text(
                    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='sherlock_audit_append_only') THEN CREATE TRIGGER sherlock_audit_append_only BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION protect_sherlock_audit(); END IF; END $$"
                )
            )
    with Session.begin() as s:
        if not s.get(SchemaVersion, 1):
            s.add(SchemaVersion(version=1))
        if not s.get(AuditHead, 1):
            s.add(AuditHead(id=1, digest="0" * 64))
        if not s.get(Case, "PROJECT-LOOKING-GLASS"):
            s.add(Case(id="PROJECT-LOOKING-GLASS", name="Project Looking Glass"))
