"""Authenticated gateway and versioned API, backed by actual PostgreSQL and Redis services."""

import asyncio
import hashlib
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
import httpx
import pyotp
import redis
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select, text
from . import config
from .models import (
    Session,
    User,
    Case,
    Evidence,
    Entity,
    CollectionJob,
    engine,
    migrate,
)
from .audit import record, verify
from .security import (
    passwords,
    issue,
    authenticate,
    require,
    check_password,
    check_totp,
)
from .tasks import dispatch

broker = redis.Redis.from_url(config.BROKER, decode_responses=True, socket_timeout=2)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Apply migrations and continuously dispatch durable collection outbox records."""
    if len(config.SECRET) < 32 or not config.TOTP_KEY:
        raise RuntimeError("Private signing/encryption keys must be configured")
    migrate()
    stop = asyncio.Event()

    async def dispatcher() -> None:
        """Retry broker dispatch without discarding pending database jobs."""
        last_sync = 0.0
        while not stop.is_set():
            try:
                await asyncio.to_thread(dispatch)
                if time.monotonic() - last_sync >= 30:
                    from .sync import synchronize

                    await asyncio.to_thread(synchronize)
                    last_sync = time.monotonic()
            except Exception:
                app.state.dispatcher_error = "BROKER OR DATABASE UNAVAILABLE"
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass

    task = asyncio.create_task(dispatcher())
    yield
    stop.set()
    await task


app = FastAPI(
    title="SHERLOCK OSINT authenticated foundation", version="0.10.0", lifespan=lifespan
)


@app.middleware("http")
async def access_log(request: Request, call_next: Any) -> Response:
    """Rate-limit access, prevent cross-origin writes, and hash-chain request metadata only."""
    length = request.headers.get("content-length", "0")
    if not length.isdigit() or int(length) > 26 * 1024 * 1024:
        return Response("Request exceeds 26 MiB gateway limit", status_code=413)
    if request.url.path != "/health":
        client_key = (
            "gateway-ip:"
            + hashlib.sha256(
                (request.client.host if request.client else "unknown").encode()
            ).hexdigest()
        )
        try:
            number = await asyncio.to_thread(broker.incr, client_key)
            if number == 1:
                await asyncio.to_thread(broker.expire, client_key, 60)
            if number > 600:
                return Response("Gateway rate limit exceeded", status_code=429)
        except redis.RedisError:
            return Response("Gateway limiter unavailable", status_code=503)
    origin = request.headers.get("origin")
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin.rstrip("/") != str(request.base_url).rstrip("/")
    ):
        response = Response("Cross-origin writes prohibited", status_code=403)
    else:
        response = await call_next(request)
    if request.url.path != "/health":
        with Session.begin() as s:
            record(
                s,
                getattr(request.state, "actor_id", None),
                "api_access",
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                },
            )
    return response


class Login(BaseModel):
    """Local account credentials; secrets are never stored in audit details."""

    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=256)
    totp: str = Field(default="", max_length=6)


class NewUser(BaseModel):
    """Administrator-provisioned role and password."""

    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    password: SecretStr = Field(min_length=12, max_length=256)
    role: str = Field(pattern=r"^(Admin|Analyst|Viewer)$")


class Collect(BaseModel):
    """Explicit single-username public-source collection request."""

    username: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,38}$")
    case_id: str = "PROJECT-LOOKING-GLASS"
    authorisation: str = Field(min_length=10, max_length=1000)


class Analyze(BaseModel):
    """Evidence-backed task delegated to the existing investigator."""

    question: str = Field(min_length=5, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class Report(BaseModel):
    """Explicit local report format."""

    format: str = Field(default="pdf", pattern=r"^(pdf|docx|json|csv)$")


@app.get("/health")
def health() -> dict[str, Any]:
    """Report independently observed database and broker readiness without secrets."""
    db = queue = False
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
            db = True
    except Exception:
        pass
    try:
        queue = bool(broker.ping())
    except redis.RedisError:
        pass
    return {
        "status": "ok" if db and queue else "degraded",
        "version": "0.10.0",
        "database": engine.dialect.name,
        "database_ready": db,
        "redis_ready": queue,
    }


@app.post("/api/v1/auth/login")
def login(value: Login, request: Request, response: Response) -> dict[str, Any]:
    """Authenticate with rate limiting and optional, replay-resistant second factor."""
    ip_key = (
        "login-ip:"
        + hashlib.sha256(
            (request.client.host if request.client else "unknown").encode()
        ).hexdigest()
    )
    try:
        ip_count = broker.incr(ip_key)
        if ip_count == 1:
            broker.expire(ip_key, 60)
        if ip_count > 20:
            raise HTTPException(429, "Login rate limit exceeded")
    except redis.RedisError as ex:
        raise HTTPException(503, "Authentication limiter unavailable") from ex
    key = (
        "login:"
        + hashlib.sha256(
            (
                (request.client.host if request.client else "unknown")
                + "|"
                + value.username.lower()
            ).encode()
        ).hexdigest()
    )
    try:
        count = broker.incr(key)
        if count == 1:
            broker.expire(key, 60)
        if count > 5:
            raise HTTPException(429, "Login rate limit exceeded")
    except redis.RedisError as ex:
        raise HTTPException(503, "Authentication limiter unavailable") from ex
    with Session.begin() as s:
        user = s.execute(
            select(User).where(User.username == value.username).with_for_update()
        ).scalar_one_or_none()
        valid = (
            check_password(user, value.password.get_secret_value()) and user.active
            if user
            else check_password(None, value.password.get_secret_value())
        )
        if not valid or (user.totp_enabled and not check_totp(user, value.totp)):
            record(
                s,
                None,
                "login_denied",
                {"account_hash": hashlib.sha256(value.username.encode()).hexdigest()},
            )
            # Commit failed-login audit event before returning an error.
            s.commit()
            raise HTTPException(401, "Invalid credentials or second factor")
        token = issue(user)
        record(s, user.id, "login_success", {"role": user.role})
    response.set_cookie(
        "sherlock_access",
        token,
        httponly=True,
        samesite="strict",
        secure=config.SECURE_COOKIES,
        max_age=900,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 900,
        "role": user.role,
    }


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    """Revoke all existing tokens for the current account and clear the browser cookie."""
    user = authenticate(request)
    with Session.begin() as s:
        current = s.execute(
            select(User).where(User.id == user.id).with_for_update()
        ).scalar_one()
        current.token_version += 1
        record(s, user.id, "logout", {})
    response.delete_cookie("sherlock_access")
    return {"logged_out": True}


@app.get("/api/v1/users/me")
def me(request: Request) -> dict[str, Any]:
    """Expose only the current account's nonsensitive role and MFA state."""
    u = authenticate(request)
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "totp_enabled": u.totp_enabled,
    }


