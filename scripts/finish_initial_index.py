"""Drain the bounded existing-vault index queue; normal continuous monitoring remains active."""

import json
from pathlib import Path
import sqlite3
import time
import httpx

root = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=20)
end = time.monotonic() + 600
last_report = 0
while time.monotonic() < end:
    with sqlite3.connect(root / "data/case.db") as db:
        source_rows = db.execute(
            "SELECT id,metadata FROM evidence WHERE sha256 IS NOT NULL"
        ).fetchall()
        eligible = {
            eid
            for eid, value in source_rows
            if (m := json.loads(value)).get("processing_status") == "COMPLETE"
            and m.get("derivative_hashes", {}).get("text.txt")
        }
        done = {
            row[0]
            for row in db.execute(
                "SELECT evidence_id FROM retrieval_documents WHERE status='COMPLETE'"
            )
        }
    missing = eligible - done
    status = c.get("/api/knowledge/status").json()
    if not missing and not status["running"]:
        record = {
            "eligible_acquired_records": len(eligible),
            "completed_index_records": len(done),
            "failed_or_unindexed_ids": sorted(missing),
            "chunks": status["chunks"],
            "identifier_occurrences": status["identifier_occurrences"],
            "continuous_interval_seconds": 60,
            "finished_utc": status["last_cycle"],
        }
        (root / "artifacts/initial-index-complete-v9.json").write_text(
            json.dumps(record, indent=2)
        )
        print(json.dumps(record))
        break
    if not status["running"]:
        c.post("/api/knowledge/index", json={}).raise_for_status()
    if time.monotonic() - last_report >= 30:
        print(
            json.dumps(
                {
                    "completed": len(done),
                    "eligible": len(eligible),
                    "remaining": len(missing),
                    "chunks": status["chunks"],
                    "error": status["error"],
                }
            ),
            flush=True,
        )
        last_report = time.monotonic()
    time.sleep(2)
else:
    raise RuntimeError(
        "Initial indexing did not complete within its ten-minute verification budget; background monitoring remains active"
    )
