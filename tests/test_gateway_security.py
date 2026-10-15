"""Bounded adversarial checks using an owned Postgres DB and Redis key namespace.

No credential guesses are sent to the running gateway or any external host.
Each module invocation owns and removes its temporary database and limiter keys.
"""
import base64
import json
import random
import secrets
import sys
import time
import uuid

import psycopg
from psycopg import sql
import pytest
import redis
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from urllib.parse import urlsplit, urlunsplit


@pytest.fixture(scope="module")
def isolated_gateway():
    assert "foundation.models" not in sys.modules, "Run this module in a fresh process"
    from foundation import config
    administrator = config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    name = "sherlock_security_" + uuid.uuid4().hex[:12]
    with psycopg.connect(administrator, autocommit=True) as db:
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    parts = urlsplit(config.DATABASE_URL)
    database_url = urlunsplit(parts._replace(path="/" + name))
    prefix = "sherlock-owned-security:" + uuid.uuid4().hex + ":"
    underlying = None
    models = None
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(config, "DATABASE_URL", database_url)
            patch.setattr(config, "SECRET", secrets.token_urlsafe(48))
            patch.setattr(config, "TOTP_KEY", Fernet.generate_key().decode())
            patch.setattr(config, "SECURE_COOKIES", True)
            patch.setattr(config, "CORE_URL", "http://127.0.0.1:1")
            from foundation import app as gateway, models, security, sync
            underlying = gateway.broker
            assert underlying.ping(), "Real Redis is required for the limiter checks"

            class ScopedBroker:
                failed = False
                def check(self):
                    if self.failed:
                        raise redis.ConnectionError("Owned limiter-outage fixture")
                def incr(self, key):
                    self.check()
                    return underlying.incr(prefix + key)
                def expire(self, key, ttl):
                    self.check()
                    return underlying.expire(prefix + key, ttl)
                def ping(self):
                    self.check()
                    return underlying.ping()
                def clear(self):
                    keys = list(underlying.scan_iter(match=prefix + "*"))
                    if keys:
                        underlying.delete(*keys)
            scoped = ScopedBroker()
            patch.setattr(gateway, "broker", scoped)
            patch.setattr(gateway, "dispatch", lambda: None)
            patch.setattr(sync, "synchronize", lambda: None)
            models.migrate()
            accounts = {}
            with models.Session.begin() as session:
                for role in ("Admin", "Viewer"):
                    password = secrets.token_urlsafe(24)
                    user = models.User(id="USER-" + uuid.uuid4().hex,
                        username="owned-" + role.lower(), role=role,
                        password_hash=security.passwords.hash(password))
                    session.add(user)
                    accounts[role] = {"id": user.id, "username": user.username, "password": password}
            yield gateway, models, security, scoped, accounts
            scoped.clear()
    finally:
        if underlying is not None:
            keys = list(underlying.scan_iter(match=prefix + "*"))
            if keys:
                underlying.delete(*keys)
            underlying.close()
        if models is not None:
            models.engine.dispose()
        with psycopg.connect(administrator, autocommit=True) as db:
            db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def client(isolated_gateway):
    gateway, _, _, broker, _ = isolated_gateway
    broker.failed = False
    broker.clear()
    with TestClient(gateway.app, base_url="https://owned.test",
                    client=("192.0.2.10", 42000)) as test_client:
        yield test_client
    broker.failed = False
    broker.clear()


def login(client, accounts, role="Admin"):
    account = accounts[role]
    response = client.post("/api/v1/auth/login", json={key: account[key] for key in ("username", "password")})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_account_guessing_is_limited_and_forwarded_ips_do_not_bypass(client, isolated_gateway):
    account = isolated_gateway[-1]["Viewer"]
    statuses = [client.post("/api/v1/auth/login",
        json={"username": account["username"], "password": "owned-wrong-guess-" + str(i)},
        headers={"X-Forwarded-For": f"192.0.2.{i + 20}"}).status_code for i in range(10)]
    assert statuses == [401] * 5 + [429] * 5
    assert client.post("/api/v1/auth/login", json={key: account[key] for key in ("username", "password")}).status_code == 429


def test_rotating_account_names_does_not_bypass_ip_limiter(client):
    statuses = [client.post("/api/v1/auth/login",
        json={"username": f"owned-absent-{i}", "password": "owned-wrong-password"},
        headers={"X-Forwarded-For": f"192.0.2.{i + 20}"}).status_code for i in range(22)]
    assert statuses == [401] * 20 + [429] * 2


