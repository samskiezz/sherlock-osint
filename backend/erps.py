"""Durable ingestion outbox and a fixed-path ERPS proxy for the local case."""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import threading
import uuid
import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from .erps_client import ErpsClient

NAMESPACE = uuid.UUID("f335e603-4a93-48c8-8c16-d48a3f083b09")
PATTERNS = [
    ("Email", re.compile(r"(?<![\w.+-])[\w.+-]{1,64}@[\w.-]{1,253}\.[A-Za-z]{2,63}\b")),
    ("Doi", re.compile(r"\b10\.\d{4,9}/[^\s<>\"]+", re.I)),
    ("Handle", re.compile(r"(?<!\w)@[A-Za-z0-9_]{2,30}\b")),
    ("Person", re.compile(r"\b[A-Z][a-z]{1,30}(?:[ -][A-Z][a-z]{1,30}){1,2}\b")),
]


class IndexRequest(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=64)


def source_uuid(eid):
    return str(uuid.uuid5(NAMESPACE, eid))


def extract(eid, text):
    """Offsets name UTF-8 bytes in the extracted text, never PDF/source bytes."""
    source = source_uuid(eid)
    result = []
    occupied = []
    for kind, pattern in PATTERNS:
        for match in pattern.finditer(text):
            if any(match.start() < b and a < match.end() for a, b in occupied):
                continue
            occupied.append(match.span())
            offset = len(text[:match.start()].encode("utf-8"))
            surface = match.group()
            result.append({"id": str(uuid.uuid5(NAMESPACE, f"{source}:{offset}:{kind}:{surface}")),
                "evidence_id": source, "byte_offset": offset, "offset_space": "ExtractedTextUtf8",
                "surface": surface, "kind": kind, "context": text[max(0,match.start()-80):match.end()+80],
                "valid_from": -9223372036854775808, "valid_to": 9223372036854775807})
            if len(result) > 500:
                raise ValueError("Extraction exceeds 500 mentions; submit a scoped selection")
    return result


