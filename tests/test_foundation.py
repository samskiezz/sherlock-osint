"""Live Phase 1 API integration tests against PostgreSQL, Redis and the existing vault."""

import json
import secrets
import time
from pathlib import Path
import httpx
import pyotp
import pytest


@pytest.fixture(scope="module")
def live():
    c = httpx.Client(base_url="http://127.0.0.1:8010", trust_env=False, timeout=90)
    for _ in range(50):
        try:
            r = c.get("/health")
            r.raise_for_status()
            break
        except httpx.RequestError:
            time.sleep(0.2)
    else:
        pytest.skip(
            "Run the real PostgreSQL/Redis foundation before this integration suite"
        )
    assert r.json()["database_ready"] and r.json()["redis_ready"]
    credentials = json.loads(
        Path("data/foundation-secrets/admin-login.json").read_text()
    )
    response = c.post("/api/v1/auth/login", json=credentials)
    response.raise_for_status()
    admin = {"Authorization": "Bearer " + response.json()["access_token"]}
    users = {}
    for role in ("Viewer", "Analyst"):
        value = {
            "username": role.lower() + "-test-" + secrets.token_hex(4),
            "password": secrets.token_urlsafe(24),
            "role": role,
        }
        created = c.post("/api/v1/users", json=value, headers=admin)
        created.raise_for_status()
        login = c.post(
            "/api/v1/auth/login",
            json={"username": value["username"], "password": value["password"]},
        )
        login.raise_for_status()
        users[role] = {
            **value,
            "id": created.json()["id"],
            "header": {"Authorization": "Bearer " + login.json()["access_token"]},
        }
    try:
        yield c, admin, users
    finally:
        # These are fixture-owned accounts, never the operator's administrator.
        # Retire them even when an assertion fails; retain their audit history.
        from foundation.models import Session, User
        from foundation.audit import record
        with Session.begin() as session:
            retired = []
            for fixture in users.values():
                user = session.get(User, fixture["id"])
                if user is not None and user.username == fixture["username"]:
                    user.active = False
                    user.token_version += 1
                    retired.append(user.id)
            if retired:
                record(session, None, "test_accounts_retired", {"user_ids": retired})
        c.close()


def test_health_and_authentication_required(live):
    c, admin, users = live
    assert c.get("/health").json()["database"] == "postgresql"
    with httpx.Client(base_url=str(c.base_url), trust_env=False) as anonymous:
        assert anonymous.get("/api/v1/cases").status_code == 401
        assert anonymous.get("/api/evidence").status_code == 401
        assert "Authenticated evidence workspace" in anonymous.get("/").text
    assert c.get("/api/v1/users/me", headers=admin).json()["role"] == "Admin"
    assert (
        c.get("/api/v1/cases", headers=users["Viewer"]["header"]).json()[0]["id"]
        == "PROJECT-LOOKING-GLASS"
    )


def test_users_roles_input_validation_and_export_access(live):
    c, admin, users = live
    viewer = users["Viewer"]["header"]
    assert (
        c.post(
            "/api/v1/users",
            headers=viewer,
            json={
                "username": "deny",
                "password": "A-long-owned-test-pass",
                "role": "Admin",
            },
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/v1/users",
            headers=admin,
            json={"username": "bad", "password": "short", "role": "Root"},
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/v1/collect",
            headers=viewer,
            json={
                "username": "sherlock-project",
                "authorisation": "Public project research",
            },
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/v1/collect",
            headers=admin,
            json={
                "username": "../../private",
                "authorisation": "Public project research",
            },
        ).status_code
        == 422
    )
    assert c.get("/api/v1/evidence", headers=viewer).json()
    system = c.get("/api/v1/system", headers=viewer).json()
    assert system["database"] == "PostgreSQL" and system["metadata_records"] > 0
    assert "DATABASE_URL" not in system
    report = c.post("/api/v1/report", headers=viewer, json={"format": "pdf"})
    assert report.status_code == 200 and report.content.startswith(b"%PDF")
    assert (
        c.post("/api/v1/report", headers=viewer, json={"format": "shell"}).status_code
        == 422
    )
    assert c.get("/api/v1/audit/verify", headers=viewer).status_code == 403


