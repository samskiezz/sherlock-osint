"""Automatic compatible-tool fan-out, applicability receipts and changed-source monitoring."""

import hashlib
import json
import re
import threading
from typing import Any
from fastapi import HTTPException
from pydantic import BaseModel, Field
from .automation import Workflow, Step, catalogue

KEYED = {
    "vigenere",
    "beaufort",
    "affine",
    "rail_fence",
    "columnar",
    "xor",
    "playfair",
    "hill2",
    "bifid",
    "gronsfeld",
    "autokey",
    "adfgx",
    "nth_letters",
}
CORPUS = {
    "tfidf_search",
    "count_matrix",
    "tfidf_similarity",
    "lsa",
    "nmf_topics",
    "lda_topics",
    "document_clusters",
    "near_duplicates",
}
TEXT = {
    "token_spans",
    "sentence_spans",
    "word_frequency",
    "bigrams",
    "trigrams",
    "character_ngrams",
    "lexical_diversity",
    "hapax_ratio",
    "character_entropy",
    "unicode_controls",
    "normalization_diff",
    "line_duplicates",
    "paragraph_duplicates",
    "urls",
    "emails",
    "dates",
    "identifiers",
    "simhash",
    "extractive_summary",
}


def profile_version(mime):
    return (
        "source-bound-image-profiles-v14"
        if (mime or "").startswith("image/")
        else "source-bound-text-profiles-v14"
    )


class Settings(BaseModel):
    """Automate analysis with resource limits, without selecting ciphers per evidence item."""

    enabled: bool = True
    include_existing: bool = True
    model_notes: bool = False
    max_new_runs_per_tick: int = Field(default=2, ge=1, le=8)


class Scan(BaseModel):
    """One explicit original or a bounded compatible case-wide pass."""

    evidence_id: str = Field(default="", max_length=100)
    limit: int = Field(default=5, ge=1, le=100)
    force: bool = False


def candidate_spans(text: str) -> list[dict]:
    """Find bounded literal encoded strings and capitalised phrases, not inferred identities."""
    result = []
    rules = {
        "hex": r"\b(?:[0-9A-Fa-f]{2}){8,1000}\b",
        "base64": r"(?<!\w)[A-Za-z0-9+/]{20,1000}={0,2}(?!\w)",
        "phrase": r"\b[A-Z][a-z]{1,24}(?:[ \t]+[A-Z][a-z]{1,24}){1,3}\b",
    }
    seen = set()
    for kind, pattern in rules.items():
        count = 0
        for m in re.finditer(pattern, text[:16000]):
            if (m.start(), m.end()) in seen:
                continue
            if kind == "base64" and not (
                re.search(r"\d|=|[+/]", m.group())
                or (re.search("[a-z]", m.group()) and re.search("[A-Z]", m.group()))
            ):
                continue
            result.append(
                {"kind": kind, "start": m.start(), "end": m.end(), "text": m.group()}
            )
            seen.add((m.start(), m.end()))
            count += 1
            if count >= 4:
                break
    return result


