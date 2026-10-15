"""Topic-oriented case reports: connections, preserved records and saved analysis."""

import json
from urllib.parse import urlparse
from fastapi import HTTPException

TOPICS = [
    (
        "eu-time-machine",
        "EU Time Machine · historical digitisation",
        "What do the official European project records establish, and is any case connection supported?",
        ("eu time machine", "timemachine.eu", "cordis", "epfl", "820323"),
    ),
    (
        "caltech",
        "Cole Allen · Caltech & JPL",
        "Which education, robotics and JPL relationships are supported by original records?",
        (
            "caltech",
            "blitzkrieg",
            "tridroid",
            "jpl",
            "cole tomas allen",
            "2016 caltech",
        ),
    ),
    (
        "games",
        "Bohrdom & First Law",
        "What do original game records and archived versions establish?",
        ("bohrdom", "first law", "steam", "945530", "945531", "ditch day"),
    ),
    (
        "mondaloy",
        "Mondaloy · inventors & patents",
        "Who is named on the alloy patents, and what do the documents actually claim?",
        (
            "mondaloy",
            "jacinto",
            "hardwick",
            "burn-resistant",
            "20030053926",
            "20100266442",
            "patent provenance",
        ),
    ),
    (
        "post",
        "The X post · Henry Martinez",
        "Is the post, its date, its account attribution or the claimed prediction authenticated?",
        (
            "1738018409441308955",
            "henry",
            "martinez",
            "x identifier",
            "cforce",
            "coldforce",
            "bohrdom1",
            "reported alumnus",
        ),
    ),
    (
        "scientists",
        "Scientists · the proposed common team",
        "Is there source-backed evidence that the listed people formed one research team?",
        (
            "roster",
            "fourteen",
            "scientists",
            "common-team",
            "chavez",
            "mccasland",
            "casias",
            "reza",
            "loureiro",
            "esk ridge",
        ),
    ),
    (
        "images",
        "Images · hidden content & alterations",
        "Which visual claims survive comparison, source checking and chronology review?",
        (
            "waterfall",
            "butler",
            "composite",
            "overlay",
            "hybrid images",
            "optical illusion",
            "public photograph",
            "image comparisons",
            "photograph and archive",
            "teacher of the month",
        ),
    ),
    (
        "codes",
        "Codes · ciphers & gematria",
        "What was decoded, with which recipe, and did it survive controls?",
        ("cipher", "gematria", "436f6c6520416c6c656e", "hexadecimal", "encoded"),
    ),
    (
        "propulsion",
        "Propulsion & the quantum hypothesis",
        "What is demonstrated engineering, and what remains a speculative interpretation?",
        (
            "propulsion",
            "quantum",
            "superalloy",
            "materials literature",
            "time travel",
            "research lead",
        ),
    ),
    (
        "legal",
        "Alleged attack · legal and identity claims",
        "Which allegations are supported by acquired court records or independently attributed sources?",
        (
            "court",
            "indictment",
            "shooting",
            "dossier",
            "biographical",
            "cole tomas allen",
        ),
    ),
]


def topic_ids(text):
    """Route by topic labels only; a shared term never establishes a relationship."""
    lower = text.casefold()
    return [key for key, _, _, terms in TOPICS if any(term in lower for term in terms)]


