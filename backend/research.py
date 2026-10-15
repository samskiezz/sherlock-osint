"""Durable cron research: search -> acquire -> follow documents -> audit -> board.

Every provider attempt and dependency is persisted. Missing sources remain
failures, and model outputs remain hypotheses requiring investigator review.
"""

import json
import os
import threading
import time
from urllib.parse import urljoin, urlparse

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .discovery import PROVIDERS, DOCUMENT, search, relevant
from .scheduler import validate_schedule, next_scheduled
from .onion import validate_onion_url


class CampaignInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=8, max_length=1500)
    queries: list[str] = Field(min_length=1, max_length=4)
    providers: list[str] = Field(min_length=1, max_length=5)
    seeds: list[str] = Field(default_factory=list, max_length=10)
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)
    max_downloads: int = Field(default=6, ge=1, le=20)
    interval_minutes: int = Field(default=360, ge=15, le=525600)
    cron_expression: str = Field(default="0 */6 * * *", max_length=100)
    provider: str = "deterministic"
    model: str = Field(default="", max_length=150)
    collect_images: bool = False
    collect_all_seed_images: bool = False
    follow_patents: bool = False


class ResearchPaused(Exception):
    pass


def install(core):
    with core.db() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS research_campaigns(id TEXT PRIMARY KEY,name TEXT,settings TEXT,enabled INTEGER,next_run REAL,created TEXT,board_id TEXT);