def install(core: Any) -> dict:
    """Create typed automatic profiles and continue processing changed acquired originals."""
    with core.db() as db:
        db.executescript("""
CREATE TABLE IF NOT EXISTS autopilot_settings(id TEXT PRIMARY KEY,data TEXT);
CREATE TABLE IF NOT EXISTS autopilot_dispatch(evidence_id TEXT,fingerprint TEXT,created TEXT,run_id TEXT,data TEXT,PRIMARY KEY(evidence_id,fingerprint));
""")
    core.execute(
        "INSERT OR IGNORE INTO autopilot_settings VALUES(?,?)",
        ("default", json.dumps(Settings().model_dump())),
    )
    gate = threading.RLock()

    def settings() -> dict:
        """Read the persisted automation preference and eligibility boundary."""
        return json.loads(
            core.rows("SELECT data FROM autopilot_settings WHERE id=?", ("default",))[
                0
            ]["data"]
        )

    def _dispatch(eid: str, force: bool = False) -> dict:
        """Automatically select compatible functions, preserving why every other tool was skipped."""
        e, meta, digest = core.forensics["source"](eid)
        config = settings()
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    eid,
                    e["sha256"],
                    digest,
                    profile_version(e["mime"]),
                    config.get("model_notes"),
                ]
            ).encode()
        ).hexdigest()
        previous = core.rows(
            "SELECT * FROM autopilot_dispatch WHERE evidence_id=? AND fingerprint=?",
            (eid, fingerprint),
        )
        active_previous = previous and core.rows(
            "SELECT id FROM automation_runs WHERE id=? AND status IN ('QUEUED','RUNNING','PAUSED')",
            (previous[0]["run_id"],),
        )
        if previous and (not force or active_previous):
            return {
                **previous[0],
                "data": json.loads(previous[0]["data"]),
                "deduplicated": True,
            }
        text = e["text"]
        window = min(4000, len(text))
        steps = [Step(id="verify", tool="evidence.verify", inputs={"evidence_id": eid})]
        steps.append(
            Step(
                id="controlled_cipher_screen",
                tool="forensics.screen",
                depends_on=["verify"],
                inputs={"evidence_id": eid},
                on_failure="continue",
            )
        )
        selected = {"evidence.verify", "forensics.screen"}
        skipped = {}
        candidates = candidate_spans(text)
        if text.strip():
            for method in sorted(TEXT):
                if (
                    method == "extractive_summary"
                    and len(re.findall(r"[^.!?\n]+[.!?]", text[:window])) < 2
                ):
                    skipped["text." + method] = "Needs at least two source sentences"
                    continue
                steps.append(
                    Step(
                        id="text_" + method,
                        tool="text." + method,
                        depends_on=["verify"],
                        inputs={"evidence_id": eid, "text_end": window},
                        on_failure="continue",
                    )
                )
                selected.add("text." + method)
            # Automatic inferred recipes use encoded literal spans, never a user-selected cipher.
            for i, c in enumerate(
                [c for c in candidates if c["kind"] in ("hex", "base64")][:3]
            ):
                steps.append(
                    Step(
                        id="auto_decode_" + str(i),
                        tool="decoder.auto",
                        depends_on=["verify"],
                        inputs={
                            "evidence_id": eid,
                            "text_start": c["start"],
                            "text_end": c["end"],
                        },
                        on_failure="continue",
                    )
                )
                selected.add("decoder.auto")
            if "decoder.auto" not in selected:
                skipped["decoder.auto"] = (
                    "No bounded structurally encoded candidate was detected in the scanned source window"
                )
            for i, c in enumerate([c for c in candidates if c["kind"] == "phrase"][:4]):
                steps.append(
                    Step(
                        id="gematria_" + str(i),
                        tool="gematria.all",
                        depends_on=["verify"],
                        inputs={
                            "evidence_id": eid,
                            "text_start": c["start"],
                            "text_end": c["end"],
                            "seed": 42,
                        },
                        on_failure="continue",
                    )
                )
                selected.add("gematria.all")
            if "gematria.all" not in selected:
                steps.append(
                    Step(
                        id="gematria_text",
                        tool="gematria.all",
                        depends_on=["verify"],
                        inputs={"evidence_id": eid, "text_end": min(200, len(text))},
                        on_failure="continue",
                    )
                )
                selected.add("gematria.all")
            # A corpus is built only from actual attested originals; numeric baselines and labels are never invented.
            corpus = []
            source_ids = []
            for row in core.rows(
                "SELECT id FROM evidence WHERE path IS NOT NULL AND id!=? ORDER BY created DESC LIMIT 40",
                (eid,),
            ):
                try:
                    other, om, od = core.forensics["source"](row["id"])
                    if other["text"].strip():
                        corpus.append(other["text"][:1500])
                        source_ids.append(
                            {
                                "evidence_id": other["id"],
                                "original_sha256": other["sha256"],
                                "text_sha256": od,
                                "text_range": [0, min(1500, len(other["text"]))],
                            }
                        )
                except ValueError:
                    continue
                if len(corpus) >= 8:
                    break
            if len(corpus) >= 2:
                for method in sorted(CORPUS):
                    steps.append(
                        Step(
                            id="corpus_" + method,
                            tool="text." + method,
                            depends_on=["verify"],
                            inputs={
                                "evidence_id": eid,
                                "text_end": window,
                                "query": e["title"][:120],
                                "corpus_sources": source_ids,
                            },
                            on_failure="continue",
                        )
                    )
                    selected.add("text." + method)
            if config.get("model_notes"):
                steps.append(
                    Step(
                        id="model_review",
                        tool="model.cited_note",
                        depends_on=["verify"],
                        inputs={
                            "evidence_id": eid,
                            "question": "Describe what this original directly states. Separate interpretation, missing evidence, and conventional explanations.",
                        },
                        on_failure="continue",
                    )
                )
                selected.add("model.cited_note")
        if e["mime"].startswith("image/"):
            steps.append(
                Step(
                    id="visual_prepare",
                    tool="visual.prepare",
                    depends_on=["verify"],
                    inputs={"evidence_id": eid},
                    on_failure="continue",
                )
            )
            steps.append(
                Step(
                    id="visual_search",
                    tool="visual.search",
                    depends_on=["visual_prepare"],
                    inputs={"evidence_id": eid, "limit": 20},
                    on_failure="continue",
                )
            )
            selected.update({"visual.prepare", "visual.search"})
        coverage = []
        for tool in catalogue():
            if tool["id"] in selected:
                state = "SCHEDULED"
                reason = "Compatible automatically selected source analysis"
            else:
                state = "NOT_APPLICABLE"
                reason = skipped.get(
                    tool["id"],
                    "Needs an explicit compatible dataset, source type, baseline, comparison design, key, target query or model setting. No data, labels or keys were invented.",
                )
            coverage.append({"tool": tool["id"], "state": state, "reason": reason})
        plan = Workflow(
            name="Automatic parallel triage · " + e["title"][:95],
            objective="Automatically execute compatible source-bound analysis and retain applicability, failed attempts and uncertainty across the complete tool catalogue.",
            authorisation="User requested automatic parallel investigation of acquired public-source evidence",
            parallelism=3,
            max_seconds=1200,
            steps=steps,
        )
        saved = core.automation["create"](plan)
        run = core.automation["launch"](
            saved["id"], dedup=None if force else "autopilot:" + fingerprint
        )
        record = {
            "coverage": coverage,
            "candidates": candidates,
            "steps": len(steps),
            "compatible_tools": len(selected),
            "catalogue_tools": len(coverage),
            "profile_version": profile_version(e["mime"]),
            "source_sha256": e["sha256"],
            "text_sha256": digest,
            "text_scan_limit": 16000,
            "policy": "Automatic type-compatible fan-out, not blind application of all algorithms to inappropriate data. Gematria and decoded candidates never establish predictions or identity. Dataset-dependent methods remain visibly unavailable until the relevant data exists.",
        }
        core.execute(
            "INSERT OR REPLACE INTO autopilot_dispatch VALUES(?,?,?,?,?)",
            (eid, fingerprint, core.now(), run["id"], json.dumps(record)),
        )
        core.log(
            "autopilot_dispatched",
            {"evidence_id": eid, "run_id": run["id"], "steps": len(steps)},
        )
        return {
            "evidence_id": eid,
            "fingerprint": fingerprint,
            "run_id": run["id"],
            "data": record,
        }

    def dispatch(eid: str, force: bool = False) -> dict:
        # Extraction and the recovery scan may discover the same original together.
        with gate:
            return _dispatch(eid, force)

    def on_extracted(eid: str) -> dict:
        """Queue analysis immediately; the periodic scan recovers a full queue/crash."""
        config = settings()
        if not config.get("enabled"):
            return {"status": "PAUSED"}
        if config.get("created_after"):
            source = core.rows("SELECT created FROM evidence WHERE id=?", (eid,))
            if source and source[0]["created"] < config["created_after"]:
                return {"status": "OUTSIDE_SCOPE"}
        return dispatch(eid)

    @core.app.get("/api/autopilot")
    def overview() -> dict:
        """Expose true compatible-tool coverage, progress and unattended processing state."""
        return {
            "settings": settings(),
            "dispatches": [
                {**r, "data": json.loads(r["data"])}
                for r in core.rows(
                    "SELECT * FROM autopilot_dispatch ORDER BY created DESC LIMIT 100"
                )
            ],
            "parallelism": {
                "global_analytical_actions": 4,
                "ready_steps_per_run": 3,
                "independent_workflow_batches": 4,
                "local_generation_calls": 1,
            },
            "policy": "New and existing acquired originals are scanned automatically. Dependencies, evidence integrity and resource bounds are preserved. Numerical coincidences and resemblance remain provisional leads.",
        }

    @core.app.put("/api/autopilot/settings")
    def configure(value: Settings) -> dict:
        """Start/stop automatic compatible analysis without choosing ciphers per item."""
        data = value.model_dump()
        if not value.include_existing:
            data["created_after"] = core.now()
        core.execute(
            "UPDATE autopilot_settings SET data=? WHERE id=?",
            (json.dumps(data), "default"),
        )
        return value.model_dump()

    @core.app.post("/api/autopilot/scan")
    def scan(value: Scan) -> dict:
        """Start a bounded immediate automatic pass; routine background discovery continues."""
        if value.force and not value.evidence_id:
            raise HTTPException(422, "Retry one explicit source at a time")
        if not gate.acquire(blocking=False):
            return {"status": "ALREADY_SCANNING", "dispatches": []}
        results = []
        try:
            # Check compact stored fingerprints before hashing originals. A newest-500
            # window starved older evidence forever once those 500 were dispatched.
            known = {
                (r["evidence_id"], r["fingerprint"])
                for r in core.rows(
                    "SELECT evidence_id,fingerprint FROM autopilot_dispatch"
                )
            }
            config = settings()
            rows = (
                [{"id": value.evidence_id}]
                if value.evidence_id
                else core.rows(
                    "SELECT id,sha256,mime,created,json_extract(metadata,'$.derivative_hashes.\"text.txt\"') text_digest FROM evidence WHERE path IS NOT NULL AND json_extract(metadata,'$.processing_status')='COMPLETE' ORDER BY created,id"
                )
            )
            for row in rows:
                if not value.evidence_id:
                    if (
                        config.get("created_after")
                        and row["created"] < config["created_after"]
                    ):
                        continue
                    fingerprint = hashlib.sha256(
                        json.dumps(
                            [
                                row["id"],
                                row["sha256"],
                                row["text_digest"],
                                profile_version(row["mime"]),
                                config.get("model_notes"),
                            ]
                        ).encode()
                    ).hexdigest()
                    if (row["id"], fingerprint) in known:
                        continue
                try:
                    result = dispatch(row["id"], force=value.force)
                    if not result.get("deduplicated"):
                        results.append(result)
                except (ValueError, HTTPException) as ex:
                    if value.evidence_id:
                        raise HTTPException(
                            422, str(ex.detail if isinstance(ex, HTTPException) else ex)
                        ) from ex
                if len(results) >= value.limit:
                    break
            return {"status": "QUEUED", "dispatches": results}
        finally:
            gate.release()

    def loop() -> None:
        """Continue analysis without a repeated user instruction or per-method selection."""
        while not core.stopping.wait(15):
            config = settings()
            if not config.get("enabled"):
                continue
            try:
                active = core.rows(
                    "SELECT id FROM automation_runs WHERE status IN ('QUEUED','RUNNING') LIMIT 13"
                )
                if len(active) < 12:
                    scan(Scan(limit=config.get("max_new_runs_per_tick", 2)))
                core.heartbeat(
                    "autopilot",
                    "Automatically selecting compatible functions and source-bound parallel branches",
                )
            except Exception as ex:
                core.log("autopilot_worker_error", {"error": type(ex).__name__})

    @core.app.on_event("startup")
    def start() -> None:
        """Resume automatic evidence fan-out from persistent dispatch fingerprints."""
        threading.Thread(target=loop, daemon=True).start()

    return {
        "dispatch": dispatch,
        "overview": overview,
        "settings": settings,
        "scan": scan,
        "on_extracted": on_extracted,
    }
