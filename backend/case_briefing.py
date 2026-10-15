"""Read-only, source-checked projection of saved investigation results."""

import hashlib
import json
from urllib.parse import urlparse


def build_briefing(core):
    """Surface saved conclusions without running tools or promoting model proposals."""
    findings, questions, rejected = [], [], []
    checked, seen, seen_questions = {}, set(), set()

    def cite(citation):
        """Check original bytes, attested extracted text, and the exact cited passage."""
        eid = citation.get("id") or citation.get("evidence_id")
        if eid not in checked:
            try:
                checked[eid] = core.forensics["source"](eid)
            except (ValueError, OSError):
                checked[eid] = None
        if checked[eid] is None:
            return None
        evidence, meta, _ = checked[eid]
        quote = citation.get("quote", "")
        if (
            not isinstance(quote, str)
            or len(quote.strip()) < 8
            or quote not in evidence["text"]
        ):
            return None
        expected = citation.get("sha256") or citation.get("original_sha256")
        if expected and expected != evidence["sha256"]:
            return None
        if evidence["status"] not in (
            "ORIGINAL VERIFIED",
            "ORIGINAL ACQUIRED",
            "HISTORICAL ARCHIVE",
        ):
            return None
        return {
            "evidence_id": eid,
            "title": evidence["title"],
            "quote": quote,
            "location": citation.get("location")
            or (
                f"Page {citation['page']}"
                if citation.get("page")
                else "Exact extracted passage"
            ),
            "sha256": evidence["sha256"],
            "retrieved_at": evidence["created"],
            "publication_date": meta.get("publication_date"),
            "domain": urlparse(evidence.get("url") or "").hostname or "Imported file",
        }

    def add(claim, citations, kind, context, method, limits, timestamp=None):
        """Deduplicate by content and bound originals, not analysis-run timestamps."""
        if not claim or not citations:
            return
        fingerprint = [
            claim,
            sorted((c["evidence_id"], c["sha256"], c["quote"]) for c in citations),
        ]
        key = hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True).encode()
        ).hexdigest()[:24]
        if key in seen:
            return
        seen.add(key)
        findings.append(
            {
                "id": key,
                "statement": claim,
                "kind": kind,
                "topic": context,
                "sources": citations,
                "method": method,
                "limits": limits,
                "recorded_at": timestamp or max(c["retrieved_at"] for c in citations),
            }
        )

    for board in core.rows("SELECT id,name,data FROM boards ORDER BY rowid"):
        data = json.loads(board["data"])
        for edge in data.get("edges", []):
            d = edge.get("data", {})
            claim, state = d.get("claim"), d.get("state")
            # Catalogue-download relationships belong to the evidence library.
            if d.get("proposed_by") == "Acquisition organiser":
                continue
            raw = d.get("evidence", [])
            citations = [cite(c) for c in raw]
            valid = bool(raw) and all(citations)
            if state in ("DOCUMENTED", "CORROBORATED") and valid:
                add(
                    claim,
                    citations,
                    "DOCUMENTED",
                    board["name"],
                    d.get("method"),
                    d.get("confidence"),
                )
            elif state in ("DOCUMENTED", "CORROBORATED"):
                rejected.append(
                    {
                        "claim": claim,
                        "reason": "Supporting original or exact passage failed current integrity checks.",
                    }
                )
            elif claim and claim not in seen_questions:
                seen_questions.add(claim)
                questions.append(
                    {
                        "statement": claim,
                        "topic": board["name"],
                        "state": state or "UNVERIFIED",
                        "sources": [c for c in citations if c],
                        "counterevidence": d.get("contradictions", []),
                        "reason": d.get("reason")
                        or d.get("confidence")
                        or "Supporting evidence has not established this claim.",
                    }
                )

    # Keep AI proposals out of the documented stream, even with a valid quotation.
    for run in core.rows(
        "SELECT id,updated,result FROM investigations WHERE status='COMPLETE' AND result IS NOT NULL ORDER BY created DESC LIMIT 200"
    ):
        for finding in json.loads(run["result"]).get("findings", []):
            citation = cite(finding)
            if citation:
                add(
                    finding.get("claim"),
                    [citation],
                    "AI PROPOSAL",
                    "Analyst proposals",
                    "Saved model output; exact quotation checked",
                    "Interpretation requires review; a matching quotation does not establish the claim.",
                    run["updated"],
                )

    # The visual engine already validates original and derivative hashes on reads.
    composites = set()
    for story in core.visual["explanations"]():
        d = story["data"]
        if d.get("unavailable") or d.get("composite_id") in composites:
            continue
        citations = [cite(c) for c in d.get("sources", [])]
        if not citations or not all(citations):
            continue
        composites.add(d.get("composite_id"))
        add(
            d.get("summary"),
            citations,
            "MEASURED RESULT",
            d.get("title", "Image analysis"),
            d.get("method"),
            d.get("limits"),
            story.get("created"),
        )

    rank = {"DOCUMENTED": 0, "MEASURED RESULT": 1, "AI PROPOSAL": 2}
    findings.sort(key=lambda f: f["recorded_at"], reverse=True)
    findings.sort(key=lambda f: rank[f["kind"]])
    recent, hashes = [], set()
    for e in core.rows(
        "SELECT id,title,kind,status,mime,sha256,created,url,metadata FROM evidence WHERE path IS NOT NULL ORDER BY created DESC"
    ):
        if not e["sha256"] or e["sha256"] in hashes:
            continue
        hashes.add(e["sha256"])
        meta = json.loads(e["metadata"])
        recent.append(
            {
                "evidence_id": e["id"],
                "title": e["title"],
                "mime": e["mime"],
                "retrieved_at": e["created"],
                "publication_date": meta.get("publication_date"),
                "domain": urlparse(e["url"] or "").hostname or "Imported file",
                "status": e["status"],
            }
        )
        if len(recent) == 8:
            break
    return {
        "findings": findings,
        "open_questions": questions,
        "recent_evidence": recent,
        "documented_count": sum(f["kind"] == "DOCUMENTED" for f in findings),
        "measured_count": sum(f["kind"] == "MEASURED RESULT" for f in findings),
        "proposal_count": sum(f["kind"] == "AI PROPOSAL" for f in findings),
        "last_evidence_added": recent[0]["retrieved_at"] if recent else None,
        "withheld": rejected,
        "scope": "Saved board statements, the latest 200 completed investigation reports and saved visual results. Repeated analyses and identical originals are deduplicated. Documented means a saved documented statement with a currently valid source passage, not an independent finding of guilt or identity.",
    }


def install(core):
    """Expose the case briefing without launching acquisition or analysis."""

    @core.app.get("/api/case/briefing")
    def briefing():
        """Return conclusions and uncertainty before raw activity or tool output."""
        return build_briefing(core)

    return {"briefing": briefing}
