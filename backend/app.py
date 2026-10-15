from __future__ import annotations
import asyncio, base64, csv, hashlib, io, ipaddress, json, math, mimetypes, os, re, socket, sqlite3, subprocess, threading, time, uuid, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .service_config import load as load_service_config

load_service_config()

ROOT = Path(
    os.environ.get("SHERLOCK_DATA", str(Path(__file__).resolve().parents[1] / "data"))
)
ROOT.mkdir(parents=True, exist_ok=True)
for folder in ["originals", "derivatives"]:
    (ROOT / folder).mkdir(exist_ok=True)
MAX_BYTES = 25 * 1024 * 1024
MAX_VAULT_BYTES = 5 * 1024 * 1024 * 1024
MIN_FREE_BYTES = 1024 * 1024 * 1024
app = FastAPI(title="SHERLOCK OSINT", version="0.9.0")


@app.middleware("http")
async def local_origin_guard(request, call_next):
    origin = request.headers.get("origin")
    allowed = {
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    }
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin not in allowed
    ):
        return Response(
            json.dumps({"detail": "Cross-origin writes are prohibited"}),
            status_code=403,
            media_type="application/json",
        )
    response = await call_next(request)
    if request.url.path.startswith("/api/") and request.url.path not in (
        "/api/audit/verify",
        "/api/audit/anchor",
    ):
        from starlette.concurrency import run_in_threadpool

        await run_in_threadpool(
            log,
            "api_access",
            {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
            },
        )
    return response


lock = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return prefix + "-" + uuid.uuid4().hex[:12]


def db():
    c = sqlite3.connect(ROOT / "case.db", timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def execute(sql, args=()):
    with lock, db() as c:
        return c.execute(sql, args).lastrowid


def rows(sql, args=()):
    with db() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def log(action, detail):
    from .audit_chain import append

    with lock, db() as c:
        append(c, now(), action, json.dumps(detail))


def initialize():
    with db() as c:
        c.executescript("""PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,title TEXT,kind TEXT,status TEXT,url TEXT,sha256 TEXT,path TEXT,mime TEXT,size INTEGER,created TEXT,metadata TEXT,text TEXT,preview TEXT);
CREATE TABLE IF NOT EXISTS boards(id TEXT PRIMARY KEY,name TEXT,data TEXT);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,objective TEXT,url TEXT,status TEXT,progress INTEGER,attempts INTEGER,error TEXT,evidence_id TEXT,created TEXT,updated TEXT,result TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,time TEXT,action TEXT,detail TEXT);
CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY,created TEXT,data TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(id UNINDEXED,title,text);
""")
    from .audit_chain import migrate

    with lock, db() as c:
        migrate(c)
    with db() as c:
        if "next_attempt" not in [r[1] for r in c.execute("PRAGMA table_info(jobs)")]:
            c.execute("ALTER TABLE jobs ADD COLUMN next_attempt REAL DEFAULT 0")
        if "transport" not in [r[1] for r in c.execute("PRAGMA table_info(jobs)")]:
            c.execute("ALTER TABLE jobs ADD COLUMN transport TEXT DEFAULT 'public'")
    # File locations are local caches, not chain-of-custody identifiers. Rebase them when a case is copied to another computer.
    for entry in rows(
        "SELECT id,sha256,path,preview FROM evidence WHERE sha256 IS NOT NULL"
    ):
        if not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]) or not re.fullmatch(
            r"[A-Za-z0-9_-]+", entry["id"]
        ):
            continue
        original = ROOT / "originals" / entry["sha256"]
        preview = ROOT / "derivatives" / entry["id"] / "preview.png"
        execute(
            "UPDATE evidence SET path=?,preview=? WHERE id=?",
            (str(original), str(preview) if preview.is_file() else None, entry["id"]),
        )
    if not rows("SELECT id FROM boards"):
        seed()


