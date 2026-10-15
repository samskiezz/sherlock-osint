"""Durable UTC cron and interval scheduler. No host shell, crontab or unrestricted agent execution."""

import json
import time
import threading
import re
import defusedxml.ElementTree as ET
from urllib.parse import quote, urljoin
from datetime import datetime, timezone
from croniter import croniter


def next_scheduled(expression, timestamp, interval_minutes):
    if not expression:
        return timestamp + interval_minutes * 60
    return croniter(
        expression, datetime.fromtimestamp(timestamp, timezone.utc)
    ).get_next(float)


def validate_schedule(expression):
    if not expression:
        return
    if len(expression.split()) != 5 or not croniter.is_valid(expression):
        raise ValueError("Use a valid five-field cron expression in UTC")
    iterator = croniter(
        expression, datetime.now(timezone.utc), max_years_between_matches=5
    )
    times = [iterator.get_next(float) for _ in range(8)]
    if any(b - a < 300 for a, b in zip(times, times[1:])):
        raise ValueError(
            "Source discovery schedules must be at least five minutes apart"
        )


def nasa_downloads(data):
    """Only explicitly public, published NASA originals; never catalogue substitutes."""
    found = []
    for item in data.get("results", [])[:10]:
        if item.get("distribution") != "PUBLIC":
            continue
        for download in item.get("downloads", []):
            path = download.get("links", {}).get("pdf")
            if (
                path
                and not download.get("draft")
                and download.get("mimetype") == "application/pdf"
            ):
                url = urljoin("https://ntrs.nasa.gov", path)
                if url.startswith("https://ntrs.nasa.gov/api/citations/"):
                    found.append((url, item.get("title", "NASA technical report")))
                    break
    return found


def archive_captures(data):
    if not data or not isinstance(data[0], list):
        return []
    fields = data[0]
    found = []
    for values in data[1:11]:
        row = dict(zip(fields, values))
        stamp, original = row.get("timestamp", ""), row.get("original", "")
        if (
            re.fullmatch(r"\d{14}", stamp)
            and original.startswith(("http://", "https://"))
            and row.get("statuscode") == "200"
        ):
            found.append(
                (
                    f"https://web.archive.org/web/{stamp}id_/{original}",
                    f"Historical capture · {stamp[:4]}-{stamp[4:6]}-{stamp[6:8]} · {original}",
                )
            )
    return found