def test_gateway_budget_blocks_the_601st_unauthenticated_request(client):
    statuses = [client.get("/api/v1/users/me").status_code for _ in range(605)]
    assert statuses == [401] * 600 + [429] * 5
    assert client.get("/health").status_code == 200


def test_secure_cookie_logout_and_old_bearer_revocation(client, isolated_gateway):
    token = login(client, isolated_gateway[-1])
    cookie = client.cookies.get("sherlock_access")
    assert cookie == token
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    stored = next(c for c in client.cookies.jar if c.name == "sherlock_access")
    assert stored.secure and stored.has_nonstandard_attr("HttpOnly")
    assert stored.get_nonstandard_attr("SameSite").lower() == "strict"
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_bounded_jwt_mutation_corpus_rejects_bad_signatures_claims_and_algorithms(client, isolated_gateway):
    _, _, security, _, accounts = isolated_gateway
    subject = accounts["Viewer"]["id"]
    claims = {"sub": subject, "ver": 0, "iat": int(time.time()), "exp": int(time.time()) + 900,
              "iss": "sherlock-foundation", "aud": "sherlock-gateway"}
    corpus = ["", ".", "..", "not-a-token", "a.b.c"]
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
    corpus.append(encode({"alg": "none"}) + "." + encode(claims) + ".")
    for change in ({"aud": "wrong"}, {"iss": "wrong"}, {"exp": 1}, {"sub": "absent"}, {"ver": 999}):
        corpus.append(security.jwt.encode({"alg": "HS256"}, dict(claims, **change), security.config.SECRET).decode())
    corpus.append(security.jwt.encode({"alg": "HS256"}, claims, "owned-wrong-signing-key" * 2).decode())
    rng = random.Random(429072)
    for _ in range(128):
        corpus.append(base64.urlsafe_b64encode(rng.randbytes(rng.randrange(1, 192))).decode())
    for token in corpus:
        assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_viewer_headers_cannot_assign_admin_privileges_and_disabled_tokens_fail(client, isolated_gateway):
    _, models, _, _, accounts = isolated_gateway
    token = login(client, accounts, "Viewer")
    headers = {"Authorization": "Bearer " + token, "X-Sherlock-Erps-Role": "Admin", "X-Role": "Admin"}
    assert client.post("/api/v1/users", headers=headers,
        json={"username": "owned-denied", "password": "owned-long-fixture-password", "role": "Admin"}).status_code == 403
    assert client.post("/api/erps/deletion", headers=headers, json={"source_var": str(uuid.uuid4())}).status_code == 403
    with models.Session.begin() as session:
        session.get(models.User, accounts["Viewer"]["id"]).active = False
    try:
        assert client.get("/api/v1/users/me", headers=headers).status_code == 401
    finally:
        with models.Session.begin() as session:
            session.get(models.User, accounts["Viewer"]["id"]).active = True


def test_cross_origin_writes_and_bad_lengths_are_rejected(client, isolated_gateway):
    token = login(client, isolated_gateway[-1])
    headers = {"Authorization": "Bearer " + token, "Origin": "https://untrusted.invalid"}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 403
    assert client.get("/api/v1/users/me").status_code == 200
    assert client.post("/api/v1/auth/login", content="{}", headers={"Content-Length": str(27 * 1024**2)}).status_code == 413
    assert client.post("/api/v1/auth/login", content="{}", headers={"Content-Length": "invalid"}).status_code == 413


def test_authentication_fails_closed_when_limiter_is_unavailable(client, isolated_gateway):
    broker = isolated_gateway[3]
    token = login(client, isolated_gateway[-1])
    broker.failed = True
    try:
        assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + token}).status_code == 503
    finally:
        broker.failed = False
    assert client.get("/api/v1/users/me").status_code == 200


def test_authentication_audit_contains_no_passwords_or_tokens(client, isolated_gateway):
    _, models, _, _, accounts = isolated_gateway
    token = login(client, accounts)
    from sqlalchemy import select
    from foundation.audit import verify
    with models.Session() as session:
        data = json.dumps([row.detail for row in session.scalars(select(models.AuditLog))])
        assert all(value["password"] not in data for value in accounts.values())
        assert token not in data
        assert verify(session)["valid"]