def seed():
    specs = [
        (
            "cole",
            "Cole Tomas Allen",
            "person",
            {"x": 110, "y": 110},
            "Biographical and legal assertions imported from the supplied dossier. No primary source has yet validated these assertions.",
        ),
        (
            "caltech",
            "California Institute of Technology",
            "organisation",
            {"x": 520, "y": 80},
            "Institutional relationship proposed in the supplied dossier; inspect the original Caltech record when acquired.",
        ),
        (
            "jpl",
            "NASA · Jet Propulsion Laboratory",
            "organisation",
            {"x": 920, "y": 110},
            "Proposed 2014 fellowship is unverified in this local case. Shared institution is not evidence of collaboration.",
        ),
        (
            "bohrdom",
            "Bohrdom · App 945530",
            "game asset",
            {"x": 110, "y": 470},
            "Steam application and depot identifiers are leads from the supplied dossier. No game executable has been acquired.",
        ),
        (
            "mondaloy",
            "Mondaloy patent history",
            "patent",
            {"x": 920, "y": 490},
            "US20030053926A1 and US20100266442A1 are candidate originals. Inventorship must be read from the records.",
        ),
        (
            "quantum",
            "The quantum timeline hypothesis",
            "hypothesis",
            {"x": 520, "y": 460},
            "Unverified proposition: a common research group or intentional predictions existed. Test conventional explanations, timestamp provenance and negative controls.",
        ),
        (
            "post",
            "X identifier · 1738018409441308955",
            "social post",
            {"x": 100, "y": 800},
            "Identifier supplied by the dossier. Decoding a Snowflake timestamp does not authenticate post text, account ownership or foreknowledge.",
        ),
        (
            "roster",
            "Fourteen-person proposed roster",
            "document",
            {"x": 930, "y": 810},
            "Secondary roster: Monica Reza, Dallis Hardwick, Anthony Chavez, William McCasland, Melissa Casias, Steven Garcia, Nuno Loureiro, Michael Hicks, Frank Maiwald, Joshua LeBlanc, Ning Li, Matthew Sullivan, Carl Grillmair, Jason Thomas, Amy Eskridge. This supplied list contains fifteen names. No common team is established.",
        ),
        (
            "notes",
            "Research discipline",
            "note",
            {"x": 530, "y": 810},
            "Follow the evidence.\nPreserve the original.\nA pattern is a question,\nnot a conclusion.",
        ),
    ]
    nodes = []
    for key, title, kind, pos, body in specs:
        evidence_id = "NOTE-" + key
        execute(
            "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                evidence_id,
                title,
                kind,
                "HYPOTHESIS" if kind == "hypothesis" else "SECONDARY SOURCE",
                "",
                None,
                None,
                "text/plain",
                0,
                now(),
                json.dumps(
                    {
                        "source": "User-supplied dossier, 13 October 2026",
                        "attribution": "Not independently verified",
                        "dates": {"imported": now()},
                        "note": body,
                    }
                ),
                body,
                None,
            ),
        )
        execute("INSERT INTO evidence_fts VALUES(?,?,?)", (evidence_id, title, body))
        nodes.append(
            {
                "id": key,
                "type": "evidence",
                "position": pos,
                "data": {"evidenceId": evidence_id},
            }
        )
    links = [
        ("cole", "caltech", "Reported alumnus"),
        ("cole", "bohrdom", "Reported developer"),
        ("caltech", "jpl", "Institutional context"),
        ("jpl", "mondaloy", "Research lead"),
        ("post", "quantum", "Prediction question"),
        ("quantum", "roster", "Unverified common-team claim"),
    ]
    edges = [
        {
            "id": f"lead-{i}",
            "source": a,
            "target": b,
            "label": label + " · unverified",
            "type": "smoothstep",
            "data": {
                "claim": label,
                "state": "UNVERIFIED",
                "confidence": "Unassessed",
                "method": "Imported secondary dossier",
                "evidence": [],
                "reason": "Investigation lead; no factual connection asserted",
                "contradictions": [],
            },
        }
        for i, (a, b, label) in enumerate(links)
    ]
    execute(
        "INSERT INTO boards VALUES(?,?,?)",
        (
            "looking-glass",
            "PROJECT LOOKING GLASS",
            json.dumps({"nodes": nodes, "edges": edges}),
        ),
    )


initialize()


def get_evidence(eid):
    r = rows("SELECT * FROM evidence WHERE id=?", (eid,))
    if not r:
        raise HTTPException(404, "Evidence not found")
    e = r[0]
    e["metadata"] = json.loads(e["metadata"])
    e["fileUrl"] = f"/api/evidence/{eid}/file" if e["path"] else None
    e["previewUrl"] = f"/api/evidence/{eid}/preview" if e["preview"] else None
    e.pop("path")
    e.pop("preview")
    return e


dns_cache = {}


def validate_url(url):
    p = urlparse(url)
    if (
        p.scheme not in ("http", "https")
        or not p.hostname
        or p.username
        or p.password
        or p.port not in (None, 80, 443)
    ):
        raise ValueError("Only public HTTP(S) URLs on standard ports are allowed")
    host = p.hostname.lower().rstrip(".")
    if host.endswith(".onion"):
        raise ValueError("Onion sources require the dedicated Tor transport")
    if (
        host == "localhost"
        or host.endswith((".localhost", ".local", ".internal"))
        or "." not in host
    ):
        raise ValueError("Local destinations are prohibited")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Private, loopback and reserved destinations are prohibited")
    return p


def safe_url(url):
    p = validate_url(url)
    host = p.hostname
    cached = dns_cache.get(host)
    if cached and cached[0] > time.time():
        addresses = cached[1]
    else:
        error = None
        for attempt in range(3):
            try:
                addresses = [
                    r[4][0]
                    for r in socket.getaddrinfo(
                        host, p.port or 443, type=socket.SOCK_STREAM
                    )
                ]
                break
            except socket.gaierror as e:
                error = e
                if attempt == 2:
                    raise ValueError(f"DNS lookup failed for {host}: {e}") from e
                time.sleep(0.25 * (attempt + 1))
        dns_cache[host] = (time.time() + 300, addresses)
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("Private, loopback and reserved destinations are prohibited")
    return p


CLIENT_HEADERS = {
    "User-Agent": "SherlockOSINT/0.1 (+public-source research; local evidence preservation)"
}


def fetch(url):
    with httpx.Client(
        timeout=35, follow_redirects=False, headers=CLIENT_HEADERS
    ) as client:
        for _ in range(6):
            safe_url(url)
            with client.stream("GET", url) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    url = str(r.url.join(r.headers["location"]))
                    continue
                r.raise_for_status()
                if int(r.headers.get("content-length", "0")) > MAX_BYTES:
                    raise ValueError("File exceeds 25 MB limit")
                chunks = []
                size = 0
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("File exceeds 25 MB limit")
                    chunks.append(chunk)
                return b"".join(chunks), url, dict(r.headers), r.status_code
        raise ValueError("Too many redirects")


def robots_allowed(url):
    p = safe_url(url)
    robots = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        data, _, _, _ = fetch(robots)
        parser = RobotFileParser()
        parser.parse(data.decode("utf-8", "replace").splitlines())
        if not parser.can_fetch("SherlockOSINT", url):
            raise ValueError("Site robots.txt disallows acquisition")
    except httpx.HTTPStatusError as e:
        # RFC 9309 section 2.3.1.3: unavailable robots (4xx) permits access.
        # Restrictions on the requested evidence URL itself remain enforced.
        if 400 <= e.response.status_code < 500:
            log(
                "robots_unavailable",
                {
                    "url": robots,
                    "status": e.response.status_code,
                    "policy": "RFC 9309 unavailable; requested resource still subject to HTTP access controls",
                },
            )
        else:
            raise ValueError(
                f"robots.txt unreachable ({e.response.status_code}); acquisition stopped"
            )
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        raise ValueError("Could not check site access policy") from e