def install(core):
    core.execute(
        """CREATE TABLE IF NOT EXISTS watches(id TEXT PRIMARY KEY,name TEXT,mode TEXT,target TEXT,interval_minutes INTEGER,enabled INTEGER,next_run REAL,last_run REAL,last_error TEXT,runs INTEGER DEFAULT 0)"""
    )
    core.execute(
        """CREATE TABLE IF NOT EXISTS discovery(watch_id TEXT,url TEXT,title TEXT,first_seen TEXT,job_id TEXT,PRIMARY KEY(watch_id,url))"""
    )
    core.execute(
        """CREATE TABLE IF NOT EXISTS watch_runs(id TEXT PRIMARY KEY,watch_id TEXT,started TEXT,status TEXT,discovered INTEGER,queued INTEGER,error TEXT)"""
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS watch_analyses(job_id TEXT PRIMARY KEY,watch_id TEXT,run_id TEXT,status TEXT,error TEXT,created TEXT)"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS watch_schedules(watch_id TEXT PRIMARY KEY,expression TEXT)"
    )
    from pydantic import BaseModel, Field
    from fastapi import HTTPException

    class WatchInput(BaseModel):
        name: str = Field(min_length=1, max_length=200)
        mode: str = "url"
        target: str = Field(min_length=1, max_length=1000)
        interval_minutes: int = Field(default=60, ge=5, le=525600)
        cron_expression: str = Field(default="", max_length=100)

    def enqueue(watch, url, title):
        from .app import Acquire

        if not core.rows(
            "SELECT id FROM watches WHERE id=? AND enabled=1", (watch["id"],)
        ):
            return False

        if watch["mode"] != "url" and core.rows(
            "SELECT url FROM discovery WHERE watch_id=? AND url=?", (watch["id"], url)
        ):
            return False
        job = core.queue(Acquire(url=url, title=title))
        core.execute(
            "INSERT OR IGNORE INTO discovery VALUES(?,?,?,?,?)",
            (watch["id"], url, title, core.now(), job["id"]),
        )
        return True

    def discover(w):
        if w["mode"] == "url":
            return [(w["target"], w["name"])]
        if w["mode"] in ("nasa", "archive"):
            url = (
                (
                    "https://ntrs.nasa.gov/api/citations/search?keyword="
                    + quote(w["target"])
                    + "&page.size=10"
                )
                if w["mode"] == "nasa"
                else (
                    "https://web.archive.org/cdx/search/cdx?output=json&filter=statuscode:200&collapse=timestamp:4&limit=10&url="
                    + quote(w["target"], safe="")
                )
            )
            core.robots_allowed(url)
            body, final, headers, _ = core.fetch(url)
            eid = core.preserve(
                body,
                w["mode"].upper() + " discovery response · " + w["target"],
                final,
                headers,
            )
            core.process(eid)
            data = json.loads(body)
            found = (
                nasa_downloads(data) if w["mode"] == "nasa" else archive_captures(data)
            )
            core.log(
                "structured_source_discovery",
                {
                    "watch": w["id"],
                    "catalogue_evidence": eid,
                    "eligible_originals": len(found),
                    "mode": w["mode"],
                },
            )
            return found
        if w["mode"] == "crossref":
            url = (
                "https://api.crossref.org/works?rows=20&sort=score&query.bibliographic="
                + quote(w["target"])
            )
            core.robots_allowed(url)
            body, final, headers, _ = core.fetch(url)
            eid = core.preserve(
                body, "Crossref discovery response · " + w["target"], final, headers
            )
            core.process(eid)
            data = json.loads(body)
            terms = [
                t.lower()
                for t in re.findall(r"\w+", w["target"])
                if len(t) > 2 and t.lower() not in {"the", "and", "for", "with"}
            ]
            found = []
            for item in data.get("message", {}).get("items", []):
                title = (item.get("title") or ["Untitled research record"])[0]
                haystack = (
                    title
                    + " "
                    + item.get("abstract", "")
                    + " "
                    + " ".join(item.get("subject", []))
                ).lower()
                if item.get("URL") and terms and all(t in haystack for t in terms):
                    found.append((item["URL"], title))
            core.log(
                "discovery_relevance_filter",
                {
                    "id": w["id"],
                    "raw_matches": len(data.get("message", {}).get("items", [])),
                    "matched_terms": terms,
                    "eligible": len(found),
                },
            )
            return found[:10]
        core.robots_allowed(w["target"])
        body, final, headers, _ = core.fetch(w["target"])
        eid = core.preserve(body, "Discovery feed · " + w["name"], final, headers)
        core.process(eid)
        root = ET.fromstring(body)
        found = []
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title") or w["name"]
            url = item.findtext("link")
            enc = item.find("enclosure")
            if enc is not None and enc.get("url"):
                url = enc.get("url")
            if url:
                found.append((urljoin(final, url), title))
        atom = "{http://www.w3.org/2005/Atom}"
        for item in root.findall(".//" + atom + "entry")[:10]:
            links = item.findall(atom + "link")
            link = next(
                (x for x in links if x.get("rel", "alternate") == "alternate"), None
            )
            if link is not None and link.get("href"):
                found.append(
                    (
                        urljoin(final, link.get("href")),
                        item.findtext(atom + "title") or w["name"],
                    )
                )
        return found[:10]

    def run(w):
        rid = core.uid("RUN")
        core.execute(
            "INSERT INTO watch_runs VALUES(?,?,?,?,?,?,?)",
            (rid, w["id"], core.now(), "RUNNING", 0, 0, None),
        )
        try:
            found = discover(w)
            queued = 0
            for url, title in found:
                if enqueue(w, url, title):
                    queued += 1
            core.execute(
                "UPDATE watch_runs SET status=?,discovered=?,queued=? WHERE id=?",
                ("COMPLETE", len(found), queued, rid),
            )
            core.execute("UPDATE watches SET last_error=NULL WHERE id=?", (w["id"],))
            core.log(
                "watch_complete",
                {"id": w["id"], "run": rid, "discovered": len(found), "queued": queued},
            )
        except Exception as e:
            core.execute(
                "UPDATE watch_runs SET status=?,error=? WHERE id=?",
                ("FAILED", str(e)[:800], rid),
            )
            core.execute(
                "UPDATE watches SET last_error=?,next_run=? WHERE id=?",
                (
                    str(e)[:800],
                    time.time() + min(w["interval_minutes"], 5) * 60,
                    w["id"],
                ),
            )
            core.log("watch_failed", {"id": w["id"], "error": str(e)[:800]})

    def tick():
        # Automatically audit each newly processed acquisition once. Original
        # preservation, extraction and seven investigative stages remain distinct.
        for item in core.rows(
            "SELECT d.watch_id,d.job_id,j.evidence_id,w.name FROM discovery d JOIN jobs j ON j.id=d.job_id JOIN watches w ON w.id=d.watch_id LEFT JOIN watch_analyses a ON a.job_id=d.job_id WHERE j.status='COMPLETE' AND a.job_id IS NULL AND w.enabled=1 LIMIT 2"
        ):
            try:
                prior = core.rows(
                    "SELECT a.run_id FROM watch_analyses a JOIN jobs j ON j.id=a.job_id JOIN investigations i ON i.id=a.run_id WHERE a.watch_id=? AND j.evidence_id=? AND i.status='COMPLETE' LIMIT 1",
                    (item["watch_id"], item["evidence_id"]),
                )
                if prior:
                    core.execute(
                        "INSERT OR IGNORE INTO watch_analyses VALUES(?,?,?,?,?,?)",
                        (
                            item["job_id"],
                            item["watch_id"],
                            None,
                            "UNCHANGED",
                            "Original already audited; repeat retrieval preserved in custody metadata",
                            core.now(),
                        ),
                    )
                    continue
                from .investigator import InvestigationInput

                with core.lock, core.db() as c:
                    if c.execute(
                        "SELECT 1 FROM watch_analyses WHERE job_id=?", (item["job_id"],)
                    ).fetchone():
                        continue
                    # create() commits to the shared connection separately; reserve
                    # first, and restart recovery releases interrupted reservations.
                    c.execute(
                        "INSERT INTO watch_analyses VALUES(?,?,?,?,?,?)",
                        (
                            item["job_id"],
                            item["watch_id"],
                            None,
                            "QUEUING",
                            None,
                            core.now(),
                        ),
                    )
                audit_run = core.investigator["create"](
                    InvestigationInput(
                        question="Audit the acquired original for this watch: "
                        + item["name"],
                        evidence_ids=[item["evidence_id"]],
                    )
                )
                core.execute(
                    "UPDATE watch_analyses SET run_id=?,status='QUEUED' WHERE job_id=?",
                    (audit_run["id"], item["job_id"]),
                )
            except Exception as e:
                core.execute(
                    "UPDATE watch_analyses SET status='FAILED',error=? WHERE job_id=?",
                    (str(e)[:800], item["job_id"]),
                )
        core.execute(
            "UPDATE watch_analyses SET status=COALESCE((SELECT status FROM investigations WHERE investigations.id=watch_analyses.run_id),status) WHERE run_id IS NOT NULL"
        )
        for w in core.rows(
            "SELECT w.*,s.expression cron_expression FROM watches w LEFT JOIN watch_schedules s ON s.watch_id=w.id WHERE w.enabled=1 AND w.next_run<=? ORDER BY w.next_run LIMIT 2",
            (time.time(),),
        ):
            # Commit next run before work; prevent a missed interval from creating a backlog storm.
            core.execute(
                "UPDATE watches SET next_run=?,last_run=?,runs=runs+1 WHERE id=?",
                (
                    next_scheduled(
                        w.get("cron_expression"), time.time(), w["interval_minutes"]
                    ),
                    time.time(),
                    w["id"],
                ),
            )
            run(w)

    def loop():
        while not core.stopping.wait(3):
            try:
                core.heartbeat("scheduled-discovery")
                tick()
            except Exception as error:
                core.log("scheduler_tick_failed", {"error": str(error)[:800]})

    @core.app.on_event("startup")
    def start_scheduler():
        core.execute(
            "DELETE FROM watch_analyses WHERE status='QUEUING' AND run_id IS NULL"
        )
        core.execute(
            "UPDATE watch_runs SET status='INTERRUPTED',error='Service restarted during discovery' WHERE status='RUNNING'"
        )
        threading.Thread(target=loop, daemon=True).start()

    @core.app.get("/api/watches")
    def watches():
        return {
            "watches": core.rows(
                "SELECT w.*,COALESCE(s.expression,'') cron_expression FROM watches w LEFT JOIN watch_schedules s ON s.watch_id=w.id ORDER BY name"
            ),
            "runs": core.rows(
                "SELECT * FROM watch_runs ORDER BY started DESC LIMIT 50"
            ),
            "discovery": core.rows(
                "SELECT * FROM discovery ORDER BY first_seen DESC LIMIT 100"
            ),
            "analyses": core.rows(
                "SELECT * FROM watch_analyses ORDER BY created DESC LIMIT 100"
            ),
        }

    @core.app.post("/api/watches")
    def create(w: WatchInput):
        try:
            validate_schedule(w.cron_expression)
        except Exception as error:
            raise HTTPException(422, str(error))
        if w.mode not in ("url", "rss", "crossref", "nasa", "archive"):
            raise HTTPException(422, "Supported: url, rss, crossref, nasa, archive")
        if w.mode not in ("crossref", "nasa"):
            try:
                core.validate_url(w.target)
            except Exception as e:
                raise HTTPException(422, str(e))
        wid = core.uid("WATCH")
        core.execute(
            "INSERT INTO watches VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                wid,
                w.name,
                w.mode,
                w.target,
                w.interval_minutes,
                1,
                time.time(),
                None,
                None,
                0,
            ),
        )
        core.log("watch_created", {"id": wid, "mode": w.mode, "target": w.target})
        core.execute(
            "INSERT OR REPLACE INTO watch_schedules VALUES(?,?)",
            (wid, w.cron_expression),
        )
        return {"id": wid}

    @core.app.put("/api/watches/{wid}")
    def edit(wid: str, w: WatchInput):
        try:
            validate_schedule(w.cron_expression)
        except Exception as error:
            raise HTTPException(422, str(error))
        if not core.rows("SELECT id FROM watches WHERE id=?", (wid,)):
            raise HTTPException(404, "Watch missing")
        if w.mode not in ("url", "rss", "crossref", "nasa", "archive"):
            raise HTTPException(422, "Unsupported discovery source")
        if w.mode not in ("crossref", "nasa"):
            try:
                core.validate_url(w.target)
            except Exception as e:
                raise HTTPException(422, str(e))
        core.execute(
            "UPDATE watches SET name=?,mode=?,target=?,interval_minutes=?,next_run=? WHERE id=?",
            (w.name, w.mode, w.target, w.interval_minutes, time.time(), wid),
        )
        core.execute(
            "INSERT OR REPLACE INTO watch_schedules VALUES(?,?)",
            (wid, w.cron_expression),
        )
        core.log("watch_updated", {"id": wid})
        return {"ok": True}

    @core.app.post("/api/watches/{wid}/{action}")
    def control(wid: str, action: str):
        if not core.rows("SELECT id FROM watches WHERE id=?", (wid,)):
            raise HTTPException(404, "Watch missing")
        if action == "pause":
            core.execute("UPDATE watches SET enabled=0 WHERE id=?", (wid,))
        elif action == "resume":
            core.execute("UPDATE watches SET enabled=1 WHERE id=?", (wid,))
        elif action == "run":
            core.execute(
                "UPDATE watches SET enabled=1,next_run=? WHERE id=?", (time.time(), wid)
            )
        elif action == "delete":
            core.execute("DELETE FROM watch_schedules WHERE watch_id=?", (wid,))
            core.execute("DELETE FROM watches WHERE id=?", (wid,))
        else:
            raise HTTPException(422, "Unknown watch action")
        core.log("watch_" + action, {"id": wid})
        return {"ok": True}

    return {"tick": tick, "discover": discover}