def build_breakdown(core, briefing):
    """Group actual saved case material and retain unsupported claims as gaps."""
    topics = {
        key: {
            "id": key,
            "title": title,
            "question": question,
            "connections": [],
            "findings": [],
            "documents": [],
            "discovery_records": [],
            "notes": [],
            "analyses": [],
            "boards": [],
        }
        for key, title, question, _ in TOPICS
    }
    evidence = {
        e["id"]: e
        for e in core.rows(
            "SELECT id,title,kind,status,path,mime,url,sha256,created,metadata FROM evidence"
        )
    }
    note_text = {
        row["id"]: row["text"] or ""
        for row in core.rows("SELECT id,text FROM evidence WHERE path IS NULL")
    }
    membership = {eid: set(topic_ids(e["title"])) for eid, e in evidence.items()}
    boards = core.rows("SELECT id,name,data FROM boards ORDER BY rowid")
    for b in boards:
        ids = topic_ids(b["name"])
        data = json.loads(b["data"])
        for n in data.get("nodes", []):
            eid = n.get("data", {}).get("evidenceId")
            if eid in membership:
                membership[eid].update(ids)
        for tid in ids:
            topics[tid]["boards"].append({"id": b["id"], "name": b["name"]})
    verified = {
        f["statement"]: f for f in briefing["findings"] if f["kind"] == "DOCUMENTED"
    }
    questions = {q["statement"]: q for q in briefing["open_questions"]}
    for b in boards:
        data = json.loads(b["data"])
        node_ids = {
            n["id"]: n.get("data", {}).get("evidenceId") for n in data.get("nodes", [])
        }
        for edge in data.get("edges", []):
            d = edge.get("data", {})
            if not d.get("claim") or d.get("proposed_by") == "Acquisition organiser":
                continue
            source, target = (
                node_ids.get(edge.get("source")),
                node_ids.get(edge.get("target")),
            )
            scope = topic_ids(
                b["name"]
                + " "
                + d["claim"]
                + " "
                + " ".join(
                    evidence.get(eid, {}).get("title", "") for eid in [source, target]
                )
            )
            for c in d.get("evidence", []):
                scope += list(membership.get(c.get("id"), set()))
            if not scope:
                if "other" not in topics:
                    topics["other"] = {
                        "id": "other",
                        "title": "Other saved case connections",
                        "question": "Which saved relationships have not been assigned to an established case thread?",
                        "connections": [],
                        "findings": [],
                        "documents": [],
                        "discovery_records": [],
                        "notes": [],
                        "analyses": [],
                        "boards": [],
                    }
                scope = ["other"]
            checked = verified.get(d["claim"])
            unresolved = questions.get(d["claim"], {})
            item = {
                "id": b["id"] + ":" + edge["id"],
                "from": evidence.get(source, {}).get("title", edge.get("source")),
                "to": evidence.get(target, {}).get("title", edge.get("target")),
                "claim": d["claim"],
                "state": "DOCUMENTED" if checked else d.get("state", "UNVERIFIED"),
                "source_checked": bool(checked),
                "proof": checked["sources"]
                if checked
                else unresolved.get("sources", []),
                "analysis": d.get("reason")
                or d.get("method")
                or unresolved.get("reason")
                or "No saved explanation accompanies this proposed connection.",
                "method": d.get("method"),
                "limits": d.get("confidence"),
                "counterevidence": d.get("contradictions", []),
                "board_id": b["id"],
            }
            if not checked and item["state"] in ("DOCUMENTED", "CORROBORATED"):
                item["state"] = "SUPPORT COULD NOT BE VERIFIED"
            for tid in set(scope):
                topics[tid]["connections"].append(item)
    for f in briefing["findings"]:
        ids = set(topic_ids(f["topic"] + " " + f["statement"]))
        for s in f["sources"]:
            ids.update(membership.get(s["evidence_id"], set()))
        for tid in ids:
            topics[tid]["findings"].append(f)
    for eid, e in evidence.items():
        meta = json.loads(e["metadata"])
        for tid in membership[eid]:
            if e["path"] and e["sha256"] and e["status"] != "SECONDARY SOURCE":
                topics[tid]["documents"].append(
                    {
                        "id": eid,
                        "title": e["title"],
                        "mime": e["mime"],
                        "status": e["status"],
                        "sha256": e["sha256"],
                        "domain": urlparse(e["url"] or "").hostname or "Imported file",
                        "retrieved_at": e["created"],
                        "publication_date": meta.get("publication_date"),
                        "archive_capture_date": meta.get("archive_capture_date"),
                        "cited_in_connection": any(
                            c["source_checked"]
                            and any(s["evidence_id"] == eid for s in c["proof"])
                            for c in topics[tid]["connections"]
                        ),
                    }
                )
            elif e["status"] in (
                "SECONDARY SOURCE",
                "HYPOTHESIS",
                "UNVERIFIED ATTRIBUTION",
            ):
                topics[tid]["notes"].append(
                    {
                        "id": eid,
                        "title": e["title"],
                        "status": e["status"],
                        "summary": note_text.get(eid, "")[:650],
                    }
                )
    # Deduplicate repeated research jobs by question and source set. Empty plans are not analysis.
    seen = set()
    for r in core.rows(
        "SELECT id,question,provider,updated,result FROM investigations WHERE status='COMPLETE' AND result IS NOT NULL ORDER BY updated DESC LIMIT 200"
    ):
        d = json.loads(r["result"])
        sources = d.get("sources", [])
        identity = (r["question"], tuple(sorted(s.get("id", "") for s in sources)))
        if identity in seen or not sources:
            continue
        seen.add(identity)
        ids = set(topic_ids(r["question"]))
        for s in sources:
            ids.update(membership.get(s.get("id"), set()))
        for tid in ids:
            topics[tid]["analyses"].append(
                {
                    "id": r["id"],
                    "kind": "investigation",
                    "title": r["question"],
                    "summary": d.get("summary") or "Saved source review",
                    "state": "AI PROPOSAL · REVIEW REQUIRED"
                    if r["provider"] != "deterministic"
                    else "SOURCE REVIEW · NO NEW FACT INFERRED",
                    "updated": r["updated"],
                    "href": "/case/breakdown/analysis/investigation/" + r["id"],
                }
            )
    for story in core.visual["explanations"]():
        d = story["data"]
        if d.get("unavailable"):
            continue
        tid = "images"
        if any(
            a.get("composite_id") == d.get("composite_id")
            for a in topics[tid]["analyses"]
        ):
            continue
        topics[tid]["analyses"].insert(
            0,
            {
                "id": story["id"],
                "kind": "visual",
                "composite_id": d.get("composite_id"),
                "title": d.get("title"),
                "summary": d.get("summary"),
                "state": d.get("assessment"),
                "href": "/case/breakdown/analysis/visual/" + story["id"],
            },
        )
    if hasattr(core, "automatic_workspaces"):
        automatic = core.automatic_workspaces["snapshot"]("cipher")
        for result in automatic["results"]:
            eid = result["evidence_id"]
            topics["codes"]["analyses"].append(
                {
                    "id": result["id"],
                    "kind": "receipt",
                    "title": result["title"] + " · " + result["method"],
                    "summary": result["summary"],
                    "state": "AUTOMATIC TEST · NOT AN AUTHENTICATED MESSAGE",
                    "href": "/case/receipts/" + result["id"],
                }
            )
            if eid in evidence and not any(
                d["id"] == eid for d in topics["codes"]["documents"]
            ):
                e = evidence[eid]
                topics["codes"]["documents"].append(
                    {
                        "id": eid,
                        "title": e["title"],
                        "mime": e["mime"],
                        "status": e["status"],
                        "sha256": e["sha256"],
                        "domain": urlparse(e["url"] or "").hostname or "Imported file",
                        "retrieved_at": e["created"],
                        "publication_date": None,
                        "archive_capture_date": None,
                        "cited_in_connection": False,
                    }
                )
        topics["codes"]["analysis_scope"] = automatic["scope"]
    for tid, t in topics.items():
        catalogue_records = [
            d
            for d in t["documents"]
            if d["mime"] == "application/json"
            and any(
                word in d["title"].casefold()
                for word in ("search", "discovery", "catalogue")
            )
        ]
        catalogue_ids = {d["id"] for d in catalogue_records}
        t["discovery_records"] = catalogue_records
        t["documents"] = [d for d in t["documents"] if d["id"] not in catalogue_ids]
        t["documents"].sort(
            key=lambda e: (
                not e["cited_in_connection"],
                e["mime"] not in ("application/pdf", "text/html"),
                e["title"],
            )
        )
        unique_documents = {}
        for document in t["documents"]:
            unique_documents.setdefault(document["sha256"], document)
        t["documents"] = list(unique_documents.values())
        t["supported_connections"] = sum(c["source_checked"] for c in t["connections"])
        t["unresolved_connections"] = len(t["connections"]) - t["supported_connections"]
        documented = [f for f in t["findings"] if f["kind"] == "DOCUMENTED"]
        t["status"] = (
            "DOCUMENTED CONNECTIONS"
            if t["supported_connections"]
            else "PROVISIONAL ANALYSIS"
            if any(f["kind"] == "MEASURED RESULT" for f in t["findings"])
            else "UNRESOLVED"
        )
        t["takeaway"] = (
            documented[0]["statement"]
            if documented
            else next(c["claim"] for c in t["connections"] if c["source_checked"])
            if t["supported_connections"]
            else next(
                (
                    f["statement"]
                    for f in t["findings"]
                    if f["kind"] == "MEASURED RESULT"
                ),
                "No source-checked factual connection has been established in this thread.",
            )
        )
        t["assessment"] = {
            "supported": f"{t['supported_connections']} saved connections currently have matching passages in integrity-checked originals.",
            "not_established": f"{t['unresolved_connections']} connections remain provisional or unsupported. Preserving a document or matching a name does not prove the broader hypothesis.",
            "coverage": "Topic routing uses titles and explicit board membership, not inferred relationships. Original records below are relevant research material; only specifically cited passages support the corresponding connection.",
        }
    return {
        "topics": list(topics.values()),
        "scope": "Connections come from saved boards; proof passages are checked against preserved originals. Analysis lists saved reports, not newly generated conclusions. The latest 200 completed research reports are considered; repeated questions/source sets are deduplicated.",
    }