def _preserve(data, title, url="", headers=None, method="httpx public HTTP"):
    sha = hashlib.sha256(data).hexdigest()
    existing = rows("SELECT id FROM evidence WHERE sha256=?", (sha,))
    if existing:
        prior = rows("SELECT metadata FROM evidence WHERE id=?", (existing[0]["id"],))[
            0
        ]
        metadata = json.loads(prior["metadata"])
        metadata.setdefault("subsequent_acquisitions", []).append(
            {
                "url": url,
                "retrieved_utc": now(),
                "headers": headers or {},
                "method": method,
            }
        )
        execute(
            "UPDATE evidence SET metadata=? WHERE id=?",
            (json.dumps(metadata), existing[0]["id"]),
        )
        log(
            "duplicate_acquisition",
            {"sha256": sha, "url": url, "evidence_id": existing[0]["id"]},
        )
        return existing[0]["id"]
    if (
        rows("SELECT COALESCE(sum(size),0) n FROM evidence")[0]["n"] + len(data)
        > MAX_VAULT_BYTES
    ):
        raise ValueError("Vault storage limit (5 GB) reached")
    if __import__("shutil").disk_usage(ROOT).free < MIN_FREE_BYTES + len(data):
        raise ValueError(
            "Insufficient disk space: preserve 1 GB free for the database and isolated processing"
        )
    eid = uid("EV")
    path = ROOT / "originals" / sha
    declared = (headers or {}).get("content-type", "").split(";")[0]
    if declared == "application/pdf" and not data.startswith(b"%PDF"):
        raise ValueError("Content-type mismatch: declared PDF is not a PDF")
    mime = (
        "application/pdf"
        if data.startswith(b"%PDF")
        else "image/png"
        if data.startswith(b"\x89PNG")
        else "image/jpeg"
        if data.startswith(b"\xff\xd8")
        else declared or mimetypes.guess_type(title)[0] or "application/octet-stream"
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    metadata = {
        "original_url": url,
        "final_url": url,
        "retrieved_utc": now(),
        "original_filename": urlparse(url).path.split("/")[-1] or title,
        "http_headers": headers or {},
        "retrieval_method": method,
        "source_publisher": urlparse(url).hostname or "User upload",
        "publication_date": None,
        "licence": "Unknown; no redistribution assertion",
        "transformations": [],
        "acquisition_log": [
            "Fetched bytes",
            "SHA-256 calculated",
            "Original stored read-only",
        ],
        "declared_mime": declared,
    }
    kind = (
        "video"
        if mime.startswith("video/")
        else "audio"
        if mime.startswith("audio/")
        else "document"
        if mime == "application/pdf"
        else "photograph"
        if mime.startswith("image/")
        else "website"
        if "html" in mime
        else "source code"
        if mime.startswith("text/")
        else "file"
    )
    execute(
        "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            eid,
            title,
            kind,
            "ORIGINAL ACQUIRED",
            url,
            sha,
            str(path),
            mime,
            len(data),
            now(),
            json.dumps(metadata),
            "",
            None,
        ),
    )
    log("original_preserved", {"id": eid, "sha256": sha, "bytes": len(data)})
    return eid


def preserve(data, title, url="", headers=None, method="httpx public HTTP"):
    with lock:
        return _preserve(data, title, url, headers, method)


processor_locks = {}


def process(eid):
    from .sandbox import run, SandboxError

    with lock:
        serial = processor_locks.setdefault(eid, threading.Lock())
    with serial:
        e = rows("SELECT * FROM evidence WHERE id=?", (eid,))[0]
        if not e["path"]:
            raise ValueError("Original not acquired")
        original = Path(e["path"]).resolve()
        if original.parent != (ROOT / "originals").resolve():
            raise ValueError("Original is outside the preserved evidence vault")
        der = ROOT / "derivatives" / eid
        try:
            result = run(original, e["mime"], e["sha256"], der)
        except Exception as ex:
            with lock:
                meta = json.loads(
                    rows("SELECT metadata FROM evidence WHERE id=?", (eid,))[0][
                        "metadata"
                    ]
                )
                meta["processing_status"] = (
                    "BLOCKED"
                    if isinstance(ex, SandboxError) and "unavailable" in str(ex).lower()
                    else "FAILED"
                )
                meta["processing_failure"] = str(ex)[:1600]
                execute(
                    "UPDATE evidence SET metadata=? WHERE id=?", (json.dumps(meta), eid)
                )
            log("isolated_processing_failed", {"id": eid, "error": str(ex)[:1600]})
            raise
        with lock:
            meta = json.loads(
                rows("SELECT metadata FROM evidence WHERE id=?", (eid,))[0]["metadata"]
            )
            allowed = {
                "json_keys",
                "static_only",
                "page_count",
                "document_metadata",
                "pages",
                "extraction_truncated",
                "ocr_pages",
                "dimensions",
                "format",
                "exif",
                "histogram",
                "average_hash",
                "ocr",
                "media_probe",
                "transcript_status",
                "document_title",
                "printable_strings",
                "processor_status",
                "links",
                "image_forensics",
                "visual_features",
                "patent",
                "media",
            }
            meta.update({k: v for k, v in result["metadata"].items() if k in allowed})
            meta["sandbox"] = result["sandbox"]
            meta["processing_status"] = "COMPLETE"
            meta.pop("processing_failure", None)
            meta.setdefault("transformations", []).append(
                {
                    "method": "Network-disabled, resource-limited container extraction",
                    "created": now(),
                    "derivative": f"{eid}/text.txt",
                    "image_id": result["sandbox"]["image_id"],
                }
            )
            meta["derivative_hashes"] = {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in der.iterdir()
                if p.is_file()
                and not p.is_symlink()
                and p.name
                in (
                    "text.txt",
                    "preview.png",
                    "result.json",
                    "red.png",
                    "green.png",
                    "blue.png",
                    "lsb.png",
                    "ela.png",
                    "visual-blur-0.png",
                    "visual-blur-2.png",
                    "visual-blur-8.png",
                    "visual-blur-24.png",
                    "visual-panel-0.png",
                    "visual-panel-1.png",
                    "visual-panel-2.png",
                    "visual-panel-3.png",
                    "visual-fit-0.png",
                    "visual-fit-1.png",
                    "visual-fit-2.png",
                    "visual-fit-3.png",
                    "visual-residual-0.png",
                    "visual-residual-1.png",
                    "visual-residual-2.png",
                    "visual-residual-3.png",
                )
            }
            meta["integrity_verified_utc"] = now()
            text = result["text"]
            preview = str(der / "preview.png") if result["preview"] else None
            execute(
                "UPDATE evidence SET text=?,preview=?,metadata=?,status=? WHERE id=?",
                (text, preview, json.dumps(meta), "ORIGINAL VERIFIED", eid),
            )
            execute("DELETE FROM evidence_fts WHERE id=?", (eid,))
            execute("INSERT INTO evidence_fts VALUES(?,?,?)", (eid, e["title"], text))
        log(
            "isolated_extraction_complete",
            {
                "id": eid,
                "characters": len(text),
                "preview": bool(preview),
                "image_id": result["sandbox"]["image_id"],
            },
        )


