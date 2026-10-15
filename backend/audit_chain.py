"""Tamper-evident audit chain. A database owner can bypass triggers/rewrite the chain."""

import sqlite3
import hashlib
import json
from typing import Any
from fastapi import Response

GENESIS = "0" * 64


def digest(row: Any, previous: str) -> str:
    """Hash an exact event and its predecessor using canonical JSON."""
    canonical = json.dumps(
        {k: row[k] for k in ("id", "time", "action", "detail")},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256((previous + "\n" + canonical).encode("utf-8")).hexdigest()


def migrate(connection: sqlite3.Connection) -> None:
    """Backfill legacy audit events once and install append-only triggers."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS audit_chain(audit_id INTEGER PRIMARY KEY,previous_hash TEXT NOT NULL,entry_hash TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS audit_chain_migration(id INTEGER PRIMARY KEY CHECK(id=1),legacy_through INTEGER NOT NULL)"
    )
    # Backfill only once. Later missing chain rows are integrity failures, never silently repaired.
    if not connection.execute(
        "SELECT 1 FROM audit_chain_migration WHERE id=1"
    ).fetchone():
        previous = GENESIS
        last = 0
        for row in connection.execute("SELECT * FROM audit ORDER BY id"):
            h = digest(row, previous)
            connection.execute(
                "INSERT INTO audit_chain VALUES(?,?,?)", (row["id"], previous, h)
            )
            previous = h
            last = row["id"]
        connection.execute("INSERT INTO audit_chain_migration VALUES(1,?)", (last,))
    for table in ("audit", "audit_chain", "audit_chain_migration"):
        for action in ("UPDATE", "DELETE"):
            connection.execute(
                f"CREATE TRIGGER IF NOT EXISTS {table}_deny_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Audit records are append-only'); END"
            )


def append(
    connection: sqlite3.Connection, timestamp: str, action: str, detail: str
) -> int:
    """Atomically append an event and chain hash, refusing an inconsistent head."""
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    last = connection.execute(
        "SELECT audit_id,entry_hash FROM audit_chain ORDER BY audit_id DESC LIMIT 1"
    ).fetchone()
    latest = connection.execute("SELECT max(id) FROM audit").fetchone()[0]
    if latest != (last["audit_id"] if last else None):
        raise RuntimeError("Audit head is inconsistent; refusing unchained append")
    previous = last["entry_hash"] if last else GENESIS
    row_id = connection.execute(
        "INSERT INTO audit(time,action,detail) VALUES(?,?,?)",
        (timestamp, action, detail),
    ).lastrowid
    value = {"id": row_id, "time": timestamp, "action": action, "detail": detail}
    connection.execute(
        "INSERT INTO audit_chain VALUES(?,?,?)",
        (row_id, previous, digest(value, previous)),
    )
    return row_id


def verify(connection: sqlite3.Connection) -> dict[str, Any]:
    """Check every predecessor and event hash without repairing history."""
    previous = GENESIS
    count = 0
    issues = []
    rows = connection.execute(
        "SELECT a.*, c.previous_hash, c.entry_hash FROM audit a LEFT JOIN audit_chain c ON a.id=c.audit_id ORDER BY a.id"
    )
    for row in rows:
        expected = digest(row, previous)
        if row["previous_hash"] != previous or row["entry_hash"] != expected:
            issues.append(
                {
                    "audit_id": row["id"],
                    "reason": "Missing chain row, changed event, or broken predecessor hash",
                }
            )
        previous = expected
        count += 1
    orphan = connection.execute(
        "SELECT c.audit_id FROM audit_chain c LEFT JOIN audit a ON a.id=c.audit_id WHERE a.id IS NULL"
    ).fetchall()
    issues.extend({"audit_id": r[0], "reason": "Audit event missing"} for r in orphan)
    migration = connection.execute(
        "SELECT legacy_through FROM audit_chain_migration WHERE id=1"
    ).fetchone()
    if not migration:
        issues.append({"reason": "Migration anchor missing"})
    return {
        "valid": not issues,
        "events_checked": count,
        "head_sha256": previous,
        "issues": issues,
        "legacy_records_through": migration[0] if migration else None,
        "limitation": "Backfilled records are not retroactively authenticated. SQLite-owner access can remove triggers and rewrite the entire chain. Save an exported head externally to detect rewriting or suffix truncation.",
    }


def install(core: Any) -> None:
    """Register persistent analysis or audit endpoints and workers."""

    @core.app.get("/api/audit/verify")
    def audit_verify() -> dict[str, Any]:
        """Return the current audit-chain integrity check."""
        with core.lock, core.db() as c:
            return verify(c)

    @core.app.get("/api/audit/anchor")
    def anchor() -> Response:
        """Export a hash head for independent retention outside the database."""
        with core.lock, core.db() as c:
            result = {**verify(c), "exported_utc": core.now()}
        return Response(
            json.dumps(result, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="looking-glass-audit-anchor.json"'
            },
        )
