"""Preserved dossier claims, exact supporting passages and explicit verification gaps."""

import json
import re
import threading
from collections import Counter
from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from pathlib import Path


def split_claims(text):
    """Keep complete paragraphs/bullets with source line numbers; retain compound-claim limits."""
    section, subsection, pending, start, claims = "Introduction", "", [], 1, []

    def flush():
        """Persist a paragraph-sized claim unit without rewriting its meaning."""
        if pending:
            body = " ".join(pending).strip()
            if len(body) > 45 and not body.startswith("|"):
                claims.append(
                    {
                        "section": section,
                        "subsection": subsection,
                        "text": body,
                        "line": start,
                        "unit": "Original paragraph or bullet; may contain multiple assertions",
                    }
                )
            pending.clear()

    for line_number, line in enumerate(text.splitlines(), 1):
        value = line.strip()
        if value.startswith("## "):
            flush()
            section = value[3:]
            subsection = ""
        elif value.startswith("### "):
            flush()
            subsection = value[4:]
        elif (
            not value
            or value == "---"
            or value.startswith("# ")
            or value.startswith("**Date:")
            or value.startswith("**Subject:")
            or value.startswith("**Classification:")
            or value.startswith("**Compiled")
        ):
            flush()
        elif value.startswith("- "):
            flush()
            start = line_number
            pending.append(value[2:])
            flush()
        elif value.startswith("|"):
            flush()
        else:
            if not pending:
                start = line_number
            pending.append(value)
    flush()
    return claims