@app.post("/api/v1/users")
def create_user(value: NewUser, request: Request) -> dict[str, str]:
    """Create a provisioned account; only an administrator can assign roles."""
    admin = require(request, "users", "write")
    with Session.begin() as s:
        if s.scalar(select(User).where(User.username == value.username)):
            raise HTTPException(409, "Username already exists")
        user = User(
            id="USER-" + uuid.uuid4().hex,
            username=value.username,
            password_hash=passwords.hash(value.password.get_secret_value()),
            role=value.role,
        )
        s.add(user)
        record(s, admin.id, "user_created", {"user_id": user.id, "role": user.role})
    return {"id": user.id, "username": user.username, "role": user.role}


@app.post("/api/v1/auth/totp/enroll")
def enroll(request: Request) -> dict[str, str]:
    """Generate an encrypted pending seed; do not disable an existing second factor."""
    user = authenticate(request)
    with Session.begin() as s:
        current = s.get(User, user.id)
        if current.totp_enabled:
            raise HTTPException(409, "Second factor already enabled")
        seed = pyotp.random_base32()
        current.totp_seed = (
            Fernet(config.TOTP_KEY.encode()).encrypt(seed.encode()).decode()
        )
        current.totp_last_counter = -1
        record(s, user.id, "totp_enrollment_started", {})
    return {
        "secret": seed,
        "provisioning_uri": pyotp.TOTP(seed).provisioning_uri(
            user.username, issuer_name="SHERLOCK OSINT"
        ),
    }


class TotpCode(BaseModel):
    """Second-factor confirmation, never written to audit logs."""

    code: str = Field(pattern=r"^\d{6}$")