executor = ThreadPoolExecutor(max_workers=2)
domain_locks = {}
running = set()
stopping = threading.Event()


def update_job(jid, status, progress, error=None, evidence_id=None, result=None):
    execute(
        "UPDATE jobs SET status=?,progress=?,error=?,evidence_id=COALESCE(?,evidence_id),updated=?,result=COALESCE(?,result) WHERE id=?",
        (
            status,
            progress,
            error,
            evidence_id,
            now(),
            json.dumps(result) if result else None,
            jid,
        ),
    )
    log(
        "job_state", {"id": jid, "status": status, "progress": progress, "error": error}
    )


def job_step(jid, status, progress, **kwargs):
    with lock:
        current = rows("SELECT status FROM jobs WHERE id=?", (jid,))
        if not current or current[0]["status"] in ("PAUSED", "CANCELLED"):
            return False
        update_job(jid, status, progress, **kwargs)
        return True


def run_job(jid):
    try:
        j = rows("SELECT * FROM jobs WHERE id=?", (jid,))[0]
        if j["status"] != "QUEUED":
            return
        execute("UPDATE jobs SET attempts=attempts+1 WHERE id=?", (jid,))
        job_step(jid, "FETCHING", 10)
        domain = urlparse(j["url"]).hostname
        with lock:
            dlock = domain_locks.setdefault(domain, threading.Lock())
        with dlock:
            if j.get("transport") == "tor":
                onion["robots"](j["url"])
                data, final, headers, code = onion["fetch"](j["url"])
            else:
                robots_allowed(j["url"])
                data, final, headers, code = fetch(j["url"])
            time.sleep(1)
        if rows("SELECT status FROM jobs WHERE id=?", (jid,))[0]["status"] in (
            "CANCELLED",
            "PAUSED",
        ):
            return
        job_step(jid, "PRESERVING", 50)
        method = (
            "Tor SOCKS5h · remote DNS · no clearnet fallback"
            if j.get("transport") == "tor"
            else "httpx public HTTP"
        )
        eid = preserve(data, j["objective"], final, headers, method)
        e = rows("SELECT metadata FROM evidence WHERE id=?", (eid,))[0]
        meta = json.loads(e["metadata"])
        if (
            not meta.get("requested_urls")
            and meta.get("retrieval_method") == "httpx public HTTP"
        ):
            meta["original_url"] = j["url"]
        meta.setdefault("requested_urls", []).append(j["url"])
        meta["response_status"] = code
        meta.setdefault("network_transport", j.get("transport", "public"))
        if j.get("transport") == "tor" and (
            urlparse(meta.get("original_url", "")).hostname or ""
        ).endswith(".onion"):
            meta["source_class"] = "PUBLIC ONION SOURCE · ATTRIBUTION UNVERIFIED"
        capture = re.match(
            r"https://web\.archive\.org/web/(\d{14})(?:id_)?/(https?://.+)", j["url"]
        )
        if capture:
            stamp, source_url = capture.groups()
            meta["source_class"] = "HISTORICAL ARCHIVE"
            meta["archive_capture_date"] = (
                datetime.strptime(stamp, "%Y%m%d%H%M%S")
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
            meta["archived_original_url"] = source_url
            meta["archive_date_interpretation"] = (
                "Timestamp in Internet Archive replay URL; distinct from original creation and publication dates"
            )
        execute("UPDATE evidence SET metadata=? WHERE id=?", (json.dumps(meta), eid))
        job_step(jid, "EXTRACTING", 75, evidence_id=eid)
        process(eid)
        job_step(
            jid,
            "COMPLETE",
            100,
            evidence_id=eid,
            result={
                "original_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )
    except Exception as e:
        current = rows("SELECT * FROM jobs WHERE id=?", (jid,))[0]
        if current["status"] not in ("CANCELLED", "PAUSED"):
            transient = (
                isinstance(e, (httpx.RequestError, socket.gaierror))
                and not isinstance(e, httpx.ProxyError)
                or isinstance(e, httpx.HTTPStatusError)
                and e.response.status_code in (429, 500, 502, 503, 504)
            )
            if transient and current["attempts"] < 3:
                delay = 30 * 2 ** max(0, current["attempts"] - 1)
                execute(
                    "UPDATE jobs SET next_attempt=? WHERE id=?",
                    (time.time() + delay, jid),
                )
                job_step(jid, "RETRY WAIT", current["progress"], error=str(e)[:800])
                log("retry_scheduled", {"id": jid, "delay_seconds": delay})
            else:
                job_step(
                    jid,
                    "PROCESSING FAILED"
                    if current["evidence_id"]
                    else "ACQUISITION FAILED",
                    current["progress"],
                    error=str(e)[:800],
                )
    finally:
        with lock:
            running.discard(jid)


def worker_loop():
    while not stopping.wait(0.5):
        heartbeat("acquisition-queue", {"active": len(running)})  # noqa: F821 - injected by vault.install before startup
        execute(
            "UPDATE jobs SET status='QUEUED' WHERE status='RETRY WAIT' AND next_attempt<=?",
            (time.time(),),
        )
        for j in rows(
            "SELECT id FROM jobs WHERE status='QUEUED' ORDER BY created LIMIT 2"
        ):
            with lock:
                if j["id"] in running:
                    continue
                running.add(j["id"])
            executor.submit(run_job, j["id"])


@app.on_event("startup")
def start():
    execute(
        "UPDATE jobs SET status='QUEUED' WHERE status IN ('FETCHING','PRESERVING','EXTRACTING')"
    )
    threading.Thread(target=worker_loop, daemon=True).start()


@app.on_event("shutdown")
def stop():
    stopping.set()


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "0.13.0",
        "processing": __import__(
            "backend.sandbox", fromlist=["availability"]
        ).availability(),
        "database": "SQLite WAL + FTS5",
        "models": "See /api/models for current configured-provider status",
        "worker": "2 persistent acquisition workers",
        "network": "Public HTTP(S), robots checked, 25 MB limit",
    }


@app.get("/api/evidence")
def evidence(summary: bool = False, cards: bool = False):
    """Return card summaries for the home page; load original text only when requested."""
    if summary:
        records = rows(
            "SELECT id,title,kind,status,url,sha256,mime,size,created,path IS NOT NULL AS acquired,preview IS NOT NULL AS has_preview,json_extract(metadata,'$.page_count') AS page_count,substr(text,1,600) AS card_text FROM evidence ORDER BY created"
        )
        return [
            {
                **{
                    k: v
                    for k, v in r.items()
                    if k not in ("acquired", "has_preview", "page_count", "card_text")
                },
                "text": (r["card_text"] or "") if cards else "",
                "metadata": {"page_count": r["page_count"]},
                "fileUrl": f"/api/evidence/{r['id']}/file" if r["acquired"] else None,
                "previewUrl": f"/api/evidence/{r['id']}/preview"
                if r["has_preview"]
                else None,
            }
            for r in records
        ]
    return [
        get_evidence(r["id"]) for r in rows("SELECT id FROM evidence ORDER BY created")
    ]


@app.get("/api/evidence/{eid}")
def detail(eid: str):
    return get_evidence(eid)


@app.get("/api/evidence/{eid}/file")
def original(eid: str):
    e = rows("SELECT * FROM evidence WHERE id=?", (eid,))
    if not e or not e[0]["path"]:
        raise HTTPException(404, "Original not acquired")
    # HTML and executable content are never served as active content.
    mime = e[0]["mime"]
    safe = mime == "application/pdf" or mime in (
        "image/png",
        "image/jpeg",
        "image/webp",
        "text/plain",
        "video/mp4",
        "audio/mpeg",
        "audio/wav",
    )
    return FileResponse(
        e[0]["path"],
        media_type=mime if safe else "application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            **({} if safe else {"Content-Disposition": "attachment"}),
        },
    )


@app.get("/api/evidence/{eid}/preview")
def preview(eid: str):
    r = rows("SELECT preview FROM evidence WHERE id=?", (eid,))
    if not r or not r[0]["preview"]:
        raise HTTPException(404, "No preview derivative")
    return FileResponse(r[0]["preview"], media_type="image/png")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "25 MB limit")
    try:
        eid = preserve(
            data,
            file.filename or "Imported file",
            headers={"content-type": file.content_type or ""},
            method="User upload",
        )
    except Exception as ex:
        raise HTTPException(422, str(ex))
    try:
        await run_in_threadpool(process, eid)
    except Exception as ex:
        log("processor_failed", {"id": eid, "error": str(ex)})
    return get_evidence(eid)


