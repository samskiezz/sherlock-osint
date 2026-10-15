"""Provision a local administrator and synchronise actual evidence metadata into PostgreSQL."""

import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from foundation.models import Session, User, Evidence, Entity, migrate
from foundation.security import passwords
from foundation.audit import record

migrate()
root = Path(__file__).resolve().parents[1]
credentials = root / "data/foundation-secrets/admin-login.json"
with Session.begin() as s:
    if not s.get(User, "LOCAL-ADMIN"):
        password = secrets.token_urlsafe(24)
        s.add(
            User(
                id="LOCAL-ADMIN",
                username="admin",
                password_hash=passwords.hash(password),
                role="Admin",
            )
        )
        credentials.write_text(json.dumps({"username": "admin", "password": password}))
        credentials.chmod(0o600)
        record(
            s,
            "LOCAL-ADMIN",
            "administrator_bootstrapped",
            {"credentials_path": str(credentials), "password_logged": False},
        )
with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=60) as c:
    response = c.get("/api/evidence")
    response.raise_for_status()
    evidence = response.json()
with Session.begin() as s:
    for e in evidence:
        value = s.get(Evidence, e["id"])
        if not value:
            value = Evidence(id=e["id"], case_id="PROJECT-LOOKING-GLASS")
            s.add(value)
        value.title = e["title"]
        value.status = e["status"]
        value.sha256 = e["sha256"]
        value.source_url = e["url"]
        value.byte_size = e["size"] or 0
        value.provenance = e["metadata"]
        if e["kind"] in ("person", "organisation", "event") and not s.get(
            Entity, e["id"]
        ):
            s.add(
                Entity(
                    id=e["id"],
                    case_id="PROJECT-LOOKING-GLASS",
                    kind=e["kind"],
                    name=e["title"],
                    data={
                        "attribution": "Source-specific imported record; no identity merge",
                        "source_evidence_id": e["id"],
                    },
                )
            )
    record(
        s,
        "LOCAL-ADMIN",
        "evidence_metadata_imported",
        {"records": len(evidence), "original_bytes_moved": False},
    )
print(
    json.dumps(
        {
            "database": "PostgreSQL",
            "metadata_records_imported": len(evidence),
            "local_admin_credentials_file": str(credentials),
            "credentials_printed": False,
        }
    )
)
