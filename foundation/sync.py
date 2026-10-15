"""Keep PostgreSQL metadata current as the original evidence vault grows."""

import hashlib
import json
from typing import Any
import httpx
from . import config
from .models import Session, Evidence, Entity
from .audit import record
from sqlalchemy.dialects.postgresql import insert


def synchronize() -> dict[str, Any]:
    """Import changed records without moving originals or merging source-specific identities."""
    with httpx.Client(
        base_url=config.CORE_URL,
        headers=config.CORE_HEADERS,
        trust_env=False,
        timeout=30,
    ) as c:
        records = []
        cursor = ""
        seen = set()
        while True:
            r = c.get("/api/vault/catalogue", params={"after": cursor, "limit": 25})
            r.raise_for_status()
            page = r.json()
            records.extend(page["records"])
            following = page["next_cursor"]
            if not following:
                break
            if following in seen or len(records) > 100000:
                raise ValueError("Metadata pagination exceeded its supported bounds")
            seen.add(following)
            cursor = following
    changed = 0
    with Session.begin() as s:
        for e in records:
            original = s.get(Evidence, e["id"])
            value = {
                "title": e["title"],
                "status": e["status"],
                "sha256": e["sha256"],
                "source_url": e["url"] or "",
                "byte_size": e["size"] or 0,
                "provenance": e["metadata"],
            }
            if original and all(getattr(original, k) == v for k, v in value.items()):
                continue
            if not original:
                s.execute(
                    insert(Evidence)
                    .values(id=e["id"], case_id="PROJECT-LOOKING-GLASS", **value)
                    .on_conflict_do_update(index_elements=[Evidence.id], set_=value)
                )
            else:
                for k, v in value.items():
                    setattr(original, k, v)
            if e["kind"] in ("person", "organisation", "event"):
                s.execute(
                    insert(Entity)
                    .values(
                        id=e["id"],
                        case_id="PROJECT-LOOKING-GLASS",
                        kind=e["kind"],
                        name=e["title"],
                        data={
                            "source_evidence_id": e["id"],
                            "attribution": "Source-specific; no automated identity merge",
                        },
                    )
                    .on_conflict_do_nothing(index_elements=[Entity.id])
                )
            changed += 1
        if changed:
            record(
                s,
                None,
                "evidence_metadata_synchronized",
                {
                    "changed": changed,
                    "total_source_records": len(records),
                    "originals_moved": False,
                },
            )
    return {"changed": changed, "records": len(records)}