@app.post("/api/evidence/{eid}/process")
def reprocess(eid: str):
    if not get_evidence(eid)["fileUrl"]:
        raise HTTPException(422, "No original acquired")
    try:
        process(eid)
    except Exception as ex:
        raise HTTPException(503, str(ex))
    return get_evidence(eid)


@app.get("/api/boards")
def boards():
    return rows("SELECT id,name FROM boards")


@app.get("/api/boards/{bid}")
def board(bid: str):
    r = rows("SELECT * FROM boards WHERE id=?", (bid,))
    if not r:
        raise HTTPException(404, "Board missing")
    return {"id": bid, "name": r[0]["name"], **json.loads(r[0]["data"])}


class BoardInput(BaseModel):
    nodes: list[dict]
    edges: list[dict]


@app.put("/api/boards/{bid}")
def save_board(bid: str, b: BoardInput):
    if not rows("SELECT id FROM boards WHERE id=?", (bid,)):
        raise HTTPException(404, "Board missing")
    for edge in b.edges:
        data = edge.get("data", {})
        if data.get("state") in ("DOCUMENTED", "CORROBORATED"):
            citations = data.get("evidence", [])
            if not citations:
                raise HTTPException(
                    422, "Documented relationships require exact source citations"
                )
            for citation in citations:
                e = get_evidence(citation.get("id", ""))
                if (
                    not e["fileUrl"]
                    or not citation.get("quote")
                    or citation["quote"] not in e["text"]
                ):
                    raise HTTPException(
                        422, "Citation must match an acquired original passage"
                    )
    execute("UPDATE boards SET data=? WHERE id=?", (json.dumps(b.model_dump()), bid))
    log("board_saved", {"id": bid, "nodes": len(b.nodes), "edges": len(b.edges)})
    return {"saved": True}


class BoardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@app.post("/api/boards")
def create_board(b: BoardCreate):
    bid = uid("BOARD")
    execute(
        "INSERT INTO boards VALUES(?,?,?)",
        (bid, b.name, json.dumps({"nodes": [], "edges": []})),
    )
    return {"id": bid, "name": b.name}


class Acquire(BaseModel):
    url: str
    title: str = Field(min_length=1, max_length=200)
    transport: str = "auto"


@app.post("/api/jobs")
def queue(a: Acquire):
    try:
        if a.transport not in ("auto", "public", "tor"):
            raise ValueError("Choose auto, public or tor transport")
        is_onion = (urlparse(a.url).hostname or "").endswith(".onion")
        transport = (
            "tor"
            if a.transport == "tor" or a.transport == "auto" and is_onion
            else "public"
        )
        if transport == "tor":
            from .onion import validate_onion_url

            validate_onion_url(a.url)
        else:
            validate_url(a.url)
    except Exception as e:
        raise HTTPException(422, str(e))
    jid = uid("TASK")
    execute(
        "INSERT INTO jobs(id,objective,url,status,progress,attempts,error,evidence_id,created,updated,result,transport) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            jid,
            a.title,
            a.url,
            "QUEUED",
            0,
            0,
            None,
            None,
            now(),
            now(),
            None,
            transport,
        ),
    )
    log("job_queued", {"id": jid, "url": a.url, "transport": transport})
    return {"id": jid}


@app.get("/api/jobs")
def jobs():
    return rows("SELECT * FROM jobs ORDER BY created DESC")


@app.post("/api/jobs/{jid}/{action}")
def job_control(jid: str, action: str):
    r = rows("SELECT * FROM jobs WHERE id=?", (jid,))
    if not r:
        raise HTTPException(404, "Job missing")
    states = {
        "pause": "PAUSED",
        "resume": "QUEUED",
        "cancel": "CANCELLED",
        "retry": "QUEUED",
    }
    if action not in states:
        raise HTTPException(422, "Unknown action")
    if r[0]["status"] == "COMPLETE":
        raise HTTPException(409, "Completed jobs are immutable")
    update_job(jid, states[action], r[0]["progress"])
    return {"status": states[action]}


@app.get("/api/activity")
def activity():
    return rows("SELECT * FROM audit ORDER BY id DESC LIMIT 80")


@app.get("/api/search")
def search(q: str):
    tokens = re.findall(r"\w+", q)
    if not tokens:
        return []
    query = " AND ".join('"' + t + '"' for t in tokens[:12])
    hits = rows(
        "SELECT id,snippet(evidence_fts,2,'<mark>','</mark>','…',30) AS snippet,bm25(evidence_fts) AS rank FROM evidence_fts WHERE evidence_fts MATCH ? ORDER BY rank LIMIT 50",
        (query,),
    )
    return [{**h, "evidence": get_evidence(h["id"])} for h in hits]


class Cipher(BaseModel):
    input: str = Field(max_length=100000)
    method: str
    shift: int = 13
    control: str = Field(default="", max_length=100000)
    evidence_id: str | None = None
    parameters: dict = Field(default_factory=dict)
    holdout_input: str = Field(default="", max_length=100000)
    holdout_expected: str = Field(default="", max_length=100000)


@app.post("/api/cipher")
def cipher(c: Cipher):
    from .cryptanalysis import transform, statistics, VERSION

    params = {"shift": c.shift, **c.parameters}
    if len(json.dumps(params)) > 110000:
        raise HTTPException(422, "Parameters exceed size limit")
    source_record = None
    if c.evidence_id:
        try:
            e, meta, digest = forensics["source"](c.evidence_id)
            offset = e["text"].find(c.input) if c.input else -1
            if offset < 0:
                raise ValueError(
                    "Exact input is absent from the attested evidence text. Use manual test input for a transcription."
                )
            source_record = {
                "sha256": e["sha256"],
                "text_sha256": digest,
                "offset": offset,
                "length": len(c.input),
            }
        except ValueError as ex:
            raise HTTPException(422, str(ex))
    try:
        output = transform(c.input, c.method, params)
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError) as ex:
        failed_id = uid("EXP")
        failed = {
            **c.model_dump(),
            "output": "",
            "control_output": None,
            "entropy": statistics(c.input)["entropy"],
            "validation": "FAILED",
            "failure": str(ex)[:500],
            "engine_version": VERSION,
            "attempt_number": rows("SELECT count(*) n FROM experiments")[0]["n"] + 1,
        }
        execute(
            "INSERT INTO experiments VALUES(?,?,?)",
            (failed_id, now(), json.dumps(failed)),
        )
        log("cipher_experiment_failed", {"id": failed_id, "method": c.method})
        raise HTTPException(422, {"reason": str(ex), "experiment_id": failed_id})
    control_output = None
    if c.control:
        try:
            control_output = transform(c.control, c.method, params)
        except (ValueError, KeyError, TypeError, UnicodeError, OverflowError) as ex:
            control_output = "Invalid control: " + str(ex)
    holdout = {"status": "NOT RUN"}
    if c.holdout_input:
        try:
            value = transform(c.holdout_input, c.method, params)
            holdout = {
                "status": "NOT INDEPENDENT"
                if c.holdout_input == c.input
                else "MATCH"
                if c.holdout_expected and value == c.holdout_expected
                else "MISMATCH"
                if c.holdout_expected
                else "EXPECTED OUTPUT REQUIRED",
                "output": value,
                "independence": "USER DECLARED; NOT INDEPENDENTLY VERIFIED",
            }
        except (ValueError, KeyError, TypeError, UnicodeError, OverflowError) as ex:
            holdout = {"status": "FAILED", "reason": str(ex)}
    eid = uid("EXP")
    result = {
        **c.model_dump(),
        "parameters": params,
        "engine_version": VERSION,
        "output": output,
        "control_output": control_output,
        "statistics": statistics(c.input),
        "entropy": statistics(c.input)["entropy"],
        "source_record": source_record,
        "holdout": holdout,
        "validation": "UNVALIDATED",
        "warning": "Readable output or a matching test vector does not authenticate an intentional message. Holdout independence requires review.",
        "attempt_number": rows("SELECT count(*) n FROM experiments")[0]["n"] + 1,
    }
    execute("INSERT INTO experiments VALUES(?,?,?)", (eid, now(), json.dumps(result)))
    log("cipher_experiment", {"id": eid, "method": c.method})
    return {"id": eid, **result}