@app.post("/api/v1/auth/totp/confirm")
def confirm(value: TotpCode, request: Request) -> dict[str, bool]:
    """Enable MFA after a valid code and revoke previous single-factor tokens."""
    user = authenticate(request)
    with Session.begin() as s:
        current = s.execute(
            select(User).where(User.id == user.id).with_for_update()
        ).scalar_one()
        if not check_totp(current, value.code):
            raise HTTPException(
                422, "Invalid or previously consumed second-factor code"
            )
        current.totp_enabled = True
        current.token_version += 1
        record(s, user.id, "totp_enabled", {})
    return {"totp_enabled": True}


@app.get("/api/v1/cases")
def cases(request: Request) -> list[dict[str, str]]:
    """List persistent cases for an authorised reader."""
    require(request, "case", "read")
    with Session() as s:
        return [{"id": x.id, "name": x.name} for x in s.scalars(select(Case))]


@app.post("/api/v1/collect", status_code=202)
def collect(value: Collect, request: Request) -> dict[str, str]:
    """Commit a collection outbox record before attempting broker dispatch."""
    user = require(request, "collection", "write")
    with Session.begin() as s:
        if not s.get(Case, value.case_id):
            raise HTTPException(404, "Case not found")
        job = CollectionJob(
            id="JOB-" + uuid.uuid4().hex,
            username=value.username,
            case_id=value.case_id,
            authorisation=value.authorisation,
        )
        s.add(job)
        record(
            s,
            user.id,
            "collection_queued",
            {
                "id": job.id,
                "username": value.username,
                "site_budget": 1,
                "authorisation": value.authorisation,
            },
        )
    return {
        "id": job.id,
        "status": "QUEUED",
        "adapter": "Sherlock 0.16.2 · one public GitHub profile",
    }


@app.get("/api/v1/collect/{job_id}")
def job(job_id: str, request: Request) -> dict[str, Any]:
    """Inspect persistent execution results and explicit acquisition failures."""
    require(request, "collection", "read")
    with Session() as s:
        j = s.get(CollectionJob, job_id)
        if not j:
            raise HTTPException(404, "Collection job missing")
        return {"id": j.id, "status": j.status, "result": j.result, "error": j.error}


def core_json(response: httpx.Response) -> dict[str, Any]:
    """Preserve upstream failure status without exposing internal request details."""
    if response.is_error:
        raise HTTPException(response.status_code, "Evidence engine request failed")
    return response.json()


@app.post("/api/v1/analyze", status_code=202)
def analyze(value: Analyze, request: Request) -> dict[str, Any]:
    """Queue a source-backed investigation through the real evidence engine."""
    require(request, "analysis", "write")
    with httpx.Client(
        base_url=config.CORE_URL,
        headers=config.CORE_HEADERS,
        trust_env=False,
        timeout=30,
    ) as c:
        r = c.post("/api/investigations", json=value.model_dump())
        return core_json(r)


@app.get("/api/v1/graph")
def graph(request: Request, board_id: str) -> dict[str, Any]:
    """Return currently citation-verified graph relationships only."""
    require(request, "analysis", "read")
    with httpx.Client(
        base_url=config.CORE_URL,
        headers=config.CORE_HEADERS,
        trust_env=False,
        timeout=30,
    ) as c:
        r = c.get("/api/graph/" + board_id, params={"documented_only": "true"})
        return core_json(r)


@app.post("/api/v1/report")
def report(value: Report, request: Request) -> Response:
    """Generate an actual report through the existing original-source-backed exporter."""
    require(request, "analysis", "read")
    with httpx.Client(
        base_url=config.CORE_URL,
        headers=config.CORE_HEADERS,
        trust_env=False,
        timeout=60,
    ) as c:
        r = c.get("/api/export/" + value.format)
        if r.is_error:
            raise HTTPException(r.status_code, "Evidence report request failed")
        return Response(
            r.content,
            media_type=r.headers.get("content-type"),
            headers={
                "Content-Disposition": r.headers.get(
                    "content-disposition", "attachment"
                )
            },
        )


@app.get("/api/v1/evidence")
def evidence(request: Request) -> list[dict[str, Any]]:
    """List actual PostgreSQL acquisition metadata, distinct from original storage."""
    require(request, "case", "read")
    with Session() as s:
        return [
            {
                "id": e.id,
                "title": e.title,
                "status": e.status,
                "sha256": e.sha256,
                "source_url": e.source_url,
            }
            for e in s.scalars(select(Evidence).limit(1000))
        ]


