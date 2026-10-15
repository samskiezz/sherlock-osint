"""Verify real gateway/worker and database/broker restarts retain users, jobs and original references."""

import json
import os
import signal
import subprocess
import time
from pathlib import Path
import httpx
from sqlalchemy import select
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundation.models import Session, User, CollectionJob, Evidence
from foundation.audit import verify

root = Path(__file__).resolve().parents[1]
with Session() as s:
    before = {
        "users": [
            (u.id, u.password_hash, u.totp_seed, u.totp_enabled, u.token_version)
            for u in s.scalars(select(User))
        ],
        "jobs": [(j.id, j.status, j.result) for j in s.scalars(select(CollectionJob))],
        "evidence": [(e.id, e.sha256) for e in s.scalars(select(Evidence))],
    }
    assert verify(s)["valid"]
for name in ("gateway", "worker", "bridge"):
    p = root / f"data/foundation-{name}.pid"
    pid = int(p.read_text())
    args = subprocess.check_output(["ps", "-p", str(pid), "-o", "args="], text=True)
    expected = {
        "gateway": "foundation.app:app",
        "worker": "foundation.tasks:celery",
        "bridge": "foundation.bridge:app",
    }[name]
    assert expected in args
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            break
    p.unlink()
base = [
    "env",
    "-u",
    "DOCKER_HOST",
    "-u",
    "DOCKER_CONTEXT",
    "-u",
    "DOCKER_TLS",
    "-u",
    "DOCKER_TLS_VERIFY",
    "-u",
    "DOCKER_CERT_PATH",
    "docker",
    "--host=unix:///var/run/docker.sock",
]
subprocess.run(
    base
    + [
        "compose",
        "--env-file",
        "data/foundation-compose.env",
        "-f",
        "compose.foundation.yml",
        "restart",
        "postgres",
        "redis",
    ],
    cwd=root,
    check=True,
    stdout=subprocess.DEVNULL,
)
for _ in range(60):
    try:
        with Session() as s:
            s.execute(__import__("sqlalchemy").text("SELECT 1"))
        break
    except Exception:
        time.sleep(0.2)
else:
    raise RuntimeError("PostgreSQL did not recover")
subprocess.run(
    [str(root / ".venv/bin/python"), str(root / "scripts/run_foundation.py")],
    cwd=root,
    check=True,
    stdout=subprocess.DEVNULL,
)
with httpx.Client(base_url="http://127.0.0.1:8010", trust_env=False, timeout=30) as c:
    for _ in range(60):
        try:
            health = c.get("/health").json()
            if health["database_ready"] and health["redis_ready"]:
                break
        except httpx.RequestError:
            pass
        time.sleep(0.2)
    else:
        raise RuntimeError("Gateway did not recover")
with Session() as s:
    for uid, password_hash, seed, enabled, version in before["users"]:
        user = s.get(User, uid)
        assert user and (
            user.password_hash,
            user.totp_seed,
            user.totp_enabled,
            user.token_version,
        ) == (password_hash, seed, enabled, version)
    for jid, status, result in before["jobs"]:
        job = s.get(CollectionJob, jid)
        assert job and (job.status, job.result) == (status, result)
    for eid, digest in before["evidence"]:
        assert s.get(Evidence, eid).sha256 == digest
    audit = verify(s)
    assert audit["valid"]
proof = {
    "actual_postgresql_and_redis_restart": True,
    "actual_gateway_worker_bridge_restart": True,
    "users_retained": len(before["users"]),
    "completed_and_failed_jobs_retained": len(before["jobs"]),
    "evidence_references_retained": len(before["evidence"]),
    "mfa_encryption_and_revocation_versions_retained": True,
    "postgres_audit_chain_valid": audit["valid"],
    "health": health,
    "secrets_exported": False,
}
(root / "artifacts/foundation-restart-v8.json").write_text(json.dumps(proof, indent=2))
print(json.dumps(proof, indent=2))