@app.get("/api/experiments")
def experiments():
    return [
        {"id": r["id"], "created": r["created"], **json.loads(r["data"])}
        for r in rows("SELECT * FROM experiments ORDER BY created DESC")
    ]


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@app.post("/api/investigate")
def investigate(q: Question):
    # Deterministic evidence retrieval/audit only. Never impersonates a configured LLM.
    tokens = [t for t in re.findall(r"\w+", q.question) if len(t) > 3]
    hits = []
    for token in tokens[:8]:
        for hit in search(token):
            if hit["id"] not in [h["id"] for h in hits]:
                hits.append(hit)
    originals = [
        h
        for h in hits
        if h["evidence"]["fileUrl"] and investigator["integrity"](h["evidence"])[0]
    ]
    jid = uid("AUDIT")
    result = {
        "mode": "Deterministic evidence auditor; model not configured",
        "question": q.question,
        "sources": [
            {
                "id": h["id"],
                "title": h["evidence"]["title"],
                "quote": h["evidence"]["text"][:600],
                "status": h["evidence"]["status"],
            }
            for h in originals[:8]
        ],
        "conclusion": "Relevant acquired records are listed for review. No factual conclusion or identity attribution has been generated.",
        "unsupported_notes": len(hits) - len(originals),
    }
    execute(
        "INSERT INTO jobs(id,objective,url,status,progress,attempts,error,evidence_id,created,updated,result) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            jid,
            q.question,
            "",
            "COMPLETE",
            100,
            1,
            None,
            None,
            now(),
            now(),
            json.dumps(result),
        ),
    )
    log("evidence_audit", {"id": jid, "originals": len(originals)})
    return result


@app.get("/api/export/{fmt}")
def export(fmt: str):
    ev = evidence()
    payload = {
        "exported": now(),
        "evidence": ev,
        "boards": [board(b["id"]) for b in boards()],
        "jobs": jobs(),
        "experiments": experiments(),
        "watches": rows("SELECT * FROM watches"),
        "watch_runs": rows("SELECT * FROM watch_runs"),
        "discoveries": rows("SELECT * FROM discovery"),
        "audit_log": rows("SELECT * FROM audit"),
        "audit_chain": rows("SELECT * FROM audit_chain"),
        "audit_chain_migration": rows("SELECT * FROM audit_chain_migration"),
        "investigations": rows("SELECT * FROM investigations"),
        "investigator_tasks": rows("SELECT * FROM investigator_tasks"),
        "claims": rows("SELECT * FROM claims"),
        "chronology": rows("SELECT * FROM chronology"),
        "places": rows("SELECT * FROM places"),
        "comparisons": rows("SELECT * FROM comparisons"),
        "watch_analyses": rows("SELECT * FROM watch_analyses"),
        "watch_schedules": rows("SELECT * FROM watch_schedules"),
        "research_campaigns": rows("SELECT * FROM research_campaigns"),
        "research_runs": rows("SELECT * FROM research_runs"),
        "research_tasks": rows("SELECT * FROM research_tasks"),
        "research_discovery": rows("SELECT * FROM research_discovery"),
        "research_run_jobs": rows("SELECT * FROM research_run_jobs"),
        "tor_config": rows("SELECT * FROM tor_config"),
        "forensic_runs": rows("SELECT * FROM forensic_runs"),
        "forensic_settings": rows("SELECT * FROM forensic_settings"),
        "vault_snapshots": rows("SELECT * FROM vault_snapshots"),
        "worker_heartbeats": rows("SELECT * FROM worker_heartbeats"),
        "patent_records": rows("SELECT * FROM patent_records"),
        "media_leads": rows("SELECT * FROM media_leads"),
        "method_registry": rows("SELECT * FROM method_registry"),
        "analytic_records": rows("SELECT * FROM analytic_records"),
        "analytic_pins": rows("SELECT * FROM analytic_pins"),
        "analysis_monitors": rows("SELECT * FROM analysis_monitors"),
        "crypto_records": rows("SELECT * FROM crypto_records"),
        "retrieval_documents": rows("SELECT * FROM retrieval_documents"),
        "retrieval_chunks": rows("SELECT * FROM retrieval_chunks"),
        "retrieval_identifiers": rows("SELECT * FROM retrieval_identifiers"),
        "retrieval_queries": rows("SELECT * FROM retrieval_queries"),
        "retrieval_requests": rows("SELECT * FROM retrieval_requests"),
        "automation_workflows": rows("SELECT * FROM automation_workflows"),
        "automation_runs": rows("SELECT * FROM automation_runs"),
        "automation_receipts": rows("SELECT * FROM automation_receipts"),
        "automation_schedules": rows("SELECT * FROM automation_schedules"),
        "automation_schedule_seen": rows("SELECT * FROM automation_schedule_seen"),
        "autopilot_settings": rows("SELECT * FROM autopilot_settings"),
        "autopilot_dispatch": rows("SELECT * FROM autopilot_dispatch"),
        "visual_runs": rows("SELECT * FROM visual_runs"),
        "visual_explanations": rows("SELECT * FROM visual_explanations"),
        "visual_review_state": rows("SELECT * FROM visual_review_state"),
        "media_reports": rows("SELECT * FROM media_reports"),
        "media_origins": rows("SELECT * FROM media_origins"),
        "social_feeds": rows("SELECT * FROM social_feeds"),
        "social_polls": rows("SELECT * FROM social_polls"),
        "social_posts": rows("SELECT * FROM social_posts"),
        "social_feed_posts": rows("SELECT * FROM social_feed_posts"),
        "social_observations": rows("SELECT * FROM social_observations"),
        "prediction_audits": rows("SELECT * FROM prediction_audits"),
    }
    if fmt in ("pdf", "docx"):
        from .reports import pdf, docx

        data = pdf(payload) if fmt == "pdf" else docx(payload)
        return Response(
            data,
            media_type="application/pdf"
            if fmt == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="looking-glass-report.{fmt}"'
            },
        )
    if fmt == "json":
        return Response(
            json.dumps(payload, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="looking-glass.json"'
            },
        )
    if fmt == "csv":
        stream = io.StringIO()
        w = csv.DictWriter(
            stream, fieldnames=["id", "title", "status", "url", "sha256", "size"]
        )
        w.writeheader()
        w.writerows({k: e.get(k) for k in w.fieldnames} for e in ev)
        return Response(
            stream.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="evidence.csv"'},
        )
    if fmt == "zip":
        from .case_archive import build

        return build(sys.modules[__name__], payload)
    raise HTTPException(404, "Export format unavailable")


