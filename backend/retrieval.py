"""Continuously index attested extracts in real BM25/vector stores with exact citations."""

import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time
from typing import Any
import uuid

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field

VERSION = "passages-2-char180-mean"
COLLECTION = "sherlock_passages_v9"
INDEX = "sherlock-passages-v9"
CHUNK_SIZE = 700
OVERLAP = 100
MAX_CHUNKS = 2000


def split_passages(text: str) -> list[dict[str, Any]]:
    """Split exact Unicode slices without crossing explicit processor page boundaries."""
    markers = list(re.finditer(r"\n\[Page (\d+)\]\n", text))
    sections = []
    if markers:
        if markers[0].start():
            sections.append((0, markers[0].start(), None))
        for i, marker in enumerate(markers):
            sections.append(
                (
                    marker.end(),
                    markers[i + 1].start() if i + 1 < len(markers) else len(text),
                    int(marker.group(1)),
                )
            )
    else:
        sections = [(0, len(text), None)]
    result = []
    for start, end, page in sections:
        for offset in range(start, end, CHUNK_SIZE - OVERLAP):
            stop = min(end, offset + CHUNK_SIZE)
            quote = text[offset:stop]
            if quote.strip():
                result.append(
                    {"start": offset, "end": stop, "page": page, "text": quote}
                )
            if stop == end:
                break
    return result


IDENTIFIERS = {
    "PATENT": r"\b(?:US|EP|WO)\s?\d{7,13}(?:[AB]\d)?\b",
    "DOI": r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+",
    "PUBLIC_HANDLE": r"(?<![\w@])@[A-Za-z0-9_]{2,30}\b",
    "ISO_DATE": r"\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b",
    "SHA256": r"\b[a-fA-F0-9]{64}\b",
}


def identifiers(text: str) -> list[dict[str, Any]]:
    """Return literal identifier occurrences, never inferred people or account ownership."""
    found = []
    for kind, pattern in IDENTIFIERS.items():
        for match in re.finditer(pattern, text):
            value = match.group().rstrip(".,;")
            normalized = (
                re.sub(r"\s+", "", value).upper()
                if kind == "PATENT"
                else value.lower()
                if kind in ("SHA256", "DOI")
                else value
            )
            found.append(
                {
                    "kind": kind,
                    "value": value,
                    "normalized": normalized,
                    "start": match.start(),
                    "end": match.start() + len(value),
                }
            )
            if len(found) >= 5000:
                return found
    return found