def test_source_verified_graph_and_investigator_routes(live):
    c, admin, users = live
    boards = c.get("/api/boards", headers=admin).json()
    bid = next(b["id"] for b in boards if "named primary record" in b["name"])
    graph = c.get(
        "/api/v1/graph", headers=users["Viewer"]["header"], params={"board_id": bid}
    )
    assert graph.status_code == 200 and all(
        e["citation_verified"] for e in graph.json()["edges"]
    )
    assert (
        c.get(
            "/api/v1/graph", headers=admin, params={"board_id": "BOARD-MISSING"}
        ).status_code
        == 404
    )
    request = {
        "question": "Which exact names appear in the acquired 2016 Caltech caption?",
        "evidence_ids": ["EV-32234078df6a"],
    }
    assert (
        c.post(
            "/api/v1/analyze", headers=users["Viewer"]["header"], json=request
        ).status_code
        == 403
    )
    result = c.post("/api/v1/analyze", headers=users["Analyst"]["header"], json=request)
    assert result.status_code == 202 and result.json()["id"]


def test_persistent_celery_job_actual_original_and_ownership_not_assumed(live):
    c, admin, users = live
    queued = c.post(
        "/api/v1/collect",
        headers=users["Analyst"]["header"],
        json={
            "username": "sherlock-project",
            "authorisation": "Official public software project profile for source-backed integration test",
        },
    )
    assert queued.status_code == 202
    jid = queued.json()["id"]
    for _ in range(90):
        result = c.get("/api/v1/collect/" + jid, headers=admin).json()
        if result["status"] in ("COMPLETE", "FAILED"):
            break
        time.sleep(1)
    assert result["status"] == "COMPLETE", result
    e = c.get(
        "/api/evidence/" + result["result"]["original_evidence_id"], headers=admin
    ).json()
    assert e["sha256"] == result["result"]["sha256"]
    assert e["metadata"]["original_url"] == "https://github.com/sherlock-project"
    assert "UNVERIFIED ATTRIBUTION" in result["result"]["attribution"]
    assert c.get("/api/v1/collect/JOB-MISSING", headers=admin).status_code == 404


def test_totp_confirmation_replay_and_logout_revocation(live):
    c, admin, users = live
    u = users["Viewer"]
    header = u["header"]
    response = c.post("/api/v1/auth/totp/enroll", headers=header)
    assert response.status_code == 200
    seed = response.json()["secret"]
    code = pyotp.TOTP(seed).now()
    assert (
        c.post(
            "/api/v1/auth/totp/confirm", headers=header, json={"code": "000000"}
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/v1/auth/totp/confirm", headers=header, json={"code": code}
        ).status_code
        == 200
    )
    assert c.get("/api/v1/users/me", headers=header).status_code == 401
    credentials = {"username": u["username"], "password": u["password"]}
    assert c.post("/api/v1/auth/login", json=credentials).status_code == 401
    assert (
        c.post("/api/v1/auth/login", json={**credentials, "totp": code}).status_code
        == 401
    )
    next_code = pyotp.TOTP(seed).at(int(time.time()) + 30)
    login = c.post("/api/v1/auth/login", json={**credentials, "totp": next_code})
    assert login.status_code == 200
    assert (
        c.post(
            "/api/v1/auth/login", json={**credentials, "totp": next_code}
        ).status_code
        == 401
    )
    access = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert c.post("/api/v1/auth/logout", headers=access).status_code == 200
    assert c.get("/api/v1/users/me", headers=access).status_code == 401


def test_gateway_audit_hashes_and_private_auth_fields(live):
    c, admin, users = live
    result = c.get("/api/v1/audit/verify", headers=admin).json()
    assert result["valid"] and result["events"] > 0
    payload = json.dumps(c.get("/api/v1/evidence", headers=admin).json())
    assert (
        users["Analyst"]["password"] not in payload and "password_hash" not in payload
    )


def test_internal_bridge_requires_token_and_preserves_original_bytes(live):
    from foundation import config
    import hashlib

    with httpx.Client(
        base_url="http://172.17.0.1:8001", trust_env=False, timeout=30
    ) as c:
        assert c.get("/api/health").status_code == 401
        assert (
            c.get("/api/health", headers=config.CORE_HEADERS).json()["status"] == "ok"
        )
        original = c.get(
            "/api/evidence/EV-3320197e1e71", headers=config.CORE_HEADERS
        ).json()
        response = c.get(original["fileUrl"], headers=config.CORE_HEADERS)
        assert (
            response.status_code == 200
            and hashlib.sha256(response.content).hexdigest() == original["sha256"]
        )