def install(core):
    """Store the import and keep candidate retrieval separate from verification."""
    with core.db() as db:
        db.executescript("""CREATE TABLE IF NOT EXISTS dossiers(id TEXT PRIMARY KEY,evidence_id TEXT,created TEXT,data TEXT);
CREATE TABLE IF NOT EXISTS dossier_claims(id TEXT PRIMARY KEY,dossier_id TEXT,sequence INTEGER,data TEXT,review TEXT,candidates TEXT);
""")

    class Import(BaseModel):
        evidence_id: str = Field(max_length=100)
        title: str = Field(default="Expanded user-supplied dossier", max_length=200)

    @core.app.post("/api/dossiers/import")
    def ingest(value: Import):
        """Import preserved user text as secondary investigative material, never verified facts."""
        e, meta, _ = core.forensics["source"](value.evidence_id)
        if meta.get("retrieval_method") != "User upload":
            raise HTTPException(422, "A preserved user upload is required")
        did = "DOSSIER-" + e["sha256"][:20]
        if core.rows("SELECT id FROM dossiers WHERE id=?", (did,)):
            return {"id": did, "deduplicated": True}
        units = split_claims(e["text"])
        with core.db() as db:
            db.execute(
                "INSERT INTO dossiers VALUES(?,?,?,?)",
                (
                    did,
                    e["id"],
                    core.now(),
                    json.dumps(
                        {
                            "title": value.title,
                            "sha256": e["sha256"],
                            "classification": "SECONDARY INVESTIGATIVE DOSSIER",
                            "claim_units": len(units),
                        }
                    ),
                ),
            )
            for i, unit in enumerate(units):
                cid = did + f"-{i:03}"
                db.execute(
                    "INSERT INTO dossier_claims VALUES(?,?,?,?,?,?)",
                    (cid, did, i, json.dumps(unit), None, "[]"),
                )
            # Original bytes remain immutable; this classification describes their evidentiary role.
            meta["source_class"] = "SECONDARY INVESTIGATIVE DOSSIER"
            meta["claim_verification"] = "NOT VERIFIED BY IMPORT"
            db.execute(
                "UPDATE evidence SET status=?,metadata=? WHERE id=?",
                ("SECONDARY SOURCE", json.dumps(meta), e["id"]),
            )
        core.log(
            "dossier_imported",
            {
                "id": did,
                "source": e["id"],
                "claim_units": len(units),
                "classification": "SECONDARY SOURCE",
            },
        )
        return {
            "id": did,
            "claim_units": len(units),
            "classification": "SECONDARY SOURCE",
        }

    def check_review(review):
        """Validate every supporting quote and hash; a secondary dossier cannot verify itself."""
        if not review:
            return None
        value = json.loads(review) if isinstance(review, str) else review
        proof = []
        for citation in value.get("proof", []):
            try:
                e, meta, digest = core.forensics["source"](citation["evidence_id"])
            except (ValueError, OSError):
                return {
                    "status": "SUPPORT UNAVAILABLE",
                    "analysis": "A cited original or derivative failed integrity verification.",
                    "proof": [],
                }
            if (
                e["status"] == "SECONDARY SOURCE"
                or meta.get("source_class") == "SECONDARY INVESTIGATIVE DOSSIER"
                or citation.get("sha256") != e["sha256"]
                or citation.get("quote", "") not in e["text"]
                or len(citation.get("quote", "").strip()) < 8
            ):
                return {
                    "status": "SUPPORT UNAVAILABLE",
                    "analysis": "The saved citation is stale, missing, or secondary dossier material.",
                    "proof": [],
                }
            proof.append({**citation, "title": e["title"]})
        if not proof:
            return (
                {**value, "proof": []}
                if value.get("status") == "NOT VERIFIED"
                else None
            )
        return {**value, "proof": proof}

    class Review(BaseModel):
        status: Literal["SUPPORTED", "PARTIALLY SUPPORTED", "DISPUTED", "NOT VERIFIED"]
        analysis: str = Field(min_length=20, max_length=8000)
        proof: list[dict] = Field(default_factory=list, max_length=20)
        origin: str = Field(default="AI-assisted source review", max_length=120)

    @core.app.post("/api/dossiers/claims/{claim_id}/review")
    def review_claim(claim_id: str, value: Review):
        """Save an explicit source-based assessment, not a search-similarity approval."""
        if not core.rows("SELECT id FROM dossier_claims WHERE id=?", (claim_id,)):
            raise HTTPException(404, "Dossier claim not found")
        checked = check_review(value.model_dump())
        if not checked or checked["status"] == "SUPPORT UNAVAILABLE":
            raise HTTPException(
                422, "Every assessment needs valid original-source quotes and hashes"
            )
        core.execute(
            "UPDATE dossier_claims SET review=? WHERE id=?",
            (value.model_dump_json(), claim_id),
        )
        core.log(
            "dossier_claim_assessed",
            {"claim_id": claim_id, "status": value.status, "origin": value.origin},
        )
        return checked

    @core.app.get("/api/dossiers/verification")
    def overview():
        """Expose every imported claim and its real proof, not the dossier's claimed certainty."""
        dossiers = []
        for r in core.rows("SELECT * FROM dossiers ORDER BY created DESC"):
            claims = []
            for row in core.rows(
                "SELECT * FROM dossier_claims WHERE dossier_id=? ORDER BY sequence",
                (r["id"],),
            ):
                claim = json.loads(row["data"])
                review = check_review(row["review"])
                claims.append(
                    {
                        "id": row["id"],
                        **claim,
                        "status": review["status"] if review else "NOT VERIFIED",
                        "analysis": review["analysis"]
                        if review
                        else "The uploaded dossier asserts this. No completed source-based verification is attached to this entire claim unit.",
                        "proof": review["proof"] if review else [],
                        "reviewed": bool(review),
                        "candidates": json.loads(row["candidates"] or "[]"),
                    }
                )
            counts = Counter(c["status"] for c in claims)
            job_ids = json.loads(r["data"]).get("source_job_ids", [])
            acquisitions = []
            for jid in job_ids:
                jobs = core.rows(
                    "SELECT id,url,status,error,evidence_id FROM jobs WHERE id=?",
                    (jid,),
                )
                if jobs:
                    acquisitions.append(jobs[0])
            dossiers.append(
                {
                    "id": r["id"],
                    "evidence_id": r["evidence_id"],
                    "created": r["created"],
                    **json.loads(r["data"]),
                    "claims": claims,
                    "counts": dict(counts),
                    "acquisitions": acquisitions,
                }
            )
        return {
            "dossiers": dossiers,
            "standard": "Claim units preserve original paragraphs/bullets. Partial support does not verify every assertion. Candidate search passages are leads, not proof; verified status requires an explicit source-based review.",
        }

    class Sources(BaseModel):
        job_ids: list[str] = Field(max_length=100)

    @core.app.post("/api/dossiers/{dossier_id}/sources")
    def attach_sources(dossier_id: str, value: Sources):
        """Attach existing source-acquisition jobs, preserving failures as visible outcomes."""
        rows = core.rows("SELECT data FROM dossiers WHERE id=?", (dossier_id,))
        if not rows:
            raise HTTPException(404, "Dossier not found")
        if any(
            not core.rows("SELECT id FROM jobs WHERE id=?", (jid,))
            for jid in value.job_ids
        ):
            raise HTTPException(422, "Source job not found")
        data = json.loads(rows[0]["data"])
        data["source_job_ids"] = list(dict.fromkeys(value.job_ids))
        core.execute(
            "UPDATE dossiers SET data=? WHERE id=?", (json.dumps(data), dossier_id)
        )
        return {"source_jobs": len(data["source_job_ids"])}

    @core.app.get("/api/delivery/gaps")
    def gaps():
        """Return the full requested-scope audit without claiming pending integrations are complete."""
        path = Path(__file__).resolve().parents[1] / "IMPLEMENTATION_GAPS.json"
        if not path.is_file():
            raise HTTPException(404, "Implementation audit not yet saved")
        return json.loads(path.read_text())

    def refresh_candidates():
        """Automatically retrieve bounded passages when the collection changes; never auto-approve claims."""
        pending = core.rows(
            "SELECT id,data FROM dossier_claims WHERE review IS NULL OR json_extract(review,'$.status') IN ('NOT VERIFIED','PARTIALLY SUPPORTED') ORDER BY sequence"
        )
        for row in pending:
            if core.stopping.is_set():
                break
            value = json.loads(row["data"])
            text = value["text"]
            words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}|\d{6,}", text)
            stop = {
                "that",
                "this",
                "from",
                "with",
                "were",
                "have",
                "been",
                "which",
                "according",
                "allen",
                "cole",
                "would",
                "their",
                "there",
                "about",
                "after",
                "before",
                "said",
                "into",
                "also",
                "source",
                "investigation",
            }
            terms = list(dict.fromkeys(w for w in words if w.casefold() not in stop))[
                :6
            ]
            if not terms:
                continue
            query = " OR ".join('"' + term.replace('"', "") + '"' for term in terms)
            matches = core.rows(
                "SELECT e.id,e.title,snippet(evidence_fts,2,'','', ' … ',45) AS quote FROM evidence_fts JOIN evidence e ON e.id=evidence_fts.id WHERE evidence_fts MATCH ? AND e.path IS NOT NULL AND e.status='ORIGINAL VERIFIED' ORDER BY bm25(evidence_fts) LIMIT 3",
                (query,),
            )
            candidates = [
                {
                    "evidence_id": m["id"],
                    "title": m["title"],
                    "excerpt": m["quote"],
                    "state": "SEARCH LEAD · DOES NOT VERIFY CLAIM",
                }
                for m in matches
            ]
            core.execute(
                "UPDATE dossier_claims SET candidates=? WHERE id=?",
                (json.dumps(candidates), row["id"]),
            )

    def loop():
        """Watch for new source material without requiring a user to rerun verification searches."""
        fingerprint = None
        while not core.stopping.is_set():
            try:
                core.heartbeat("dossier-verification")
                state = core.rows(
                    "SELECT count(*) n,max(created) newest FROM evidence"
                )[0]
                marker = (
                    state["n"],
                    state["newest"],
                    core.rows("SELECT count(*) n FROM dossier_claims")[0]["n"],
                )
                if marker != fingerprint:
                    refresh_candidates()
                    fingerprint = marker
            except Exception as error:
                core.log(
                    "dossier_candidate_refresh_failed", {"reason": str(error)[:250]}
                )
            core.stopping.wait(30)

    @core.app.on_event("startup")
    def startup():
        """Start the bounded source-matching worker; assessments stay distinct from matches."""
        threading.Thread(target=loop, name="dossier-verification", daemon=True).start()

    return {
        "overview": overview,
        "check_review": check_review,
        "refresh_candidates": refresh_candidates,
    }