def reciprocal_rank_fusion(
    rankings: list[list[str]], limit: int = 30
) -> list[tuple[str, float]]:
    """Combine independent ranked lists using RRF k=60; scores are not probabilities."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(dict.fromkeys(ranking), 1):
            scores[key] = scores.get(key, 0.0) + 1 / (60 + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:limit]


def configuration(root: Path) -> dict[str, Any]:
    """Read private service credentials without exposing them in results or logs."""
    p = root / "retrieval.json"
    if not p.is_file() or p.is_symlink() or p.stat().st_mode & 0o077:
        raise ValueError("Retrieval configuration absent or permissions invalid")
    cfg = json.loads(p.read_text())
    expected = {
        "qdrant_url": "http://127.0.0.1:56333",
        "elastic_url": "http://127.0.0.1:59200",
        "ollama_url": "http://127.0.0.1:11434",
    }
    if (
        any(cfg.get(k) != v for k, v in expected.items())
        or cfg.get("embedding_model") != "all-minilm:22m"
    ):
        raise ValueError(
            "Only the configured loopback retrieval services are supported"
        )
    return cfg


class Services:
    """Bounded local-only HTTP adapters; no untrusted URL is accepted."""

    def __init__(self, root: Path):
        """Load the reviewed embedding manifest and configured private service credentials."""
        self.cfg = configuration(root)
        manifest = root.parent / "artifacts/embedding-model-integrity-v9.json"
        record = json.loads(manifest.read_text())
        self.digest = record["manifest_sha256"]
        self.client = httpx.Client(trust_env=False, timeout=90)

    def close(self) -> None:
        """Close local HTTP connections."""
        self.client.close()

    def q(self, method: str, path: str, **kwargs: Any) -> Any:
        """Issue an authenticated local Qdrant request."""
        response = self.client.request(
            method,
            self.cfg["qdrant_url"] + path,
            headers={"api-key": self.cfg["qdrant_key"]},
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def es(self, method: str, path: str, **kwargs: Any) -> Any:
        """Issue an authenticated local Elasticsearch request."""
        response = self.client.request(
            method,
            self.cfg["elastic_url"] + path,
            auth=("elastic", self.cfg["elastic_password"]),
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def validate_model(self) -> None:
        """Reject a replaced model tag rather than mixing incompatible vector spaces."""
        r = self.client.get(self.cfg["ollama_url"] + "/api/tags")
        r.raise_for_status()
        actual = next(
            (
                m
                for m in r.json().get("models", [])
                if m["name"] == self.cfg["embedding_model"]
            ),
            None,
        )
        if not actual or actual["digest"] != self.digest:
            raise ValueError(
                "Embedding manifest does not match the reviewed installed model"
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed bounded passages with the verified local 384-dimensional MiniLM model."""
        # A 180-character window fits the model's 256-token WordPiece budget.
        # Embed every window and normalise the mean, preserving the entire passage.
        windows = []
        spans = []
        for text in texts:
            start = len(windows)
            windows.extend(
                [text[i : i + 180] for i in range(0, len(text), 180)] or [" "]
            )
            spans.append((start, len(windows)))
        r = self.client.post(
            self.cfg["ollama_url"] + "/api/embed",
            json={
                "model": self.cfg["embedding_model"],
                "input": windows,
                "truncate": False,
                "keep_alive": "5m",
            },
        )
        r.raise_for_status()
        raw = r.json()["embeddings"]
        if len(raw) != len(windows) or any(
            len(v) != 384 or not all(math.isfinite(x) for x in v) for v in raw
        ):
            raise ValueError("Invalid embedding shape or values")
        result = []
        for start, end in spans:
            vector = [
                sum(raw[i][j] for i in range(start, end)) / (end - start)
                for j in range(384)
            ]
            norm = math.sqrt(sum(x * x for x in vector))
            if norm <= 0:
                raise ValueError("Zero embedding vector")
            result.append([x / norm for x in vector])
        return result

    def ensure(self) -> None:
        """Create real vector and BM25 collections with explicit searchable mappings."""
        self.validate_model()
        collections = self.q("GET", "/collections")["result"]["collections"]
        if COLLECTION not in [x["name"] for x in collections]:
            self.q(
                "PUT",
                "/collections/" + COLLECTION,
                json={"vectors": {"size": 384, "distance": "Cosine"}},
            )
        existing = self.client.head(
            self.cfg["elastic_url"] + "/" + INDEX,
            auth=("elastic", self.cfg["elastic_password"]),
        )
        if existing.status_code == 404:
            self.es(
                "PUT",
                "/" + INDEX,
                json={
                    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                    "mappings": {
                        "dynamic": "strict",
                        "properties": {
                            "text": {"type": "text"},
                            "title": {"type": "text"},
                            "evidence_id": {"type": "keyword"},
                            "model_digest": {"type": "keyword"},
                        },
                    },
                },
            )
        else:
            existing.raise_for_status()