def install(core):
    core.execute("CREATE TABLE IF NOT EXISTS erps_outbox(evidence_id TEXT PRIMARY KEY, text_hash TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, error TEXT, updated TEXT NOT NULL)")
    serial = threading.Lock()
    scan_after = ""

    def enqueue(eid, force=False):
        if not force and os.environ.get("ERPS_AUTO_INGEST") != "1":
            return
        found = core.rows("SELECT text FROM evidence WHERE id=? AND status='ORIGINAL VERIFIED'", (eid,))
        if not found:
            raise ValueError("Only verified extracted evidence can be indexed")
        digest = hashlib.sha256(found[0]["text"].encode()).hexdigest()
        core.execute("INSERT INTO erps_outbox(evidence_id,text_hash,status,updated) VALUES(?,?,'pending',?) ON CONFLICT(evidence_id) DO UPDATE SET text_hash=excluded.text_hash,status=CASE WHEN erps_outbox.text_hash=excluded.text_hash AND erps_outbox.status='complete' THEN 'complete' ELSE 'pending' END,attempts=CASE WHEN erps_outbox.text_hash=excluded.text_hash AND erps_outbox.status='complete' THEN erps_outbox.attempts ELSE 0 END,error=NULL,updated=excluded.updated", (eid, digest, core.now()))

    def reconcile_once():
        """Recover a crash between extraction commit and outbox insertion."""
        nonlocal scan_after
        if os.environ.get("ERPS_AUTO_INGEST") != "1":
            return
        batch = core.rows("SELECT e.id,o.text_hash FROM evidence e LEFT JOIN erps_outbox o ON o.evidence_id=e.id WHERE e.status='ORIGINAL VERIFIED' AND e.id>? ORDER BY e.id LIMIT 50", (scan_after,))
        for item in batch:
            text = core.rows("SELECT text FROM evidence WHERE id=?", (item["id"],))[0]["text"]
            if hashlib.sha256(text.encode()).hexdigest() != item["text_hash"]:
                enqueue(item["id"], force=True)
        scan_after = batch[-1]["id"] if len(batch) == 50 else ""

    def drain_once():
        if not serial.acquire(blocking=False):
            return
        try:
            for item in core.rows("SELECT * FROM erps_outbox WHERE status IN ('pending','retry') AND attempts<10 ORDER BY updated LIMIT 5"):
                try:
                    evidence = core.rows("SELECT text FROM evidence WHERE id=?", (item["evidence_id"],))[0]
                    if hashlib.sha256(evidence["text"].encode()).hexdigest() != item["text_hash"]:
                        raise ValueError("Extracted text changed; enqueue its current version")
                    mentions = extract(item["evidence_id"], evidence["text"])
                    if mentions:
                        with ErpsClient() as c:
                            c.resolve(mentions)
                    core.execute("UPDATE erps_outbox SET status='complete',error=NULL,updated=? WHERE evidence_id=?", (core.now(), item["evidence_id"]))
                    core.log("erps_ingest_complete", {"evidence_id": item["evidence_id"], "mentions": len(mentions)})
                except Exception as ex:
                    # Do not persist HTTP request headers or provider credentials.
                    reason = "ERPS unavailable" if isinstance(ex, httpx.HTTPError) else str(ex)[:200]
                    core.execute("UPDATE erps_outbox SET status=CASE WHEN attempts+1>=10 THEN 'failed' ELSE 'retry' END,attempts=attempts+1,error=?,updated=? WHERE evidence_id=?", (reason, core.now(), item["evidence_id"]))
        finally:
            serial.release()

    async def worker():
        while True:
            try:
                await run_in_threadpool(reconcile_once)
                await run_in_threadpool(drain_once)
            except Exception:
                import contextlib
                with contextlib.suppress(Exception):
                    core.log("erps_outbox_unavailable", {"retry_seconds": 30})
            await asyncio.sleep(30)

    @core.app.on_event("startup")
    async def startup():
        if os.environ.get("ERPS_AUTO_INGEST") == "1":
            core.app.state.erps_worker = asyncio.create_task(worker())

    @core.app.on_event("shutdown")
    async def shutdown():
        task = getattr(core.app.state, "erps_worker", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def role(request):
        value = request.headers.get("x-sherlock-erps-role")
        if not value:
            return "Admin"  # Core is a loopback-only trusted desktop service.
        from foundation import config
        if not config.CORE_TOKEN or not hmac.compare_digest(request.headers.get("x-sherlock-core-token", ""), config.CORE_TOKEN):
            raise HTTPException(403, "Trusted gateway identity required")
        if value not in ("Admin", "Analyst", "Viewer"):
            raise HTTPException(403, "Unknown role")
        return value

    def forward(request, method, path, **kwargs):
        try:
            with ErpsClient(role(request)) as client:
                return client.request(method, path, **kwargs)
        except httpx.HTTPStatusError as ex:
            try:
                detail = ex.response.json().get("detail", "ERPS request failed")
            except (ValueError, AttributeError):
                detail = "ERPS rejected the request; check field names, types, and limits"
            raise HTTPException(ex.response.status_code, detail) from None
        except (httpx.HTTPError, RuntimeError):
            raise HTTPException(503, "ERPS unavailable; start the configured service") from None

    @core.app.get("/api/erps/health")
    def health(request: Request):
        return forward(request, "GET", "/health")

    @core.app.get("/api/erps/entities")
    def entities(request: Request):
        return forward(request, "GET", "/entities", params=dict(request.query_params))

    @core.app.get("/api/erps/entities/{eid}")
    def entity(eid: uuid.UUID, request: Request):
        return forward(request, "GET", f"/entities/{eid}", params=dict(request.query_params))

    @core.app.get("/api/erps/entities/{eid}/neighbors")
    def neighbors(eid: uuid.UUID, request: Request):
        return forward(request, "GET", f"/entities/{eid}/neighbors", params=dict(request.query_params))

    @core.app.get("/api/erps/lineage/{eid}")
    def lineage(eid: uuid.UUID, request: Request):
        return forward(request, "GET", f"/lineage/{eid}")

    @core.app.post("/api/erps/resolve")
    def resolve(payload: dict, request: Request):
        return forward(request, "POST", "/resolve", json=payload)

    @core.app.post("/api/erps/deletion")
    def deletion(payload: dict, request: Request):
        return forward(request, "POST", "/deletion", json=payload)

    @core.app.get("/api/erps/sources")
    def sources(request: Request):
        role(request)
        return {"sources": [{"id": e["id"], "source_uuid": source_uuid(e["id"]), "title": e["title"]} for e in core.rows("SELECT id,title FROM evidence WHERE status='ORIGINAL VERIFIED' ORDER BY created DESC")], "outbox": core.rows("SELECT * FROM erps_outbox ORDER BY updated DESC")}

    @core.app.post("/api/erps/index")
    def index(payload: IndexRequest, request: Request):
        if role(request) == "Viewer":
            raise HTTPException(403, "Write role required")
        try:
            enqueue(payload.evidence_id, force=True)
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from None
        drain_once()
        return core.rows("SELECT * FROM erps_outbox WHERE evidence_id=?", (payload.evidence_id,))[0]

    return {"enqueue": enqueue, "drain_once": drain_once, "reconcile_once": reconcile_once}
