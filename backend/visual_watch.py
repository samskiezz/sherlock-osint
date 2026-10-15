"""Unattended visual review independent of the text-analysis backlog."""

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor


def install(core):
    """Revisit acquired images on corpus changes using the shared isolated-parser limit."""
    core.execute(
        "CREATE TABLE IF NOT EXISTS visual_review_state(evidence_id TEXT PRIMARY KEY,fingerprint TEXT,status TEXT,updated TEXT,attempts INTEGER,retry_after REAL,error TEXT)"
    )

    def review(eid, fingerprint, attempt):
        """Preserve a durable receipt for automatic extraction, comparison and explanation."""
        core.execute(
            "INSERT OR REPLACE INTO visual_review_state VALUES(?,?,?,?,?,?,?)",
            (eid, fingerprint, "RUNNING", core.now(), attempt, 0, None),
        )
        try:
            try:
                source, features = core.visual["source"](eid)
            except ValueError:
                features = {}
            if features.get("version") != "0.12.0" or "panel_analysis" not in features:
                core.process(eid)
            result = core.visual["search"](eid, 20)
            core.execute(
                "UPDATE visual_review_state SET status=?,updated=?,error=NULL WHERE evidence_id=?",
                ("COMPLETE", core.now(), eid),
            )
            core.log(
                "automatic_visual_review_complete",
                {
                    "evidence_id": eid,
                    "comparison_id": result["id"],
                    "explanations": result.get("explanation_ids", []),
                },
            )
        except Exception as ex:
            core.execute(
                "UPDATE visual_review_state SET status=?,updated=?,retry_after=?,error=? WHERE evidence_id=?",
                (
                    "RETRY" if attempt < 3 else "FAILED",
                    core.now(),
                    time.time() + 30,
                    str(ex)[:700],
                    eid,
                ),
            )
            core.log(
                "automatic_visual_review_failed",
                {"evidence_id": eid, "attempt": attempt, "error": str(ex)[:700]},
            )

    def loop():
        """Automatically schedule bounded independent visual work while unattended mode is enabled."""
        inflight = {}
        with ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="sherlock-visual-review"
        ) as workers:
            while not core.stopping.wait(3):
                for eid, future in list(inflight.items()):
                    if future.done():
                        try:
                            future.result()
                        except Exception as ex:
                            core.log(
                                "visual_review_worker_error",
                                {"error": type(ex).__name__},
                            )
                        del inflight[eid]
                if not core.autopilot["settings"]().get("enabled"):
                    continue
                originals = core.rows(
                    "SELECT id,sha256 FROM evidence WHERE path IS NOT NULL AND mime LIKE 'image/%' ORDER BY created DESC,id"
                )
                contexts = core.rows(
                    "SELECT id,sha256 FROM evidence WHERE path IS NOT NULL AND mime LIKE '%html%' ORDER BY created DESC LIMIT 100"
                )
                corpus = hashlib.sha256(
                    json.dumps(
                        [originals, contexts, "visual-review-v13.1"], sort_keys=True
                    ).encode()
                ).hexdigest()
                for row in originals:
                    if len(inflight) >= 2:
                        break
                    eid = row["id"]
                    if eid in inflight:
                        continue
                    old = core.rows(
                        "SELECT * FROM visual_review_state WHERE evidence_id=?", (eid,)
                    )
                    attempt = 1
                    if old and old[0]["fingerprint"] == corpus:
                        if old[0]["status"] in ["COMPLETE", "FAILED"]:
                            continue
                        if old[0]["retry_after"] > time.time():
                            continue
                        attempt = old[0]["attempts"] + 1
                    inflight[eid] = workers.submit(review, eid, corpus, attempt)

    @core.app.on_event("startup")
    def start():
        """Resume pending image reviews after service restart without a browser action."""
        threading.Thread(target=loop, daemon=True).start()

    return {"review": review}