def install(core: Any) -> dict[str, Any]:
    """Register persistent indexing, exact-source retrieval and identifier-link APIs."""
    core.execute(
        "CREATE TABLE IF NOT EXISTS retrieval_documents(evidence_id TEXT PRIMARY KEY,fingerprint TEXT,status TEXT,updated TEXT,data TEXT)"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS retrieval_chunks(id TEXT PRIMARY KEY,evidence_id TEXT,data TEXT)"
    )
    core.execute(
        "CREATE INDEX IF NOT EXISTS retrieval_chunk_evidence ON retrieval_chunks(evidence_id)"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS retrieval_identifiers(evidence_id TEXT,kind TEXT,normalized TEXT,data TEXT)"
    )
    core.execute(
        "CREATE INDEX IF NOT EXISTS retrieval_identifier_value ON retrieval_identifiers(kind,normalized)"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS retrieval_queries(id TEXT PRIMARY KEY,created TEXT,data TEXT)"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS retrieval_requests(evidence_id TEXT PRIMARY KEY,created TEXT)"
    )
    guard = threading.Lock()
    stop = threading.Event()
    state = {"running": False, "last_cycle": None, "error": None, "changed": 0}

    def status() -> dict[str, Any]:
        """Return observed inventory and worker state without any service credentials."""
        return {
            **state,
            "documents": core.rows(
                "SELECT status,count(*) count FROM retrieval_documents GROUP BY status"
            ),
            "chunks": core.rows("SELECT count(*) count FROM retrieval_chunks")[0][
                "count"
            ],
            "identifier_occurrences": core.rows(
                "SELECT count(*) count FROM retrieval_identifiers"
            )[0]["count"],
            "pending_priority_sources": core.rows(
                "SELECT evidence_id,created FROM retrieval_requests ORDER BY created LIMIT 20"
            ),
            "model": "all-minilm:22m",
            "dimensions": 384,
            "stores": [
                "Elasticsearch BM25",
                "Qdrant cosine vectors",
                "SQLite citation records",
            ],
            "interval_seconds": 60,
            "chunk_characters": CHUNK_SIZE,
            "overlap_characters": OVERLAP,
            "max_chunks_per_document": MAX_CHUNKS,
            "embedding_recipe": VERSION,
            "scope": "Acquired originals with attested extracted text. Notes are excluded. Similarity and shared identifiers are leads, not verified relationships.",
        }

    def fingerprint(e: dict[str, Any], digest: str, model: str) -> str:
        """Bind indexing to both source hashes, model identity and segmentation parameters."""
        return hashlib.sha256(
            json.dumps(
                [e["id"], e["sha256"], digest, model, VERSION, CHUNK_SIZE, OVERLAP]
            ).encode()
        ).hexdigest()

    def index_one(service: Services, eid: str) -> bool:
        """Verify original/derivative integrity and atomically commit a complete citation index."""
        e, meta, digest = core.forensics["source"](eid)
        fp = fingerprint(e, digest, service.digest)
        previous = core.rows(
            "SELECT * FROM retrieval_documents WHERE evidence_id=?", (eid,)
        )
        if (
            previous
            and previous[0]["fingerprint"] == fp
            and previous[0]["status"] == "COMPLETE"
        ):
            return False
        core.execute(
            "INSERT INTO retrieval_documents VALUES(?,?,?,?,?) ON CONFLICT(evidence_id) DO UPDATE SET fingerprint=excluded.fingerprint,status=excluded.status,updated=excluded.updated,data=excluded.data",
            (eid, fp, "RUNNING", core.now(), "{}"),
        )
        chunks = split_passages(e["text"])
        all_count = len(chunks)
        chunks = chunks[:MAX_CHUNKS]
        common = {
            "evidence_id": eid,
            "title": e["title"],
            "original_sha256": e["sha256"],
            "text_sha256": digest,
            "source_url": e["url"],
            "acquisition_status": e["status"],
            "model_digest": service.digest,
            "fingerprint": fp,
            "embedding_recipe": VERSION,
        }
        for chunk in chunks:
            chunk.update(common)
            chunk["id"] = str(
                uuid.uuid5(uuid.NAMESPACE_URL, fp + ":" + str(chunk["start"]))
            )
        try:
            service.q(
                "POST",
                f"/collections/{COLLECTION}/points/delete?wait=true",
                json={
                    "filter": {
                        "must": [{"key": "evidence_id", "match": {"value": eid}}]
                    }
                },
            )
            service.es(
                "POST",
                "/" + INDEX + "/_delete_by_query?refresh=true",
                json={"query": {"term": {"evidence_id": eid}}},
            )
            for start in range(0, len(chunks), 16):
                if hasattr(core, "heartbeat"):
                    core.heartbeat(
                        "semantic-indexer",
                        {
                            "evidence_id": eid,
                            "completed_chunks": start,
                            "total_chunks": len(chunks),
                        },
                    )
                batch = chunks[start : start + 16]
                vectors = service.embed([c["text"] for c in batch])
                service.q(
                    "PUT",
                    f"/collections/{COLLECTION}/points?wait=true",
                    json={
                        "points": [
                            {
                                "id": c["id"],
                                "vector": v,
                                "payload": {
                                    "evidence_id": eid,
                                    "model_digest": service.digest,
                                },
                            }
                            for c, v in zip(batch, vectors)
                        ]
                    },
                )
                lines = []
                for chunk in batch:
                    lines.extend(
                        [
                            json.dumps(
                                {"index": {"_index": INDEX, "_id": chunk["id"]}}
                            ),
                            json.dumps(
                                {
                                    "text": chunk["text"],
                                    "title": e["title"],
                                    "evidence_id": eid,
                                    "model_digest": service.digest,
                                }
                            ),
                        ]
                    )
                result = service.es(
                    "POST",
                    "/_bulk",
                    content="\n".join(lines) + "\n",
                    headers={"Content-Type": "application/x-ndjson"},
                )
                if result.get("errors"):
                    raise ValueError("BM25 bulk indexing failed")
            mentions = identifiers(e["text"])
            summary = {
                **common,
                "chunk_count": len(chunks),
                "total_chunks": all_count,
                "truncated": all_count > len(chunks),
                "identifier_count": len(mentions),
                "extraction_truncated": bool(meta.get("extraction_truncated")),
            }
            with core.lock, core.db() as db:
                db.execute("DELETE FROM retrieval_chunks WHERE evidence_id=?", (eid,))
                db.execute(
                    "DELETE FROM retrieval_identifiers WHERE evidence_id=?", (eid,)
                )
                db.executemany(
                    "INSERT INTO retrieval_chunks VALUES(?,?,?)",
                    [(c["id"], eid, json.dumps(c)) for c in chunks],
                )
                db.executemany(
                    "INSERT INTO retrieval_identifiers VALUES(?,?,?,?)",
                    [
                        (eid, m["kind"], m["normalized"], json.dumps(m))
                        for m in mentions
                    ],
                )
                db.execute(
                    "UPDATE retrieval_documents SET status=?,updated=?,data=? WHERE evidence_id=?",
                    ("COMPLETE", core.now(), json.dumps(summary), eid),
                )
            core.log(
                "retrieval_document_indexed",
                {
                    "evidence_id": eid,
                    "sha256": e["sha256"],
                    "chunks": len(chunks),
                    "identifiers": len(mentions),
                    "model_digest": service.digest,
                },
            )
            return True
        except Exception:
            core.execute(
                "UPDATE retrieval_documents SET status=?,updated=?,data=? WHERE evidence_id=?",
                (
                    "FAILED",
                    core.now(),
                    json.dumps(
                        {
                            "failure": "Local embedding or search indexing failed; source original preserved"
                        }
                    ),
                    eid,
                ),
            )
            raise

    def tick(priority: str | None = None) -> dict[str, Any]:
        """Index a bounded batch; unchanged sources are skipped and failures remain visible."""
        if not guard.acquire(blocking=False):
            return status()
        service = None
        state.update(running=True, error=None, changed=0)
        try:
            service = Services(core.ROOT)
            service.ensure()
            requests = core.rows(
                "SELECT evidence_id FROM retrieval_requests ORDER BY created LIMIT 1"
            )
            priority = priority or (requests[0]["evidence_id"] if requests else None)
            started = time.monotonic()
            for row in core.rows(
                "SELECT id,sha256,metadata FROM evidence WHERE sha256 IS NOT NULL ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END,created ASC",
                (priority,),
            ):
                if (
                    stop.is_set()
                    or time.monotonic() - started > 110
                    or state["changed"] >= 8
                ):
                    break
                meta = json.loads(row["metadata"])
                if meta.get("processing_status") != "COMPLETE" or not meta.get(
                    "derivative_hashes", {}
                ).get("text.txt"):
                    continue
                try:
                    state["changed"] += int(index_one(service, row["id"]))
                    core.execute(
                        "DELETE FROM retrieval_requests WHERE evidence_id=?",
                        (row["id"],),
                    )
                except ValueError:
                    state["error"] = (
                        "A source failed integrity validation or an indexing bound; inspect index document failures."
                    )
                    core.execute(
                        "INSERT INTO retrieval_documents VALUES(?,?,?,?,?) ON CONFLICT(evidence_id) DO UPDATE SET status=excluded.status,updated=excluded.updated,data=excluded.data",
                        (
                            row["id"],
                            "",
                            "FAILED",
                            core.now(),
                            json.dumps(
                                {
                                    "failure": "Source integrity, model or indexing validation failed"
                                }
                            ),
                        ),
                    )
                except Exception:
                    state["error"] = (
                        "A local search service failed; indexing will retry automatically."
                    )
                    break
            service.es("POST", "/" + INDEX + "/_refresh")
        except Exception:
            state["error"] = (
                "Retrieval services unavailable or model validation failed; lexical legacy search remains available."
            )
        finally:
            if service:
                service.close()
            state.update(running=False, last_cycle=core.now())
            guard.release()
        return status()

    class Query(BaseModel):
        """Bounded investigative query over acquired evidence only."""

        query: str = Field(min_length=2, max_length=500)
        mode: str = Field(default="hybrid", pattern=r"^(hybrid|semantic|keyword)$")
        limit: int = Field(default=12, ge=1, le=30)

    def retrieve(value: Query) -> dict[str, Any]:
        """Rank attested passages and revalidate every returned original and exact quote."""
        service = Services(core.ROOT)
        try:
            service.validate_model()
            rankings = []
            if value.mode in ("keyword", "hybrid"):
                r = service.es(
                    "POST",
                    "/" + INDEX + "/_search",
                    json={
                        "size": 100,
                        "query": {
                            "bool": {
                                "must": [
                                    {
                                        "multi_match": {
                                            "query": value.query,
                                            "fields": ["text", "title^1.5"],
                                        }
                                    }
                                ],
                                "filter": [{"term": {"model_digest": service.digest}}],
                            }
                        },
                        "_source": False,
                    },
                )
                rankings.append([h["_id"] for h in r["hits"]["hits"]])
            if value.mode in ("semantic", "hybrid"):
                vector = service.embed([value.query])[0]
                r = service.q(
                    "POST",
                    f"/collections/{COLLECTION}/points/query",
                    json={
                        "query": vector,
                        "limit": 100,
                        "with_payload": False,
                        "filter": {
                            "must": [
                                {
                                    "key": "model_digest",
                                    "match": {"value": service.digest},
                                }
                            ]
                        },
                    },
                )
                rankings.append([str(h["id"]) for h in r["result"]["points"]])
            result = []
            checked: dict[str, Any] = {}
            for cid, score in reciprocal_rank_fusion(rankings, 100):
                found = core.rows(
                    "SELECT c.data,d.status FROM retrieval_chunks c JOIN retrieval_documents d ON c.evidence_id=d.evidence_id WHERE c.id=?",
                    (cid,),
                )
                if not found or found[0]["status"] != "COMPLETE":
                    continue
                chunk = json.loads(found[0]["data"])
                if chunk.get("embedding_recipe") != VERSION:
                    continue
                eid = chunk["evidence_id"]
                if eid not in checked:
                    try:
                        checked[eid] = core.forensics["source"](eid)
                    except ValueError:
                        checked[eid] = None
                if not checked[eid]:
                    continue
                e, meta, digest = checked[eid]
                if (
                    digest != chunk["text_sha256"]
                    or e["sha256"] != chunk["original_sha256"]
                    or e["text"][chunk["start"] : chunk["end"]] != chunk["text"]
                ):
                    continue
                if any(
                    c["evidence_id"] == eid
                    and abs(c["start"] - chunk["start"]) < CHUNK_SIZE
                    for c in result
                ):
                    continue
                result.append(
                    {
                        **chunk,
                        "rank_score": score,
                        "citation_verified": True,
                        "original_file_url": f"/api/evidence/{eid}/file",
                    }
                )
                if len(result) >= value.limit:
                    break
            record = {
                "id": core.uid("QUERY"),
                "verified_at": core.now(),
                "embedding_recipe": VERSION,
                "query": value.query,
                "mode": value.mode,
                "results": result,
                "model": self_model(service),
                "ranking": "Reciprocal rank fusion k=60; rank score is not confidence",
                "answer": {
                    "type": "EXTRACTIVE EVIDENCE SET",
                    "passages": [
                        {
                            "evidence_id": c["evidence_id"],
                            "quote": c["text"],
                            "page": c["page"],
                            "start": c["start"],
                            "end": c["end"],
                        }
                        for c in result
                    ],
                    "assessment": "Retrieved passages must be interpreted in context. No generated factual conclusion or identity attribution is asserted.",
                },
            }
            core.execute(
                "INSERT INTO retrieval_queries VALUES(?,?,?)",
                (record["id"], record["verified_at"], json.dumps(record)),
            )
            core.log(
                "cited_retrieval_saved",
                {
                    "id": record["id"],
                    "source_passages": len(record["results"]),
                    "mode": value.mode,
                },
            )
            return record
        finally:
            service.close()

    @core.app.get("/api/knowledge/queries")
    def query_history() -> list[dict[str, Any]]:
        """List saved query metadata without treating a result as original evidence."""
        return [
            {
                "id": r["id"],
                "created": r["created"],
                "query": json.loads(r["data"])["query"],
            }
            for r in core.rows(
                "SELECT * FROM retrieval_queries ORDER BY created DESC LIMIT 100"
            )
        ]

    @core.app.get("/api/knowledge/queries/{qid}")
    def query_record(qid: str) -> dict[str, Any]:
        """Return the exact historical source set and parameters, verified at its recorded time."""
        found = core.rows("SELECT data FROM retrieval_queries WHERE id=?", (qid,))
        if not found:
            raise HTTPException(404, "Query record not found")
        return json.loads(found[0]["data"])

    @core.app.get("/api/knowledge/status")
    def overview() -> dict[str, Any]:
        """Show continuous indexing inventory, errors and explicitly bounded coverage."""
        return {
            **status(),
            "recent_documents": [
                {**r, "data": json.loads(r["data"])}
                for r in core.rows(
                    "SELECT * FROM retrieval_documents ORDER BY updated DESC LIMIT 30"
                )
            ],
        }

    class IndexRequest(BaseModel):
        """Optional acquired source to prioritise in the next bounded cycle."""

        evidence_id: str | None = Field(default=None, max_length=100)

    @core.app.post("/api/knowledge/index")
    def run_index(value: IndexRequest) -> dict[str, Any]:
        """Trigger a bounded asynchronous indexing cycle without launching duplicate workers."""
        if value.evidence_id:
            evidence = core.get_evidence(value.evidence_id)
            if not evidence.get("sha256"):
                raise HTTPException(422, "An acquired original is required")
            core.execute(
                "INSERT INTO retrieval_requests VALUES(?,?) ON CONFLICT(evidence_id) DO UPDATE SET created=excluded.created",
                (value.evidence_id, core.now()),
            )
        if not state["running"]:
            threading.Thread(target=tick, daemon=True, name="retrieval-manual").start()
        return {
            "queued": True,
            "priority_source": value.evidence_id,
            "status": status(),
        }

    @core.app.post("/api/knowledge/search")
    def search(value: Query) -> dict[str, Any]:
        """Search BM25 and vectors while preserving exact verified source references."""
        try:
            return retrieve(value)
        except Exception as ex:
            raise HTTPException(
                503,
                "Search service unavailable; check the index status. No evidence answer was generated.",
            ) from ex

    @core.app.get("/api/knowledge/identifiers")
    def shared_identifiers(kind: str = "PATENT") -> dict[str, Any]:
        """Find literal cross-document identifiers, with per-occurrence attested spans."""
        if kind not in IDENTIFIERS:
            raise HTTPException(422, "Unknown identifier category")
        groups = core.rows(
            "SELECT i.normalized,count(DISTINCT i.evidence_id) sources FROM retrieval_identifiers i JOIN retrieval_documents d ON i.evidence_id=d.evidence_id WHERE i.kind=? AND d.status='COMPLETE' GROUP BY i.normalized HAVING count(DISTINCT i.evidence_id)>1 ORDER BY sources DESC,i.normalized LIMIT 50",
            (kind,),
        )
        results = []
        checked = {}
        for group in groups:
            occurrences = []
            for r in core.rows(
                "SELECT evidence_id,data FROM retrieval_identifiers WHERE kind=? AND normalized=? LIMIT 50",
                (kind, group["normalized"]),
            ):
                eid = r["evidence_id"]
                if eid not in checked:
                    try:
                        checked[eid] = core.forensics["source"](eid)
                    except ValueError:
                        checked[eid] = None
                if not checked[eid]:
                    continue
                e, meta, digest = checked[eid]
                m = json.loads(r["data"])
                if e["text"][m["start"] : m["end"]] != m["value"]:
                    continue
                occurrences.append(
                    {
                        **m,
                        "evidence_id": eid,
                        "title": e["title"],
                        "original_sha256": e["sha256"],
                        "text_sha256": digest,
                        "context": e["text"][max(0, m["start"] - 100) : m["end"] + 150],
                        "citation_verified": True,
                    }
                )
            if len({x["evidence_id"] for x in occurrences}) > 1:
                results.append(
                    {
                        **group,
                        "occurrences": occurrences,
                        "independent_source_count": "NOT ESTABLISHED",
                    }
                )
        return {
            "kind": kind,
            "results": results,
            "interpretation": "Literal identifier overlap only. Copies and citations are not independent corroboration, shared accounts or a verified relationship. No graph edge is created.",
        }

    def loop() -> None:
        """Continuously discover newly processed sources and retry interrupted index writes."""
        while not stop.is_set():
            tick()
            if hasattr(core, "heartbeat"):
                core.heartbeat("semantic-indexer", status())
            stop.wait(60)

    @core.app.on_event("startup")
    def startup() -> None:
        """Start the single periodic indexer with persistent records."""
        stop.clear()
        threading.Thread(target=loop, daemon=True, name="semantic-indexer").start()

    @core.app.on_event("shutdown")
    def shutdown() -> None:
        """Stop scheduling additional batches on service shutdown."""
        stop.set()

    return {
        "tick": tick,
        "status": status,
        "retrieve": retrieve,
        "Query": Query,
        "index_one": index_one,
    }


def self_model(service: Services) -> dict[str, str]:
    """Expose model identity and immutable manifest hash, never private configuration."""
    return {"name": service.cfg["embedding_model"], "manifest_sha256": service.digest}
