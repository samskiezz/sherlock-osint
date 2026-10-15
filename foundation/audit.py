"""Transactionally serialised audit hashes; external anchoring is needed against owner rewriting."""

import hashlib
import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import AuditLog, AuditHead, utcnow


def event_hash(
    time: str, actor: str | None, action: str, detail: dict[str, Any], previous: str
) -> str:
    """Calculate a canonical event/predecessor digest."""
    value = json.dumps(
        {"time": time, "actor": actor, "action": action, "detail": detail},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256((previous + "\n" + value).encode()).hexdigest()


def record(s: Session, actor: str | None, action: str, detail: dict[str, Any]) -> None:
    """Append within the caller's transaction while holding the shared chain-head lock."""
    head = s.execute(
        select(AuditHead).where(AuditHead.id == 1).with_for_update()
    ).scalar_one()
    stamp = utcnow()
    digest = event_hash(stamp.isoformat(), actor, action, detail, head.digest)
    s.add(
        AuditLog(
            time=stamp,
            actor=actor,
            action=action,
            detail=detail,
            previous_hash=head.digest,
            entry_hash=digest,
        )
    )
    head.digest = digest
    s.flush()


def verify(s: Session) -> dict[str, Any]:
    """Verify all stored events and the committed head without repairing records."""
    from datetime import timezone

    head = s.execute(
        select(AuditHead).where(AuditHead.id == 1).with_for_update()
    ).scalar_one()
    previous = "0" * 64
    issues = []
    count = 0
    for row in s.scalars(select(AuditLog).order_by(AuditLog.id)):
        stamp = (
            row.time.replace(tzinfo=timezone.utc)
            if row.time.tzinfo is None
            else row.time
        )
        digest = event_hash(
            stamp.isoformat(), row.actor, row.action, row.detail, previous
        )
        if row.previous_hash != previous or row.entry_hash != digest:
            issues.append(row.id)
        previous = digest
        count += 1
    return {
        "valid": not issues and bool(head) and head.digest == previous,
        "events": count,
        "head_sha256": previous,
        "issues": issues,
        "limitation": "A database owner can rewrite the chain. Retain an external anchor.",
    }