CREATE TABLE IF NOT EXISTS research_runs(id TEXT PRIMARY KEY,campaign_id TEXT,created TEXT,updated TEXT,status TEXT,cursor INTEGER,data TEXT,error TEXT);
CREATE TABLE IF NOT EXISTS research_tasks(id TEXT PRIMARY KEY,run_id TEXT,task_key TEXT,objective TEXT,status TEXT,attempts INTEGER,started TEXT,completed TEXT,output TEXT,error TEXT,UNIQUE(run_id,task_key));
CREATE TABLE IF NOT EXISTS research_discovery(campaign_id TEXT,url TEXT,first_seen TEXT,last_seen TEXT,data TEXT,job_id TEXT,PRIMARY KEY(campaign_id,url));
CREATE TABLE IF NOT EXISTS research_run_jobs(run_id TEXT,job_id TEXT,data TEXT,PRIMARY KEY(run_id,job_id));
""")
    active, gate = set(), threading.Lock()

    def run_value(rid):
        records = core.rows("SELECT * FROM research_runs WHERE id=?", (rid,))
        if not records:
            raise HTTPException(404, "Research run missing")
        r = records[0]
        r["data"] = json.loads(r["data"])
        r["tasks"] = core.rows(
            "SELECT * FROM research_tasks WHERE run_id=? ORDER BY rowid", (rid,)
        )
        for t in r["tasks"]:
            t["output"] = json.loads(t["output"]) if t["output"] else None
        return r

    def update(rid, force=False, **values):
        with core.lock, core.db() as c:
            state = c.execute(
                "SELECT status FROM research_runs WHERE id=?", (rid,)
            ).fetchone()
            if state and state["status"] in ("PAUSED", "CANCELLED") and not force:
                return False
            if "data" in values:
                values["data"] = json.dumps(values["data"])
            values["updated"] = core.now()
            unknown = set(values) - {"status", "cursor", "data", "error", "updated"}
            if unknown:
                raise ValueError("Unknown research checkpoint fields")
            c.execute(
                "UPDATE research_runs SET status=CASE WHEN ? THEN ? ELSE status END, "
                "cursor=CASE WHEN ? THEN ? ELSE cursor END, "
                "data=CASE WHEN ? THEN ? ELSE data END, "
                "error=CASE WHEN ? THEN ? ELSE error END, updated=? WHERE id=?",
                (
                    "status" in values,
                    values.get("status"),
                    "cursor" in values,
                    values.get("cursor"),
                    "data" in values,
                    values.get("data"),
                    "error" in values,
                    values.get("error"),
                    values["updated"],
                    rid,
                ),
            )

    def stopped(rid):
        return core.stopping.is_set() or run_value(rid)["status"] in (
            "PAUSED",
            "CANCELLED",
        )

    def task(rid, key, objective, operation):
        existing = core.rows(
            "SELECT * FROM research_tasks WHERE run_id=? AND task_key=?", (rid, key)
        )
        if existing and existing[0]["status"] in ("COMPLETE", "FAILED"):
            return json.loads(existing[0]["output"] or "{}")
        tid = existing[0]["id"] if existing else core.uid("RESEARCH-TASK")
        with core.lock:
            if stopped(rid):
                return None
            core.execute(
                "INSERT OR IGNORE INTO research_tasks VALUES(?,?,?,?,?,?,?,?,?,?)",
                (tid, rid, key, objective, "QUEUED", 0, None, None, None, None),
            )
            core.execute(
                "UPDATE research_tasks SET status='RUNNING',attempts=attempts+1,started=?,error=NULL WHERE id=?",
                (core.now(), tid),
            )
        try:
            output = operation()
            core.execute(
                "UPDATE research_tasks SET status='COMPLETE',output=?,completed=? WHERE id=?",
                (json.dumps(output), core.now(), tid),
            )
            core.log("research_tool_complete", {"run": rid, "task": tid, "tool": key})
            return output
        except ResearchPaused:
            core.execute(
                "UPDATE research_tasks SET status='QUEUED',error='Paused before tool checkpoint; registered jobs retained' WHERE id=?",
                (tid,),
            )
            return None
        except Exception as e:
            output = {"error": str(e)[:1200]}
            core.execute(
                "UPDATE research_tasks SET status='FAILED',output=?,error=?,completed=? WHERE id=?",
                (json.dumps(output), str(e)[:1200], core.now(), tid),
            )
            core.log(
                "research_tool_failed",
                {"run": rid, "task": tid, "tool": key, "error": str(e)[:800]},
            )
            return output

    def in_scope(hit, settings):
        host = (urlparse(hit["url"]).hostname or "").lower()
        domains = settings["allowed_domains"]
        if domains and not any(host == d or host.endswith("." + d) for d in domains):
            return False
        try:
            if host.endswith(".onion"):
                validate_onion_url(hit["url"])
            else:
                core.validate_url(hit["url"])
        except (ValueError, TypeError):
            return False
        return True

    def enqueue_unlocked(r, hit):
        from .app import Acquire

        cid = r["campaign_id"]
        if stopped(r["id"]):
            raise ResearchPaused()
        registered = [
            json.loads(j["data"])
            for j in core.rows(
                "SELECT data FROM research_run_jobs WHERE run_id=?", (r["id"],)
            )
        ]
        existing = next((j for j in registered if j["hit"]["url"] == hit["url"]), None)
        if existing:
            return existing
        prior = core.rows(
            "SELECT * FROM research_discovery WHERE campaign_id=? AND url=?",
            (cid, hit["url"]),
        )
        if prior and prior[0]["job_id"] and not hit.get("pre_acquired_id"):
            job = core.rows("SELECT * FROM jobs WHERE id=?", (prior[0]["job_id"],))
            if job and job[0]["status"] not in (
                "CANCELLED",
                "ACQUISITION FAILED",
                "PROCESSING FAILED",
            ):
                core.execute(
                    "UPDATE research_discovery SET last_seen=? WHERE campaign_id=? AND url=?",
                    (core.now(), cid, hit["url"]),
                )
                result = {
                    "job_id": job[0]["id"],
                    "hit": hit,
                    "owned": False,
                    "seen_before": True,
                }
                core.execute(
                    "INSERT OR IGNORE INTO research_run_jobs VALUES(?,?,?)",
                    (r["id"], result["job_id"], json.dumps(result)),
                )
                return result
        jid = core.queue(
            Acquire(
                url=hit["url"],
                title=hit["title"][:200],
                transport=hit.get("transport", "auto"),
            )
        )["id"]
        core.execute(
            "INSERT INTO research_discovery VALUES(?,?,?,?,?,?) ON CONFLICT(campaign_id,url) DO UPDATE SET last_seen=excluded.last_seen,data=excluded.data,job_id=excluded.job_id",
            (cid, hit["url"], core.now(), core.now(), json.dumps(hit), jid),
        )
        seen_before = False
        if hit.get("pre_acquired_id"):
            source = core.get_evidence(hit["pre_acquired_id"])
            good, reason = core.investigator["integrity"](source)
            if not good:
                core.job_control(jid, "cancel")
                raise ValueError("Pre-acquired source failed integrity: " + reason)
            old_job = (
                core.rows(
                    "SELECT evidence_id FROM jobs WHERE id=?", (prior[0]["job_id"],)
                )
                if prior and prior[0]["job_id"]
                else []
            )
            seen_before = bool(old_job and old_job[0]["evidence_id"] == source["id"])
            if old_job and old_job[0]["evidence_id"] and not seen_before:
                older = core.get_evidence(old_job[0]["evidence_id"])
                old_text = (
                    older["metadata"].get("derivative_hashes", {}).get("text.txt")
                )
                new_text = (
                    source["metadata"].get("derivative_hashes", {}).get("text.txt")
                )
                seen_before = bool(old_text and old_text == new_text)
                if seen_before:
                    core.log(
                        "source_bytes_changed_text_unchanged",
                        {
                            "new_source": source["id"],
                            "prior_source": older["id"],
                            "claim": "No new extracted text; no duplicate analyst task",
                        },
                    )
            core.update_job(
                jid,
                "COMPLETE",
                100,
                evidence_id=source["id"],
                result=json.dumps(
                    {
                        "acquired_in": "Discovery source-page connector",
                        "evidence_id": source["id"],
                        "sha256": source["sha256"],
                    }
                ),
            )
        result = {"job_id": jid, "hit": hit, "owned": True, "seen_before": seen_before}
        core.execute(
            "INSERT INTO research_run_jobs VALUES(?,?,?)",
            (r["id"], jid, json.dumps(result)),
        )
        return result

    def enqueue(r, hit):
        with core.lock:
            result = enqueue_unlocked(r, hit)
            if hit.get("kind") == "image" and hasattr(core, "media_reports"):
                core.media_reports["register"](
                    hit["url"],
                    {
                        "kind": "RESEARCH_MEDIA_LINK",
                        "campaign_id": r["campaign_id"],
                        "parent_evidence_id": hit.get("parent_evidence_id")
                        or hit.get("catalogue_id"),
                        "post_url": hit.get("parent_post_url"),
                        "provider": hit.get("provider"),
                        "query": hit.get("query"),
                        "attribution": hit.get(
                            "attribution", "Source-linked media; subject not verified"
                        ),
                    },
                )
            return result

    terminal = {"COMPLETE", "ACQUISITION FAILED", "PROCESSING FAILED", "CANCELLED"}

    def jobs_ready(items, deadline):
        ready = True
        for item in items:
            job = core.rows("SELECT * FROM jobs WHERE id=?", (item["job_id"],))
            if job and job[0]["status"] not in terminal:
                if time.time() > deadline:
                    if item["owned"]:
                        core.job_control(item["job_id"], "cancel")
                else:
                    ready = False
        return ready

    def files(items):
        found, ids = [], set()
        for item in items:
            job = core.rows("SELECT * FROM jobs WHERE id=?", (item["job_id"],))
            if (
                job
                and job[0]["status"] == "COMPLETE"
                and job[0]["evidence_id"] not in ids
            ):
                source = core.get_evidence(job[0]["evidence_id"])
                expected_image = item["hit"].get("kind") == "image"
                expected_pdf = (
                    urlparse(item["hit"]["url"]).path.lower().endswith(".pdf")
                )
                if (
                    expected_image
                    and not source["mime"].startswith("image/")
                    or expected_pdf
                    and source["mime"] != "application/pdf"
                ):
                    reason = (
                        "Expected original image/PDF was not returned; captured response is "
                        + source["mime"]
                    )
                    core.update_job(
                        job[0]["id"],
                        "ACQUISITION FAILED",
                        100,
                        error=reason,
                        evidence_id=source["id"],
                    )
                    core.log(
                        "research_expected_original_missing",
                        {
                            "job": job[0]["id"],
                            "captured_response": source["id"],
                            "reason": reason,
                        },
                    )
                    continue
                good, reason = core.investigator["integrity"](source)
                if good:
                    ids.add(source["id"])
                    found.append(
                        {
                            "id": source["id"],
                            "sha256": source["sha256"],
                            "title": source["title"],
                            "url": source["url"],
                            "kind": source["kind"],
                            "created": source["created"],
                            "seen_before": item["seen_before"],
                            "hit": item["hit"],
                        }
                    )
                else:
                    core.log(
                        "research_integrity_failed",
                        {"source": source["id"], "reason": reason},
                    )
        return found

    def publish(r, data):
        sources = files(data.get("jobs", []))
        bid = data["settings"]["board_id"]
        # Board insertion is transactional and idempotent. Existing manual
        # positions and relationship judgments are preserved.
        with core.lock, core.db() as c:
            if stopped(r["id"]):
                raise ResearchPaused()
            row = c.execute("SELECT data FROM boards WHERE id=?", (bid,)).fetchone()
            board = json.loads(row["data"])
            ids = {n.get("data", {}).get("evidenceId") for n in board["nodes"]}
            for e in sources:
                if e["id"] in ids:
                    continue
                i = len(board["nodes"])
                board["nodes"].append(
                    {
                        "id": "research-" + e["id"],
                        "type": "evidence",
                        "position": {"x": (i % 4) * 330, "y": (i // 4) * 380},
                        "data": {"evidenceId": e["id"]},
                    }
                )
                ids.add(e["id"])
            c.execute("UPDATE boards SET data=? WHERE id=?", (json.dumps(board), bid))
        proposals = []
        analysis = data.get("investigation_id")
        if analysis:
            inv = core.investigator["value"](analysis)
            if inv["status"] == "COMPLETE":
                for i, _ in enumerate((inv.get("result") or {}).get("findings", [])):
                    if stopped(r["id"]):
                        raise ResearchPaused()
                    proposals.append(
                        core.investigator["attach_proposal"](analysis, i, bid)
                    )
        errors = [
            t["error"] for t in run_value(r["id"])["tasks"] if t["status"] == "FAILED"
        ]
        failures = [
            j
            for item in data.get("jobs", [])
            for j in core.rows(
                "SELECT id,status,error,evidence_id FROM jobs WHERE id=?",
                (item["job_id"],),
            )
            if j["status"] != "COMPLETE"
        ]
        return {
            "board_id": bid,
            "acquired": sources,
            "new_originals": sum(e["created"] >= r["created"] for e in sources),
            "new_to_campaign": sum(not e["seen_before"] for e in sources),
            "failures": failures,
            "source_errors": errors,
            "hypothesis_proposals": proposals,
            "investigation_id": analysis,
            "analysis_state": inv["status"] if analysis else "UNCHANGED / NO INPUT",
            "outcome": "ORIGINALS ACQUIRED" if sources else "NO ORIGINALS ACQUIRED",
            "limitations": [
                "Public search indexes have incomplete coverage; result absence is not evidence of absence.",
                "A public disclosure or leak label does not authenticate contents or attribution.",
                "Model findings remain hypotheses; no factual entity relationships are automatically created.",
            ],
        }

    def advance(rid):
        r = run_value(rid)
        if stopped(rid):
            return
        update(rid, status="RUNNING")
        data, stage = r["data"], r["cursor"]
        settings = data["settings"]
        if stage == 0:
            hits, catalogues = [], []
            for provider in settings["providers"]:
                for i, query in enumerate(settings["queries"]):
                    output = task(
                        rid,
                        f"discover:{provider}:{i}",
                        f"Search {PROVIDERS[provider]} for {query}",
                        lambda p=provider, q=query: search(
                            core,
                            p,
                            q,
                            settings["seeds"],
                            min(10, settings["max_downloads"]),
                        ),
                    )
                    if output is None or stopped(rid):
                        return
                    hits += [
                        {**h, "query": query}
                        for h in output.get("hits", [])
                        if provider != "feeds"
                        or h.get("kind") != "image"
                        or settings.get("collect_images")
                    ]
                    catalogues += output.get("catalogues", [])
            seen = set()
            data["hits"] = []
            for hit in hits:
                if hit["url"] not in seen and in_scope(hit, settings):
                    data["hits"].append(hit)
                    seen.add(hit["url"])
            data["catalogues"] = list(dict.fromkeys(catalogues))
            update(rid, data=data, cursor=1, status="QUEUED")
        elif stage == 1:
            ordered = sorted(data["hits"], key=lambda h: h.get("kind") != "document")
            count = (
                settings["max_downloads"]
                if all(h.get("kind") == "document" for h in ordered)
                else max(1, (settings["max_downloads"] + 1) // 2)
            )
            output = task(
                rid,
                "acquire",
                "Queue bounded original acquisitions",
                lambda: {"jobs": [enqueue(r, h) for h in ordered[:count]]},
            )
            if output is None or stopped(rid):
                return
            data["jobs"] = output.get("jobs", [])
            data["deadline"] = time.time() + 900
            update(rid, data=data, cursor=2, status="WAITING")
        elif stage == 2:
            if not jobs_ready(data["jobs"], data["deadline"]):
                update(rid, status="WAITING")
                return

            def follow():
                queued, seen = [], {x["hit"]["url"] for x in data["jobs"]}
                for entry in files(data["jobs"]):
                    e = core.get_evidence(entry["id"])
                    # Only document links extracted in the no-network parser;
                    # no browser JS, arbitrary crawling or executable downloads.
                    linked = list(e["metadata"].get("links", []))
                    patent = e["metadata"].get("patent", {})
                    linked = [
                        {
                            "href": url,
                            "label": "Original patent PDF",
                            "kind": "document",
                        }
                        for url in patent.get("pdf_urls", [])
                    ] + linked
                    if settings.get("collect_images"):
                        for media in e["metadata"].get("media", []):
                            is_preview = media.get("origin") == "publisher meta tag"
                            all_seed_media = settings.get(
                                "collect_all_seed_images", False
                            ) and (
                                e["url"] in settings.get("seeds", [])
                                or entry["hit"].get("url") in settings.get("seeds", [])
                            )
                            if (
                                all_seed_media
                                or is_preview
                                or any(
                                    relevant(media.get("caption", ""), q)
                                    for q in settings["queries"]
                                )
                            ):
                                linked.append(
                                    {
                                        "href": media["href"],
                                        "label": media.get("caption")
                                        or "Publisher image",
                                        "kind": "image",
                                        "attribution": media.get("attribution"),
                                    }
                                )
                    if settings.get("follow_patents"):
                        linked += [
                            {
                                "href": p["href"],
                                "label": p["identifier"] + " · " + p["section_heading"],
                                "kind": "patent",
                            }
                            for p in patent.get("linked_patents", [])[:2]
                        ]
                    for link in linked:
                        if stopped(rid):
                            raise ResearchPaused()
                        if len(data["jobs"]) + len(queued) >= settings["max_downloads"]:
                            break
                        if not DOCUMENT.search(link["href"]) and link.get(
                            "kind"
                        ) not in ("image", "patent"):
                            continue
                        url = urljoin(e["url"], link["href"])
                        hit = {
                            "url": url,
                            "title": (link["label"] or "Linked original document")[
                                :200
                            ],
                            "kind": link.get("kind", "document"),
                            "attribution": link.get(
                                "attribution",
                                "Source-linked document; interpretation requires review",
                            ),
                            "parent_evidence_id": e["id"],
                            "query": entry["hit"].get("query", ""),
                            "provider": entry["hit"].get("provider", "onion"),
                        }
                        if (urlparse(e["url"]).hostname or "").endswith(".onion") and (
                            urlparse(url).hostname or ""
                        ) != urlparse(e["url"]).hostname:
                            continue
                        if url in seen or not in_scope(hit, settings):
                            continue
                        if entry["hit"].get("transport") == "tor" and not any(
                            relevant(
                                link["label"]
                                + " "
                                + link["href"]
                                + " "
                                + e["text"][:10000],
                                q,
                            )
                            for q in settings["queries"]
                        ):
                            continue
                        seen.add(url)
                        queued.append(enqueue(r, hit))
                return {
                    "jobs": queued,
                    "policy": "One hop; documents plus explicitly enabled publisher images/patent links; onion links stay on the seed host; subject attribution remains unverified",
                }

            output = task(
                rid,
                "follow-documents",
                "Follow original document links from acquired source pages",
                follow,
            )
            if output is None or stopped(rid):
                return
            data["jobs"] += output.get("jobs", [])
            data["deadline"] = time.time() + 900
            update(rid, data=data, cursor=3, status="WAITING")
        elif stage == 3:
            if not jobs_ready(data["jobs"], data["deadline"]):
                update(rid, status="WAITING")
                return

            def analyse():
                from .investigator import InvestigationInput

                acquired = files(data["jobs"])
                changed = [e["id"] for e in acquired if not e["seen_before"]]
                if not changed:
                    return {
                        "investigation_id": None,
                        "reason": "No newly acquired sources; no duplicate investigative plan created",
                    }
                with core.lock:
                    if stopped(rid):
                        raise ResearchPaused()
                    inv = core.investigator["create"](
                        InvestigationInput(
                            question=settings["question"],
                            evidence_ids=changed[:12],
                            provider=settings["provider"],
                            model=settings["model"],
                        )
                    )
                    checkpoint = run_value(rid)["data"]
                    checkpoint["investigation_id"] = inv["id"]
                    update(rid, data=checkpoint)
                return {
                    "investigation_id": inv["id"],
                    "input_evidence": changed[:12],
                    "not_in_this_audit": changed[12:],
                }

            output = task(
                rid,
                "analyse",
                "Audit new original evidence and optionally generate cited proposals",
                analyse,
            )
            if output is None or stopped(rid):
                return
            data["investigation_id"] = output.get("investigation_id")
            data["deadline"] = time.time() + 900
            update(rid, data=data, cursor=4, status="WAITING")
        elif stage == 4:
            iid = data.get("investigation_id")
            if iid:
                inv = core.investigator["value"](iid)
                if inv["status"] not in ("COMPLETE", "FAILED", "CANCELLED"):
                    if time.time() < data["deadline"]:
                        update(rid, status="WAITING")
                        return
                    core.investigator["control"](iid, "cancel")
            output = task(
                rid,
                "publish",
                "Publish actual original cards and review-required proposals",
                lambda: publish(r, data),
            )
            if output is None or stopped(rid):
                return
            data["result"] = output
            status = (
                "PARTIAL"
                if output.get("source_errors")
                or output.get("failures")
                or output.get("error")
                or output.get("analysis_state") in ("FAILED", "CANCELLED")
                else "COMPLETE"
            )
            if output.get("error"):
                status = "FAILED"
            if not output.get("acquired") and output.get("source_errors"):
                status = "FAILED"
            update(rid, data=data, cursor=5, status=status)
            core.log(
                "research_run_finished",
                {
                    "id": rid,
                    "status": status,
                    "acquired": len(output.get("acquired", [])),
                },
            )

    def execute_run(rid):
        try:
            advance(rid)
        except Exception as e:
            with core.lock:
                if not stopped(rid):
                    update(rid, status="FAILED", error=str(e)[:1200])
            core.log("research_run_failed", {"id": rid, "error": str(e)[:800]})
        finally:
            with gate:
                active.discard(rid)

    def launch(cid):
        with core.lock, core.db() as c:
            existing = c.execute(
                "SELECT id FROM research_runs WHERE campaign_id=? AND status IN ('QUEUED','WAITING','RUNNING','PAUSED')",
                (cid,),
            ).fetchone()
            if existing:
                return run_value(existing["id"])
            campaign = c.execute(
                "SELECT * FROM research_campaigns WHERE id=?", (cid,)
            ).fetchone()
            if not campaign:
                raise HTTPException(404, "Research campaign missing")
            if not campaign["enabled"]:
                raise HTTPException(409, "Research campaign is paused")
            rid = core.uid("RESEARCH")
            settings = {
                **json.loads(campaign["settings"]),
                "board_id": campaign["board_id"],
            }
            c.execute(
                "INSERT INTO research_runs VALUES(?,?,?,?,?,?,?,?)",
                (
                    rid,
                    cid,
                    core.now(),
                    core.now(),
                    "QUEUED",
                    0,
                    json.dumps({"settings": settings}),
                    None,
                ),
            )
        core.log("research_started", {"id": rid, "campaign": cid})
        return run_value(rid)

    def tick():
        for campaign in core.rows(
            "SELECT * FROM research_campaigns WHERE enabled=1 AND next_run<=? ORDER BY next_run LIMIT 1",
            (time.time(),),
        ):
            with core.lock:
                if not core.rows(
                    "SELECT id FROM research_campaigns WHERE id=? AND enabled=1",
                    (campaign["id"],),
                ):
                    continue
                settings = json.loads(campaign["settings"])
                core.execute(
                    "UPDATE research_campaigns SET next_run=? WHERE id=?",
                    (
                        next_scheduled(
                            settings["cron_expression"],
                            time.time(),
                            settings["interval_minutes"],
                        ),
                        campaign["id"],
                    ),
                )
                launch(campaign["id"])
        with gate:
            if active:
                return
            pending = core.rows(
                "SELECT id FROM research_runs WHERE status IN ('QUEUED','WAITING','RUNNING') ORDER BY updated LIMIT 1"
            )
            if pending:
                rid = pending[0]["id"]
                active.add(rid)
                threading.Thread(target=execute_run, args=(rid,), daemon=True).start()

    def loop():
        while not core.stopping.wait(2):
            try:
                core.heartbeat("online-research")
                tick()
            except Exception as e:
                core.log("research_scheduler_failed", {"error": str(e)[:800]})

    @core.app.on_event("startup")
    def start():
        core.execute(
            "UPDATE research_tasks SET status='QUEUED',error='Interrupted; resume checkpoint' WHERE status='RUNNING'"
        )
        threading.Thread(target=loop, daemon=True).start()

    @core.app.get("/api/research/providers")
    def providers():
        return [
            {
                "id": key,
                "name": name,
                "state": core.onion["status"]()["state"]
                if key == "onion"
                else "KEY CONFIGURED"
                if key in ("brave", "brave_images")
                and os.environ.get("BRAVE_SEARCH_API_KEY")
                else "API KEY REQUIRED"
                if key in ("brave", "brave_images")
                else "PUBLIC CONNECTOR · REACHABILITY CHECKED PER RUN",
            }
            for key, name in PROVIDERS.items()
        ]

    @core.app.get("/api/research")
    def listing():
        campaigns = core.rows("SELECT * FROM research_campaigns ORDER BY created DESC")
        for c in campaigns:
            c["settings"] = json.loads(c["settings"])
        return {
            "campaigns": campaigns,
            "runs": [
                run_value(r["id"])
                for r in core.rows(
                    "SELECT id FROM research_runs ORDER BY created DESC LIMIT 30"
                )
            ],
            "discovery": [
                {**r, "data": json.loads(r["data"])}
                for r in core.rows(
                    "SELECT * FROM research_discovery ORDER BY last_seen DESC LIMIT 100"
                )
            ],
        }

    def validate_input(value: CampaignInput):
        if any(p not in PROVIDERS for p in value.providers) or len(
            set(value.providers)
        ) != len(value.providers):
            raise HTTPException(
                422, "Choose distinct supported public research providers"
            )
        if value.collect_all_seed_images and (
            not value.collect_images or not value.seeds
        ):
            raise HTTPException(
                422,
                "Collecting all seed-page images requires image collection and explicit public seed URLs",
            )
        if value.provider not in ("deterministic", "ollama", "anthropic"):
            raise HTTPException(422, "Unsupported analysis provider")
        try:
            validate_schedule(value.cron_expression)
            for q in value.queries:
                if not 2 <= len(q.strip()) <= 400:
                    raise ValueError("Each query must contain 2–400 characters")
            for seed in value.seeds:
                validate_onion_url(seed) if (urlparse(seed).hostname or "").endswith(
                    ".onion"
                ) else core.validate_url(seed)
            for domain in value.allowed_domains:
                validate_onion_url("http://" + domain) if domain.endswith(
                    ".onion"
                ) else core.validate_url("https://" + domain)
            if "onion" in value.providers and not any(
                (urlparse(s).hostname or "").endswith(".onion") for s in value.seeds
            ):
                raise ValueError("Onion research requires public v3 onion seed URLs")
            if "feeds" in value.providers and not any(
                not (urlparse(s).hostname or "").endswith(".onion") for s in value.seeds
            ):
                raise ValueError(
                    "Feed research requires a public feed/disclosure-page URL"
                )
        except ValueError as e:
            raise HTTPException(422, str(e))

    @core.app.post("/api/research")
    def create(value: CampaignInput):
        validate_input(value)
        cid, bid = core.uid("CAMPAIGN"), core.uid("BOARD")
        with core.lock, core.db() as c:
            c.execute(
                "INSERT INTO boards VALUES(?,?,?)",
                (
                    bid,
                    "Research · " + value.name,
                    json.dumps({"nodes": [], "edges": []}),
                ),
            )
            c.execute(
                "INSERT INTO research_campaigns VALUES(?,?,?,?,?,?,?)",
                (
                    cid,
                    value.name,
                    json.dumps(value.model_dump()),
                    1,
                    time.time(),
                    core.now(),
                    bid,
                ),
            )
        core.log("research_campaign_created", {"id": cid, "providers": value.providers})
        return {"id": cid, "board_id": bid}

    @core.app.patch("/api/research/{cid}")
    def edit(cid: str, value: CampaignInput):
        if not core.rows("SELECT id FROM research_campaigns WHERE id=?", (cid,)):
            raise HTTPException(404, "Research campaign missing")
        validate_input(value)
        core.execute(
            "UPDATE research_campaigns SET name=?,settings=? WHERE id=?",
            (value.name, json.dumps(value.model_dump()), cid),
        )
        core.log(
            "research_campaign_updated",
            {
                "id": cid,
                "providers": value.providers,
                "effective": "Next run; current run retains its settings snapshot",
            },
        )
        return {
            "id": cid,
            "settings": value.model_dump(),
            "current_run_unchanged": True,
        }

    @core.app.post("/api/research/{cid}/{action}")
    def control(cid: str, action: str):
        if not core.rows("SELECT id FROM research_campaigns WHERE id=?", (cid,)):
            raise HTTPException(404, "Research campaign missing")
        if action not in ("pause", "resume", "cancel", "run"):
            raise HTTPException(422, "Choose pause, resume, cancel or run")
        with core.lock:
            if action in ("pause", "cancel"):
                core.execute(
                    "UPDATE research_campaigns SET enabled=0 WHERE id=?", (cid,)
                )
                for r in core.rows(
                    "SELECT id FROM research_runs WHERE campaign_id=? AND status IN ('QUEUED','WAITING','RUNNING','PAUSED')",
                    (cid,),
                ):
                    value = run_value(r["id"])
                    value["data"]["paused_at"] = time.time()
                    update(
                        r["id"],
                        force=True,
                        data=value["data"],
                        status="PAUSED" if action == "pause" else "CANCELLED",
                    )
                    for item in [
                        json.loads(j["data"])
                        for j in core.rows(
                            "SELECT data FROM research_run_jobs WHERE run_id=?",
                            (r["id"],),
                        )
                    ]:
                        if item["owned"]:
                            j = core.rows(
                                "SELECT status FROM jobs WHERE id=?", (item["job_id"],)
                            )
                            if j and j[0]["status"] not in terminal:
                                core.job_control(item["job_id"], action)
                    iid = value["data"].get("investigation_id")
                    if iid:
                        inv = core.investigator["value"](iid)
                        if inv["status"] not in ("COMPLETE", "FAILED", "CANCELLED"):
                            core.investigator["control"](iid, action)
            else:
                core.execute(
                    "UPDATE research_campaigns SET enabled=1,next_run=? WHERE id=?",
                    (time.time(), cid),
                )
                for r in core.rows(
                    "SELECT id FROM research_runs WHERE campaign_id=? AND status='PAUSED'",
                    (cid,),
                ):
                    value = run_value(r["id"])
                    if value["data"].get("deadline"):
                        value["data"]["deadline"] += time.time() - value["data"].get(
                            "paused_at", time.time()
                        )
                    value["data"].pop("paused_at", None)
                    update(r["id"], force=True, data=value["data"], status="QUEUED")
                    for item in [
                        json.loads(j["data"])
                        for j in core.rows(
                            "SELECT data FROM research_run_jobs WHERE run_id=?",
                            (r["id"],),
                        )
                    ]:
                        j = core.rows(
                            "SELECT status FROM jobs WHERE id=?", (item["job_id"],)
                        )
                        if item["owned"] and j and j[0]["status"] == "PAUSED":
                            core.job_control(item["job_id"], "resume")
                    iid = value["data"].get("investigation_id")
                    if iid and core.investigator["value"](iid)["status"] == "PAUSED":
                        core.investigator["control"](iid, "resume")
        core.log("research_" + action, {"campaign": cid})
        return {"ok": True}

    return {
        "tick": tick,
        "advance": advance,
        "launch": launch,
        "value": run_value,
        "create": create,
    }
