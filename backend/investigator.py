"""Durable, checkpointed investigative tasks with independent provenance checks."""

import hashlib, json, re, threading, time
from pathlib import Path
from pydantic import BaseModel, Field
from fastapi import HTTPException
from . import models

STAGES = [
    (
        "Chief Investigator",
        "Scope and retrieve acquired originals",
        "retrieve_originals",
    ),
    ("Document Intelligence", "Locate exact source passages", "extract_passages"),
    (
        "Graph Intelligence",
        "Audit source-backed relationships",
        "inspect_relationships",
    ),
    ("Chronology Agent", "Separate date types and uncertainty", "source_chronology"),
    ("Analyst", "Generate optional model proposals", "model_proposals"),
    (
        "Evidence Auditor",
        "Verify files, derivative hashes and exact citations",
        "validate_citations",
    ),
    (
        "Red-Team Analyst",
        "Challenge attribution and reasoning gaps",
        "review_limitations",
    ),
]


class InvestigationInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)
    provider: str = "deterministic"
    model: str = Field(default="", max_length=150)


def install(core):
    core.execute(
        """CREATE TABLE IF NOT EXISTS investigations(id TEXT PRIMARY KEY,question TEXT,provider TEXT,model TEXT,evidence_ids TEXT,status TEXT,cursor INTEGER,created TEXT,updated TEXT,result TEXT,error TEXT)"""
    )
    core.execute(
        """CREATE TABLE IF NOT EXISTS investigator_tasks(id TEXT PRIMARY KEY,run_id TEXT,sequence INTEGER,agent TEXT,objective TEXT,tool TEXT,dependency TEXT,status TEXT,attempts INTEGER,input_evidence TEXT,output TEXT,started TEXT,completed TEXT,error TEXT,UNIQUE(run_id,sequence))"""
    )
    active = set()
    lock = threading.Lock()

    def value_unlocked(run_id):
        rs = core.rows("SELECT * FROM investigations WHERE id=?", (run_id,))
        if not rs:
            raise HTTPException(404, "Investigation missing")
        r = rs[0]
        r["evidence_ids"] = json.loads(r["evidence_ids"])
        r["result"] = json.loads(r["result"]) if r["result"] else None
        r["tasks"] = core.rows(
            "SELECT * FROM investigator_tasks WHERE run_id=? ORDER BY sequence",
            (run_id,),
        )
        for task in r["tasks"]:
            task["input_evidence"] = json.loads(task["input_evidence"] or "[]")
            task["output"] = json.loads(task["output"]) if task["output"] else None
        return r

    def value(run_id):
        with core.lock:
            return value_unlocked(run_id)

    def integrity(e):
        if not e.get("fileUrl") or not e.get("sha256"):
            return False, "No acquired original"
        path = (core.ROOT / "originals" / e["sha256"]).resolve()
        if path.parent != (core.ROOT / "originals").resolve() or not path.is_file():
            return False, "Original missing or outside vault"
        if hashlib.sha256(path.read_bytes()).hexdigest() != e["sha256"]:
            return False, "Original hash mismatch"
        derivatives = e["metadata"].get("derivative_hashes", {})
        if not derivatives.get("text.txt"):
            return False, "Text derivative is not attested; reprocess in sandbox"
        derivative = (core.ROOT / "derivatives" / e["id"] / "text.txt").resolve()
        if (
            core.ROOT / "derivatives"
        ).resolve() not in derivative.parents or not derivative.is_file():
            return False, "Attested text derivative missing or outside vault"
        if (
            hashlib.sha256(derivative.read_bytes()).hexdigest()
            != derivatives["text.txt"]
        ):
            return False, "Stored text derivative hash mismatch"
        text = e["text"].encode()
        if hashlib.sha256(text).hexdigest() != derivatives["text.txt"]:
            return False, "Indexed text hash does not match attested derivative"
        return True, "Original and indexed-text hashes verified"

    def sources(run):
        ids = run["evidence_ids"]
        hits = []
        if ids:
            for eid in ids:
                hits.append(core.get_evidence(eid))
        else:
            terms = [
                x
                for x in re.findall(r"\w+", run["question"])
                if len(x) > 3
                and x.lower()
                not in {
                    "what",
                    "which",
                    "does",
                    "about",
                    "show",
                    "source",
                    "sources",
                    "acquired",
                    "records",
                    "document",
                    "documents",
                    "evidence",
                    "connecting",
                    "their",
                    "these",
                    "original",
                    "originals",
                    "have",
                    "that",
                    "from",
                    "with",
                    "research",
                    "published",
                }
            ]
            for term in terms[:10]:
                for hit in core.search(term):
                    if hit["id"] not in [e["id"] for e in hits]:
                        hits.append(hit["evidence"])
        accepted = []
        excluded = []
        for e in hits[:30]:
            good, reason = integrity(e)
            if good:
                accepted.append(e["id"])
            else:
                excluded.append({"id": e["id"], "reason": reason})
        return {
            "input_evidence": accepted[:12],
            "excluded": excluded,
            "scope": "Only locally acquired originals with verified original and derivative hashes",
        }

    def passage(e, question):
        stop = {
            "what",
            "which",
            "show",
            "give",
            "name",
            "names",
            "list",
            "listed",
            "find",
            "from",
            "with",
            "that",
            "these",
            "their",
            "original",
            "record",
            "records",
            "actual",
            "exact",
            "short",
            "quote",
            "quotes",
            "each",
            "provided",
            "passage",
            "appear",
            "printed",
            "under",
            "only",
            "page",
            "named",
            "state",
            "explain",
            "describe",
            "determine",
            "field",
            "infer",
            "relationships",
        }
        terms = [
            t.lower()
            for t in re.findall(r"\w+", question)
            if len(t) > 3 and t.lower() not in stop
        ]
        text = e["text"]
        pages = e["metadata"].get("pages") or []
        best = None
        requested = re.search(
            r"\bpage\s+(\d+|one|two|three|four|five)\b", question, re.I
        )
        page_number = None
        if requested:
            value = requested.group(1).lower()
            page_number = (
                int(value)
                if value.isdigit()
                else {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}[value]
            )
            selected = next((p for p in pages if p["page"] == page_number), None)
            if not selected and pages:
                raise ValueError(
                    f"Requested page {page_number} is absent from the acquired document"
                )
            if selected:
                best = (float("inf"), selected["text"], f"Page {page_number}")
        for p in pages:
            score = sum(
                bool(re.search(r"\b" + re.escape(t) + r"\b", p["text"], re.I))
                for t in terms
            )
            if not best or score > best[0]:
                best = (score, p["text"], f"Page {p['page']}")
        if best:
            text = best[1]
            location = best[2]
        else:
            location = "Extracted source text"
        lower = text.lower()
        offset = next((lower.index(t) for t in terms if t in lower), 0)
        start = max(0, offset - 200)
        end = min(len(text), start + 1200)
        quote = text[start:end]
        # Locate the exact passage in attested indexed text (OCR/PDF blocks remain source derivatives).
        absolute = e["text"].find(quote)
        if absolute < 0:
            raise ValueError("Page text does not match indexed source text")
        return {
            "id": e["id"],
            "title": e["title"],
            "quote": quote,
            "location": location,
            "start": absolute,
            "end": absolute + len(quote),
            "status": e["status"],
            "sha256": e["sha256"],
            "text_sha256": e["metadata"]["derivative_hashes"]["text.txt"],
        }

    def citations(data, input_ids, supplied=None):
        accepted = []
        rejected = []
        checks = []
        for eid in input_ids:
            e = core.get_evidence(eid)
            valid, reason = integrity(e)
            checks.append(
                {
                    "id": eid,
                    "valid": valid,
                    "reason": reason,
                    "original_sha256": e.get("sha256"),
                    "text_sha256": e["metadata"]
                    .get("derivative_hashes", {})
                    .get("text.txt"),
                }
            )
        for candidate in data.get("findings", [])[:30]:
            if not isinstance(candidate, dict):
                rejected.append({"reason": "Invalid finding schema"})
                continue
            eid = candidate.get("evidence_id")
            quote = candidate.get("quote")
            claim = candidate.get("claim")
            if (
                eid not in input_ids
                or not isinstance(quote, str)
                or len(quote.strip()) < 8
                or not isinstance(claim, str)
                or not claim.strip()
            ):
                rejected.append(
                    {
                        "claim": claim,
                        "reason": "Missing claim or exact supplied-source citation",
                    }
                )
                continue
            e = core.get_evidence(eid)
            good, reason = integrity(e)
            if not good or quote not in e["text"]:
                rejected.append(
                    {
                        "claim": claim,
                        "reason": reason
                        if not good
                        else "Quoted passage does not occur in acquired original derivative",
                    }
                )
                continue
            if supplied is not None and not any(
                s["id"] == eid and quote in s["quote"] for s in supplied
            ):
                rejected.append(
                    {
                        "claim": claim,
                        "reason": "Citation was not present in the passages supplied to the model",
                    }
                )
                continue
            location = next(
                (
                    f"Page {p['page']}"
                    for p in e["metadata"].get("pages", [])
                    if quote in p["text"]
                ),
                f"Indexed characters {e['text'].find(quote)}–{e['text'].find(quote) + len(quote)}",
            )
            accepted.append(
                {
                    "claim": claim,
                    "evidence_id": eid,
                    "quote": quote,
                    "proposed_location": candidate.get("location"),
                    "location": location,
                    "review_state": "REVIEW REQUIRED",
                    "citation_status": "EXACT PASSAGE VERIFIED",
                    "original_sha256": e["sha256"],
                }
            )
        return {
            "findings": accepted,
            "rejected": rejected,
            "integrity_checks": checks,
            "validation": "Exact quote matching does not prove that a claim follows from its source; human review required",
        }

    def step(run, sequence):
        outputs = {
            t["sequence"]: t["output"] for t in run["tasks"] if t["output"] is not None
        }
        ids = outputs.get(0, {}).get("input_evidence", [])
        if sequence == 0:
            return sources(run)
        if sequence == 1:
            return {
                "sources": [
                    passage(core.get_evidence(eid), run["question"])
                    for eid in ids
                    if core.get_evidence(eid)["text"].strip()
                ]
            }
        if sequence == 2:
            links = []
            for board in core.boards():
                for edge in core.board(board["id"])["edges"]:
                    d = edge.get("data", {})
                    evidence = d.get("evidence", [])
                    if any(c.get("id") in ids for c in evidence):
                        valid = all(
                            c.get("id") in ids
                            and c.get("quote") in core.get_evidence(c["id"])["text"]
                            for c in evidence
                        )
                        links.append(
                            {
                                "board_id": board["id"],
                                "edge_id": edge["id"],
                                "claim": d.get("claim", edge.get("label")),
                                "state": d.get("state", "UNVERIFIED"),
                                "citation_valid": bool(evidence) and valid,
                                "citations": evidence,
                            }
                        )
            return {
                "relationships": links,
                "notice": "Imported unverified leads are not upgraded into factual relationships",
            }
        if sequence == 3:
            dates = []
            for eid in ids:
                e = core.get_evidence(eid)
                m = e["metadata"]
                dates.append(
                    {
                        "id": eid,
                        "title": e["title"],
                        "retrieved_utc": m.get("retrieved_utc"),
                        "publication_date": m.get("publication_date"),
                        "embedded_creation_date": m.get("document_metadata", {}).get(
                            "creationDate"
                        ),
                        "creation_date_review": "Embedded metadata is not independently authenticated",
                        "archive_capture_date": m.get("archive_capture_date"),
                    }
                )
            return {
                "dates": dates,
                "rule": "Retrieval, publication, creation and archive capture are distinct; unknown dates stay unknown",
            }
        if sequence == 4:
            if run["provider"] == "deterministic":
                return {
                    "findings": [],
                    "summary": "Matching acquired passages and relationship records are available for review. No model-generated or factual conclusion has been produced.",
                    "limitations": ["Model reasoning not requested/configured"],
                    "mode": "Deterministic evidence retrieval",
                }
            if not outputs[1]["sources"]:
                return {
                    "findings": [],
                    "summary": "No acquired source passages; model was not invoked.",
                    "limitations": ["No substantiated input evidence"],
                }
            return models.propose(
                run["provider"], run["model"], run["question"], outputs[1]["sources"]
            )
        if sequence == 5:
            return citations(outputs[4], ids, outputs[1]["sources"])
        if sequence == 6:
            failures = [c for c in outputs[5]["integrity_checks"] if not c["valid"]]
            warnings = [
                "Shared names, institutions or keywords do not establish identity or collaboration.",
                "Hash verification establishes preserved bytes, not the truth of the source.",
                "Exact quotation checks do not establish logical entailment or independent corroboration.",
                "A dated identifier does not authenticate historical post content or account ownership.",
            ]
            if failures:
                warnings.insert(
                    0,
                    "Some sources failed the independent integrity recheck and were excluded from the final answer.",
                )
            if not outputs[1]["sources"]:
                warnings.insert(
                    0, "No acquired text passages support an answer to this question."
                )
            return {
                "limitations": warnings,
                "red_team_mode": "Deterministic provenance/attribution checks; not independent model reasoning",
                "unsupported_sources": outputs[0]["excluded"],
                "rejected_findings": outputs[5]["rejected"],
                "review_state": "REVIEW REQUIRED",
            }

    def finish(run_id):
        r = value(run_id)
        outputs = {t["sequence"]: t["output"] for t in r["tasks"]}
        result = {
            "question": r["question"],
            "sources": [
                s
                for s in outputs[1]["sources"]
                if any(
                    c["id"] == s["id"] and c["valid"]
                    for c in outputs[5]["integrity_checks"]
                )
            ],
            "relationships": outputs[2]["relationships"],
            "chronology": outputs[3]["dates"],
            "summary": outputs[4].get("summary", "")
            if r["provider"] == "deterministic"
            else f"The model proposed {len(outputs[5]['findings'])} findings for review; {len(outputs[5]['rejected'])} were rejected. No model finding is accepted as a verified fact.",
            "findings": outputs[5]["findings"],
            "rejected_findings": outputs[5]["rejected"],
            "limitations": outputs[6]["limitations"],
            "excluded_sources": outputs[0]["excluded"]
            + [c for c in outputs[5]["integrity_checks"] if not c["valid"]],
            "integrity_checks": outputs[5]["integrity_checks"],
            "review_state": "REVIEW REQUIRED",
            "mode": r["provider"],
            "automatic_factual_edges": False,
        }
        core.execute(
            "UPDATE investigations SET result=?,status=?,updated=? WHERE id=? AND status NOT IN (?,?)",
            (json.dumps(result), "COMPLETE", core.now(), run_id, "CANCELLED", "PAUSED"),
        )

    def run(run_id):
        try:
            while not core.stopping.is_set():
                with core.lock:
                    r = value(run_id)
                    if r["status"] in ("PAUSED", "CANCELLED", "COMPLETE", "FAILED"):
                        return
                    core.execute(
                        "UPDATE investigations SET status=?,updated=? WHERE id=?",
                        ("RUNNING", core.now(), run_id),
                    )
                    cursor = r["cursor"]
                    if cursor >= len(STAGES):
                        finish(run_id)
                        return
                    task = r["tasks"][cursor]
                    ids = (
                        r["tasks"][0]["output"].get("input_evidence", [])
                        if r["tasks"][0]["output"]
                        else r["evidence_ids"]
                    )
                    core.execute(
                        "UPDATE investigator_tasks SET status=?,attempts=attempts+1,input_evidence=?,started=?,error=NULL WHERE id=?",
                        ("RUNNING", json.dumps(ids), core.now(), task["id"]),
                    )
                core.log(
                    "investigator_tool_started",
                    {
                        "id": run_id,
                        "task": task["id"],
                        "agent": task["agent"],
                        "tool": task["tool"],
                        "input_evidence": ids,
                    },
                )
                output = step(value(run_id), cursor)
                with core.lock:
                    core.execute(
                        "UPDATE investigator_tasks SET output=?,status=?,completed=? WHERE id=?",
                        (json.dumps(output), "COMPLETE", core.now(), task["id"]),
                    )
                    core.execute(
                        "UPDATE investigations SET cursor=?,updated=? WHERE id=?",
                        (cursor + 1, core.now(), run_id),
                    )
                core.log(
                    "investigator_tool_complete",
                    {
                        "id": run_id,
                        "task": task["id"],
                        "agent": task["agent"],
                        "tool": task["tool"],
                    },
                )
        except Exception as ex:
            with core.lock:
                r = value(run_id)
                task = r["tasks"][min(r["cursor"], len(STAGES) - 1)]
                core.execute(
                    "UPDATE investigator_tasks SET status=?,error=?,completed=? WHERE id=?",
                    ("FAILED", str(ex)[:1200], core.now(), task["id"]),
                )
                core.execute(
                    "UPDATE investigations SET status='FAILED',error=?,updated=? WHERE id=? AND status NOT IN ('CANCELLED','PAUSED')",
                    (str(ex)[:1200], core.now(), run_id),
                )
            core.log("investigator_failed", {"id": run_id, "error": str(ex)[:1200]})
        finally:
            with lock:
                active.discard(run_id)

    def loop():
        while not core.stopping.wait(0.5):
            with lock:
                if active:
                    continue
                rs = core.rows(
                    "SELECT id FROM investigations WHERE status='QUEUED' ORDER BY created LIMIT 1"
                )
                if not rs:
                    continue
                run_id = rs[0]["id"]
                active.add(run_id)
            threading.Thread(target=run, args=(run_id,), daemon=True).start()

    @core.app.on_event("startup")
    def start():
        core.execute("UPDATE investigations SET status='QUEUED' WHERE status='RUNNING'")
        core.execute(
            "UPDATE investigator_tasks SET status='QUEUED',error='Interrupted; resuming persisted checkpoint' WHERE status='RUNNING'"
        )
        threading.Thread(target=loop, daemon=True).start()

    @core.app.get("/api/models")
    def model_status():
        return models.status()

    @core.app.post("/api/investigations")
    def create(a: InvestigationInput):
        if a.provider not in ("deterministic", "ollama", "anthropic"):
            raise HTTPException(422, "Unsupported investigator provider")
        if a.provider != "deterministic":
            settings = models.status()[a.provider]
            if not settings["ready"]:
                raise HTTPException(422, a.provider + " is not configured or reachable")
            if a.provider == "ollama" and a.model not in settings["models"]:
                raise HTTPException(422, "Choose an installed local Ollama model")
            if a.provider == "anthropic" and not (a.model or settings["model"]):
                raise HTTPException(422, "Configure a model name")
            if not a.model:
                a.model = settings.get("model", "")
        for eid in a.evidence_ids:
            core.get_evidence(eid)
        run_id = core.uid("INV")
        with core.lock, core.db() as connection:
            connection.execute(
                "INSERT INTO investigations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    a.question,
                    a.provider,
                    a.model,
                    json.dumps(a.evidence_ids),
                    "QUEUED",
                    0,
                    core.now(),
                    core.now(),
                    None,
                    None,
                ),
            )
            previous = None
            for seq, (agent, objective, tool) in enumerate(STAGES):
                task_id = core.uid("AGENT")
                connection.execute(
                    "INSERT INTO investigator_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        task_id,
                        run_id,
                        seq,
                        agent,
                        objective,
                        tool,
                        previous,
                        "QUEUED",
                        0,
                        json.dumps(a.evidence_ids),
                        None,
                        None,
                        None,
                        None,
                    ),
                )
                previous = task_id
        core.log(
            "investigation_queued",
            {"id": run_id, "provider": a.provider, "question": a.question},
        )
        return value(run_id)

    @core.app.get("/api/investigations")
    def listing():
        return [
            value(r["id"])
            for r in core.rows(
                "SELECT id FROM investigations ORDER BY created DESC LIMIT 50"
            )
        ]

    @core.app.get("/api/investigations/{run_id}")
    def detail(run_id: str):
        return value(run_id)

    class AttachInput(BaseModel):
        board_id: str = "looking-glass"

    @core.app.post("/api/investigation-findings/{run_id}/{finding_index}/attach")
    def attach(run_id: str, finding_index: int, a: AttachInput):
        r = value(run_id)
        if (
            r["status"] != "COMPLETE"
            or not r["result"]
            or not 0 <= finding_index < len(r["result"]["findings"])
        ):
            raise HTTPException(422, "No citation-checked proposal at this index")
        finding = r["result"]["findings"][finding_index]
        source = core.get_evidence(finding["evidence_id"])
        good, reason = integrity(source)
        if not good or finding["quote"] not in source["text"]:
            raise HTTPException(422, "Source revalidation failed: " + reason)
        bid = a.board_id
        eid = "HYP-" + run_id.removeprefix("INV-") + "-" + str(finding_index)
        nid = "proposal-" + eid
        with core.lock, core.db() as connection:
            boards = connection.execute(
                "SELECT data FROM boards WHERE id=?", (bid,)
            ).fetchone()
            if not boards:
                raise HTTPException(404, "Board missing")
            board = json.loads(boards["data"])
            if any(n["id"] == nid for n in board["nodes"]):
                return {"board_id": bid, "evidence_id": eid, "already_attached": True}
            metadata = {
                "source": "Model-generated proposal; not original evidence",
                "actor": "AI proposal attached for investigator review",
                "run_id": run_id,
                "provider": r["provider"],
                "model": r["model"],
                "review_state": "REVIEW REQUIRED",
                "citations": [
                    {
                        "id": source["id"],
                        "quote": finding["quote"],
                        "location": finding["location"],
                    }
                ],
                "original_sha256": source["sha256"],
            }
            if not connection.execute(
                "SELECT id FROM evidence WHERE id=?", (eid,)
            ).fetchone():
                connection.execute(
                    "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        eid,
                        finding["claim"][:120],
                        "hypothesis",
                        "HYPOTHESIS",
                        "",
                        None,
                        None,
                        "text/plain",
                        0,
                        core.now(),
                        json.dumps(metadata),
                        finding["claim"],
                        None,
                    ),
                )
                connection.execute(
                    "INSERT INTO evidence_fts VALUES(?,?,?)",
                    (eid, finding["claim"][:120], finding["claim"]),
                )
            x = 40
            y = max((n["position"]["y"] for n in board["nodes"]), default=-350) + 400
            board["nodes"].append(
                {
                    "id": nid,
                    "type": "evidence",
                    "position": {"x": x, "y": y},
                    "data": {"evidenceId": eid},
                }
            )
            target = next(
                (
                    n["id"]
                    for n in board["nodes"]
                    if n.get("data", {}).get("evidenceId") == source["id"]
                ),
                None,
            )
            if target is None:
                target = "source-" + source["id"]
                board["nodes"].append(
                    {
                        "id": target,
                        "type": "evidence",
                        "position": {"x": x + 410, "y": y},
                        "data": {"evidenceId": source["id"]},
                    }
                )
            board["edges"].append(
                {
                    "id": "support-" + eid,
                    "source": nid,
                    "target": target,
                    "type": "smoothstep",
                    "label": "Proposed support · review required",
                    "data": {
                        "claim": finding["claim"],
                        "state": "HYPOTHESIS",
                        "confidence": "Unassessed; human review required",
                        "method": r["provider"] + " model proposal, manually attached",
                        "reason": "Exact source passage verified; factual interpretation not approved",
                        "evidence": metadata["citations"],
                        "contradictions": [],
                    },
                }
            )
            connection.execute(
                "UPDATE boards SET data=? WHERE id=?", (json.dumps(board), bid)
            )
        core.log(
            "model_proposal_attached",
            {
                "id": run_id,
                "evidence_id": eid,
                "board_id": bid,
                "source_id": source["id"],
                "state": "HYPOTHESIS",
            },
        )
        return {"board_id": bid, "evidence_id": eid, "already_attached": False}

    @core.app.post("/api/investigations/{run_id}/{action}")
    def control(run_id: str, action: str):
        with core.lock:
            r = value(run_id)
            if action not in ("pause", "resume", "cancel", "retry"):
                raise HTTPException(422, "Unknown investigation action")
            if r["status"] == "COMPLETE":
                raise HTTPException(409, "Completed run is immutable; create a new run")
            status = {
                "pause": "PAUSED",
                "resume": "QUEUED",
                "cancel": "CANCELLED",
                "retry": "QUEUED",
            }[action]
            core.execute(
                "UPDATE investigations SET status=?,error=NULL,updated=? WHERE id=?",
                (status, core.now(), run_id),
            )
        core.log("investigation_" + action, {"id": run_id})
        return value(run_id)

    return {
        "run": run,
        "create": create,
        "validate": citations,
        "integrity": integrity,
        "step": step,
        "value": value,
        "control": control,
        "attach_proposal": lambda run_id,index,board_id: attach(run_id,index,AttachInput(board_id=board_id)),
    }
