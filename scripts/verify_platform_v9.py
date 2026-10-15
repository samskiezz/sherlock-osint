"""Exercise real store/container restarts, source integrity, query persistence and supervision."""

import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
from collections import Counter

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.sandbox import command
from backend.retrieval import Services, COLLECTION, INDEX
from foundation.models import Session, CollectionJob, User
from foundation.audit import verify
from sqlalchemy import select

root = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8010", trust_env=False, timeout=120)


def wait_health():
    """Wait with short bounded probes while the actual services recover."""
    for _ in range(120):
        try:
            r = c.get("/health", timeout=3)
            if r.status_code == 200 and r.json()["status"] == "ok":
                return r.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError("Gateway/database/broker did not recover")


def login():
    """Read local administrator credentials in memory without exporting them."""
    r = c.post(
        "/api/v1/auth/login",
        json=json.loads(
            (root / "data/foundation-secrets/admin-login.json").read_text()
        ),
    )
    r.raise_for_status()
    c.headers["Authorization"] = "Bearer " + r.json()["access_token"]


wait_health()
login()
# Prefer the named primary PDF; other completed originals remain searchable too.
for _ in range(120):
    current = c.get("/api/knowledge/status").json()
    response = c.post(
        "/api/knowledge/search",
        json={"query": "Blitzkrieg Bots Cole Allen", "mode": "hybrid", "limit": 20},
    )
    response.raise_for_status()
    answer = response.json()
    if any(
        h["evidence_id"] == "EV-32234078df6a" and h["page"] == 11
        for h in answer["results"]
    ):
        break
    c.post(
        "/api/knowledge/index", json={"evidence_id": "EV-32234078df6a"}
    ).raise_for_status()
    time.sleep(0.5)
else:
    raise RuntimeError("Primary page-11 PDF was not indexed")
query_id = answer["id"]
board = next(
    b for b in c.get("/api/boards").json() if "named primary record" in b["name"]
)
before_board = c.get("/api/boards/" + board["id"]).json()
with Session() as db:
    users = [
        (u.id, u.password_hash, u.totp_seed, u.totp_enabled, u.token_version)
        for u in db.scalars(select(User))
    ]
    completed_jobs = [
        (j.id, j.status, j.result)
        for j in db.scalars(select(CollectionJob))
        if j.status in ("COMPLETE", "FAILED")
    ]
    assert verify(db)["valid"]
s = Services(root / "data")
counts_before = {
    "qdrant": s.q("GET", f"/collections/{COLLECTION}")["result"]["points_count"],
    "elasticsearch": s.es("GET", "/" + INDEX + "/_count")["count"],
}
s.close()
# Stop and restart the actual durable infrastructure, not simulated clients.
command(
    [
        "restart",
        "--time",
        "10",
        "sherlock-foundation-postgres-1",
        "sherlock-foundation-redis-1",
        "sherlock-foundation-qdrant-1",
        "sherlock-foundation-elasticsearch-1",
    ],
    timeout=120,
)
wait_health()
command(
    [
        "restart",
        "--time",
        "10",
        "sherlock-foundation-api-1",
        "sherlock-foundation-worker-1",
    ],
    timeout=60,
)
wait_health()
login()
s = Services(root / "data")
for _ in range(200):
    try:
        s.ensure()
        counts_after = {
            "qdrant": s.q("GET", f"/collections/{COLLECTION}")["result"][
                "points_count"
            ],
            "elasticsearch": s.es("GET", "/" + INDEX + "/_count")["count"],
        }
        break
    except Exception:
        time.sleep(0.5)
else:
    raise RuntimeError("Vector/BM25 stores did not recover")
s.close()
assert all(counts_after[k] >= counts_before[k] for k in counts_before)
# Supervisor recovers both owned processes without manually launching replacements.
recovery = {}
for service, pidfile, marker in [
    ("core", "service-v2.pid", "backend.app:app"),
    ("bridge", "foundation-bridge.pid", "foundation.bridge:app"),
]:
    path = root / "data" / pidfile
    old = int(path.read_text())
    assert marker in Path(f"/proc/{old}/cmdline").read_text()
    os.kill(old, signal.SIGTERM)
    for _ in range(200):
        time.sleep(0.25)
        if path.exists() and int(path.read_text()) != old:
            try:
                response = c.get("/api/evidence", timeout=3)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
    else:
        raise RuntimeError("Supervisor failed to restore " + service)
    recovery[service] = {
        "old_pid": old,
        "new_pid": int(path.read_text()),
        "automatic_recovery": True,
    }
record = c.get("/api/knowledge/queries/" + query_id)
record.raise_for_status()
assert record.json() == answer
assert c.get("/api/boards/" + board["id"]).json() == before_board
with Session() as db:
    for uid, password, seed, enabled, version in users:
        u = db.get(User, uid)
        assert (u.password_hash, u.totp_seed, u.totp_enabled, u.token_version) == (
            password,
            seed,
            enabled,
            version,
        )
    for jid, status, result in completed_jobs:
        j = db.get(CollectionJob, jid)
        assert (j.status, j.result) == (status, result)
    audit = verify(db)
    assert audit["valid"]
manifest = c.get("/api/vault/manifest").json()
originals = [r for r in manifest["records"] if r["file_exists"]]
assert originals and all(r["hash_matches"] for r in originals)
for e in originals:
    assert not ((root / "data/originals" / e["sha256"]).stat().st_mode & 0o222)
assert not manifest["missing_original_ids"]
methods = c.get("/api/tradecraft").json()["methods"]
core_audit = c.get("/api/audit/verify").json()
assert core_audit["valid"]
proof = {
    "gateway": "http://127.0.0.1:8010",
    "health": wait_health(),
    "actual_containers_restarted": [
        "postgres",
        "redis",
        "qdrant",
        "elasticsearch",
        "api",
        "worker",
    ],
    "index_counts_before": counts_before,
    "index_counts_after": counts_after,
    "saved_query_retained": query_id,
    "named_primary_pdf_page_11_retrieved": True,
    "source_board_persisted": True,
    "supervisor_automatic_recovery": recovery,
    "users_and_mfa_states_retained": len(users),
    "terminal_collection_jobs_retained": len(completed_jobs),
    "read_only_original_files_sha256_verified": len(originals),
    "original_bytes": sum(e["size"] for e in originals),
    "disk_free_bytes": manifest["disk_free_bytes"],
    "method_counts": dict(Counter(m["implementation"] for m in methods)),
    "core_audit_valid": core_audit["valid"],
    "postgres_audit_valid": audit["valid"],
    "tor": {
        "reachable": manifest["tor"].get("reachable", False),
        "note": "No successful onion acquisition claimed; environment has no TCP grants",
    },
    "mac_installed_or_tested": False,
    "credentials_exported": False,
}
(root / "artifacts/platform-restart-proof-v9.json").write_text(
    json.dumps(proof, indent=2)
)
print(json.dumps(proof, indent=2))