class Annotation(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = "note"
    text: str = Field(min_length=1, max_length=20000)
    citations: list[dict] = []


@app.post("/api/annotations")
def annotate(a: Annotation):
    for citation in a.citations:
        source = get_evidence(citation.get("id", ""))
        if (
            not source["fileUrl"]
            or not citation.get("quote")
            or citation["quote"] not in source["text"]
        ):
            raise HTTPException(
                422, "Annotation citation must match an acquired original"
            )
    eid = uid("NOTE")
    metadata = {
        "source": "Human-created annotation",
        "citations": a.citations,
        "attribution": "Secondary annotation; inspect cited originals",
        "dates": {"annotated": now()},
    }
    execute(
        "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            eid,
            a.title,
            a.kind,
            "SECONDARY SOURCE",
            "",
            None,
            None,
            "text/plain",
            0,
            now(),
            json.dumps(metadata),
            a.text,
            None,
        ),
    )
    execute("INSERT INTO evidence_fts VALUES(?,?,?)", (eid, a.title, a.text))
    log("annotation_created", {"id": eid, "citations": len(a.citations)})
    return get_evidence(eid)


# Imported after API definitions so discovery can enqueue durable acquisition tasks.
import sys
from .onion import install as install_onion

onion = install_onion(sys.modules[__name__])
from .scheduler import install as install_scheduler

scheduler = install_scheduler(sys.modules[__name__])
from .investigator import install as install_investigator

investigator = install_investigator(sys.modules[__name__])
from .audit_chain import install as install_audit_chain

install_audit_chain(sys.modules[__name__])

from .workspaces import install as install_workspaces

workspaces = install_workspaces(sys.modules[__name__])
from .forensics import install as install_forensics

forensics = install_forensics(sys.modules[__name__])

from .vault import install as install_vault

vault = install_vault(sys.modules[__name__])

from .research import install as install_research

research = install_research(sys.modules[__name__])

from .patents import install as install_patents

patents = install_patents(sys.modules[__name__])
from .tradecraft import install as install_tradecraft

tradecraft = install_tradecraft(sys.modules[__name__])
from .analysis_monitors import install as install_analysis_monitors

analysis_monitors = install_analysis_monitors(sys.modules[__name__])
from .crypto_lab import install as install_crypto

crypto_lab = install_crypto(sys.modules[__name__])


from .retrieval import install as install_retrieval

retrieval = install_retrieval(sys.modules[__name__])

from .case_archive import install as install_case_archive

install_case_archive(sys.modules[__name__])

from .automation import install as install_automation

automation = install_automation(sys.modules[__name__])

from .visual_intelligence import install as install_visual

visual = install_visual(sys.modules[__name__])
from .social_watch import install as install_social

social = install_social(sys.modules[__name__])
from .prediction_audit import install as install_prediction_audit

prediction_audit = install_prediction_audit(sys.modules[__name__])
from .autopilot import install as install_autopilot

autopilot = install_autopilot(sys.modules[__name__])

from .visual_watch import install as install_visual_watch

visual_watch = install_visual_watch(sys.modules[__name__])

from .media_reports import install as install_media_reports
media_reports = install_media_reports(sys.modules[__name__])

from .case_overview import install as install_case_overview
from .case_briefing import install as install_case_briefing
from .case_breakdown import install as install_case_breakdown
from .dossier_verification import install as install_dossier_verification
from .automatic_workspaces import install as install_automatic_workspaces

case_overview = install_case_overview(sys.modules[__name__])
case_briefing = install_case_briefing(sys.modules[__name__])
case_breakdown = install_case_breakdown(sys.modules[__name__])
dossier_verification = install_dossier_verification(sys.modules[__name__])
automatic_workspaces = install_automatic_workspaces(sys.modules[__name__])

# Production: one loopback service serves the compiled UI and API.
from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
