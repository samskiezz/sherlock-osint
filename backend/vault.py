"""Visible persistent vault inventory, growth snapshots and worker heartbeats."""

import hashlib
import json
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from starlette.background import BackgroundTask


def install(core):
    core.execute(
        "CREATE TABLE IF NOT EXISTS vault_snapshots(bucket INTEGER PRIMARY KEY,created TEXT,data TEXT)"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS worker_heartbeats(name TEXT PRIMARY KEY,updated REAL,data TEXT)"
    )
    heartbeat_times = {}

    def heartbeat(name, data=None):
        stamp = time.time()
        if heartbeat_times.get(name, 0) + 10 > stamp:
            return
        heartbeat_times[name] = stamp
        core.execute(
            "INSERT INTO worker_heartbeats VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET updated=excluded.updated,data=excluded.data",
            (name, stamp, json.dumps(data or {})),
        )

    core.heartbeat = heartbeat

    def inventory():
        entries = core.rows(
            "SELECT id,title,kind,mime,size,sha256,path,status,created,url,metadata FROM evidence ORDER BY created DESC"
        )
        records = []
        physical = {}
        missing = []
        for e in entries:
            meta = json.loads(e.pop("metadata"))
            declared = e.pop("path")
            e["file_exists"] = bool(declared and Path(declared).is_file())
            if e["file_exists"]:
                p = Path(declared)
                physical[e["sha256"]] = p.stat().st_size
            elif e["sha256"]:
                missing.append(e["id"])
            e["role"] = (
                meta.get("collection_role")
                if meta.get("collection_role")
                else "CATALOGUE RESPONSE"
                if meta.get("retrieval_method") == "Public research connector response"
                or "search response" in e["title"].lower()
                or "document inventory" in e["title"].lower()
                else "ORIGINAL ARTEFACT"
                if e["sha256"]
                else "SECONDARY NOTE"
            )
            e["file_url"] = (
                f"/api/evidence/{e['id']}/file" if e["file_exists"] else None
            )
            e["source_class"] = meta.get(
                "source_class",
                "PUBLIC WEB / USER IMPORT" if e["sha256"] else "SECONDARY",
            )
            records.append(e)
        free = shutil.disk_usage(core.ROOT)
        derivatives = sum(
            p.stat().st_size
            for p in (core.ROOT / "derivatives").rglob("*")
            if p.is_file() and not p.is_symlink()
        )
        return {
            "created": core.now(),
            "database_path": str(core.ROOT / "case.db"),
            "originals_path": str(core.ROOT / "originals"),
            "derivatives_path": str(core.ROOT / "derivatives"),
            "database_bytes": (core.ROOT / "case.db").stat().st_size,
            "wal_bytes": (core.ROOT / "case.db-wal").stat().st_size
            if (core.ROOT / "case.db-wal").exists()
            else 0,
            "original_files": len(physical),
            "original_bytes": sum(physical.values()),
            "derivative_bytes": derivatives,
            "missing_original_ids": missing,
            "disk_free_bytes": free.free,
            "vault_limit_bytes": core.MAX_VAULT_BYTES,
            "records": records,
            "acquisition_by_day": core.rows(
                "SELECT substr(created,1,10) day,count(*) records, sum(size) bytes FROM evidence WHERE sha256 IS NOT NULL GROUP BY day ORDER BY day"
            ),
            "jobs": core.rows("SELECT status,count(*) count FROM jobs GROUP BY status"),
            "heartbeats": [
                {
                    **h,
                    "data": json.loads(h["data"]),
                    "age_seconds": round(time.time() - h["updated"], 1),
                    "state": "ALIVE" if time.time() - h["updated"] < 90 else "STALE",
                }
                for h in core.rows("SELECT * FROM worker_heartbeats")
            ],
            "coverage": "Counts describe this vault, not every document or photograph on the internet. Catalogue bytes are separated from acquired source artefacts.",
            "tor": core.onion["status"](),
        }

    @core.app.get("/api/vault/catalogue")
    def catalogue(after: str = "", limit: int = 25):
        """Page source provenance without transferring full text and PDF extraction coordinates."""
        if not 1 <= limit <= 100 or len(after) > 100:
            raise core.HTTPException(
                422, "Use a page size of 1–100 and a bounded evidence cursor"
            )
        records = core.rows(
            "SELECT id,title,kind,status,url,sha256,size,created,metadata FROM evidence WHERE id>? ORDER BY id LIMIT ?",
            (after, limit),
        )
        for entry in records:
            metadata = json.loads(entry["metadata"])
            entry["metadata"] = {
                k: v
                for k, v in metadata.items()
                if k
                not in {
                    "pages",
                    "printable_strings",
                    "links",
                    "media",
                    "image_forensics",
                    "histogram",
                    "ocr",
                }
            }
            entry["metadata"]["full_extraction_record"] = f"/api/evidence/{entry['id']}"
        return {
            "records": records,
            "next_cursor": records[-1]["id"] if len(records) == limit else None,
            "scope": "Source provenance and extraction hashes; complete text/coordinates remain in the original vault and derivatives",
        }

    @core.app.get("/api/vault")
    def status():
        return {
            **inventory(),
            "snapshots": [
                json.loads(r["data"])
                for r in core.rows(
                    "SELECT data FROM vault_snapshots ORDER BY bucket DESC LIMIT 288"
                )
            ],
        }

    @core.app.get("/api/vault/manifest")
    def manifest():
        data = inventory()
        records = []
        for e in data["records"]:
            if e["file_exists"]:
                expected = e["sha256"]
                p = core.ROOT / "originals" / expected
                e["hash_matches"] = (
                    p.is_file()
                    and hashlib.sha256(p.read_bytes()).hexdigest() == expected
                )
            records.append(e)
        return {
            **data,
            "records": records,
            "verification": "Actual original-file SHA-256 checked; provenance verification is separate.",
        }

    @core.app.get("/api/vault/database")
    def database_snapshot():
        fd, name = tempfile.mkstemp(prefix="sherlock-case-", suffix=".sqlite")
        __import__("os").close(fd)
        path = Path(name)
        try:
            with core.lock, core.db() as source, sqlite3.connect(path) as dest:
                source.backup(dest)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return core.FileResponse(
            path,
            media_type="application/vnd.sqlite3",
            filename="looking-glass-case.sqlite",
            background=BackgroundTask(path.unlink, missing_ok=True),
        )

    def monitor():
        while not core.stopping.is_set():
            try:
                heartbeat("vault-monitor")
                data = inventory()
                snapshot = {
                    k: data[k]
                    for k in (
                        "created",
                        "original_files",
                        "original_bytes",
                        "derivative_bytes",
                        "database_bytes",
                        "disk_free_bytes",
                    )
                }
                core.execute(
                    "INSERT OR IGNORE INTO vault_snapshots VALUES(?,?,?)",
                    (int(time.time() // 300), core.now(), json.dumps(snapshot)),
                )
            except Exception as ex:
                core.log("vault_monitor_failed", {"reason": str(ex)[:500]})
            core.stopping.wait(30)

    @core.app.on_event("startup")
    def start():
        threading.Thread(target=monitor, name="vault-monitor", daemon=True).start()

    return {"inventory": inventory}