def install(core):
    """Expose the case breakdown and source-validated full analysis records."""

    @core.app.get("/api/case/breakdown")
    def breakdown():
        """Return all case threads with direct connections, proof and analysis links."""
        from .case_briefing import build_briefing

        return build_breakdown(core, build_briefing(core))

    @core.app.get("/api/case/breakdown/analysis/{kind}/{record_id}")
    def analysis(kind: str, record_id: str):
        """Open a saved analysis and check its underlying originals before showing it."""
        if kind == "visual":
            records = [
                r
                for r in core.visual["explanations"]()
                if r["id"] == record_id and not r["data"].get("unavailable")
            ]
            if not records:
                raise HTTPException(
                    409,
                    "Saved visual result is unavailable or its source integrity failed",
                )
            return {"kind": kind, "id": record_id, "data": records[0]["data"]}
        if kind != "investigation":
            raise HTTPException(404, "Unknown saved analysis type")
        records = core.rows(
            "SELECT question,result FROM investigations WHERE id=? AND status='COMPLETE'",
            (record_id,),
        )
        if not records:
            raise HTTPException(404, "Completed analysis not found")
        data = json.loads(records[0]["result"])
        for s in data.get("sources", []):
            try:
                e, _, digest = core.forensics["source"](s["id"])
            except (ValueError, OSError) as error:
                raise HTTPException(409, "Analysis source integrity failed") from error
            if (
                s.get("sha256") != e["sha256"]
                or s.get("text_sha256") != digest
                or s.get("quote", "") not in e["text"]
            ):
                raise HTTPException(409, "Analysis source binding is stale")
        return {
            "kind": kind,
            "id": record_id,
            "question": records[0]["question"],
            "data": data,
        }

    return {"breakdown": breakdown}