@app.get("/api/v1/system")
def system(request: Request) -> dict[str, Any]:
    """Expose nonsensitive foundation counts for the database workspace."""
    require(request, "case", "read")
    from sqlalchemy import func

    with Session() as s:
        return {
            "database": "PostgreSQL",
            "metadata_records": s.scalar(select(func.count()).select_from(Evidence)),
            "entity_records": s.scalar(select(func.count()).select_from(Entity)),
            "case_records": s.scalar(select(func.count()).select_from(Case)),
            "collection_jobs": s.scalar(
                select(func.count()).select_from(CollectionJob)
            ),
            "metadata_sync_seconds": 30,
            "original_storage": "Existing immutable local evidence vault; originals not moved",
        }


@app.get("/api/v1/audit/verify")
def audit_verify(request: Request) -> dict[str, Any]:
    """Verify the gateway's PostgreSQL hash chain for an administrator."""
    require(request, "users", "read")
    with Session() as s:
        return verify(s)


LOGIN_PAGE = """<!doctype html><html><head><title>SHERLOCK OSINT · Sign in</title><style>body{background:#101820;color:#dce5eb;font:16px system-ui;display:grid;place-items:center;height:95vh}form{background:#18232c;padding:40px;border:1px solid #405461;border-radius:12px;width:380px}label{display:block;margin:18px 0}input,button{width:100%;box-sizing:border-box;padding:12px;background:#0f1920;color:#dce5eb;border:1px solid #405461;border-radius:6px}button{background:#aacbd8;color:#11202a}small{color:#8da6b5}</style></head><body><form id="login"><h1>SHERLOCK OSINT</h1><p>Project Looking Glass</p><small>Authenticated evidence workspace</small><label>Username<input name="username" autocomplete="username" required></label><label>Password<input type="password" name="password" autocomplete="current-password" required></label><label>Authenticator code<input name="totp" autocomplete="one-time-code" inputmode="numeric"></label><button>Sign in</button><p id="error"></p></form><script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));const r=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});if(r.ok)location.href='/';else document.querySelector('#error').textContent=(await r.json()).detail;};</script></body></html>"""


class KnowledgeQuery(BaseModel):
    """Read-only semantic search is available to every authenticated reading role."""

    query: str = Field(min_length=2, max_length=500)
    mode: str = Field(default="hybrid", pattern=r"^(hybrid|semantic|keyword)$")
    limit: int = Field(default=12, ge=1, le=30)


@app.post("/api/knowledge/search")
def knowledge_search(value: KnowledgeQuery, request: Request) -> dict[str, Any]:
    """Proxy a read-only query while preserving Viewer access and upstream errors."""
    require(request, "analysis", "read")
    with httpx.Client(
        base_url=config.CORE_URL,
        headers=config.CORE_HEADERS,
        trust_env=False,
        timeout=120,
    ) as c:
        return core_json(c.post("/api/knowledge/search", json=value.model_dump()))


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def core_proxy(path: str, request: Request) -> Response:
    """Serve the existing board and media behind role checks, without forwarding credentials."""
    if (
        not path
        and not request.cookies.get("sherlock_access")
        and not request.headers.get("authorization")
    ):
        return HTMLResponse(LOGIN_PAGE)
    action = "read" if request.method == "GET" else "write"
    resource = (
        "users"
        if path in ("api/models/config", "api/onion/config", "api/forensics/settings", "api/erps/deletion")
        else "legacy"
    )
    user = require(request, resource, action)
    client = httpx.AsyncClient(
        base_url=config.CORE_URL,
        headers=config.CORE_HEADERS,
        trust_env=False,
        timeout=config.CORE_PROXY_TIMEOUT,
    )
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in ("content-type", "range", "if-none-match")
    }
    headers.update(config.CORE_HEADERS)
    if path.startswith("api/erps/"):
        headers["X-Sherlock-Erps-Role"] = user.role
    upstream = await client.send(
        client.build_request(
            request.method,
            config.CORE_URL + "/" + path.lstrip("/"),
            params=request.query_params,
            content=await request.body(),
            headers=headers,
        ),
        stream=True,
    )

    async def stream() -> AsyncIterator[bytes]:
        """Stream real media and close the internal response even if the browser disconnects."""
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    response_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower()
        in (
            "content-type",
            "content-disposition",
            "etag",
            "content-range",
            "accept-ranges",
            "content-security-policy",
            "x-content-type-options",
            "cache-control",
        )
    }
    return StreamingResponse(
        stream(), status_code=upstream.status_code, headers=response_headers
    )
