"""A read-only case result feed: viewing the interface never initiates analysis."""

import json
import os
from collections import Counter


def install(core):
    """Expose persisted automatic progress and concise findings, separating blockers."""

    @core.app.get("/api/case/overview")
    def overview():
        """Summarise actual autonomous work; no tool invocation or queue writes."""
        settings = core.autopilot["settings"]()
        originals = core.rows(
            "SELECT count(*) AS n,coalesce(sum(size),0) AS bytes FROM evidence WHERE path IS NOT NULL"
        )[0]
        latest = {}
        for r in core.rows(
            "SELECT d.evidence_id,d.created,r.id,r.status,r.data FROM autopilot_dispatch d JOIN automation_runs r ON d.run_id=r.id ORDER BY d.created DESC,d.rowid DESC"
        ):
            latest.setdefault(r["evidence_id"], r)
        statuses = Counter(x["status"] for x in latest.values())
        active = []
        for row in latest.values():
            if row["status"] not in ["QUEUED", "RUNNING"]:
                continue
            d = json.loads(row["data"])
            steps = len(d.get("plan", {}).get("steps", []))
            remaining = d.get("remaining_steps", steps)
            title = core.rows(
                "SELECT title FROM evidence WHERE id=?", (row["evidence_id"],)
            )[0]["title"]
            active.append(
                {
                    "id": row["id"],
                    "evidence_id": row["evidence_id"],
                    "title": title,
                    "status": row["status"],
                    "completed_steps": max(0, steps - remaining),
                    "total_steps": steps,
                }
            )
        watches = core.rows(
            "SELECT count(*) AS n,min(next_run) AS next_due FROM research_campaigns WHERE enabled=1"
        )[0]
        queue = core.rows(
            "SELECT count(*) AS n FROM jobs WHERE status IN ('QUEUED','FETCHING','PROCESSING','RUNNING','DOWNLOADING','VERIFYING','EXTRACTING')"
        )[0]["n"]
        blockers = []
        if not os.environ.get("X_BEARER_TOKEN"):
            blockers.append(
                {
                    "title": "X / Twitter collection",
                    "reason": "An authorised X API credential is required. The monitor is saved and waiting.",
                }
            )
        onion = core.onion["status"]() if hasattr(core, "onion") else None
        if onion and not onion.get("ready"):
            blockers.append(
                {
                    "title": "Onion collection",
                    "reason": onion.get("reason") or "Tor connection is not ready.",
                }
            )
        visual_reviews = core.rows(
            "SELECT status,count(*) AS n FROM visual_review_state GROUP BY status"
        )
        visual_states = {r["status"]: r["n"] for r in visual_reviews}
        if visual_states.get("FAILED"):
            blockers.append(
                {
                    "title": "Image review needs attention",
                    "reason": f"{visual_states['FAILED']} image reviews exhausted their automatic retries. Exact failures remain in the audit trail.",
                }
            )
        if hasattr(core, "research"):
            seen_campaigns = set()
            for run in core.rows(
                "SELECT campaign_id,id,status FROM research_runs ORDER BY created DESC,rowid DESC"
            ):
                if run["campaign_id"] in seen_campaigns:
                    continue
                seen_campaigns.add(run["campaign_id"])
                if run["status"] not in ("FAILED", "PARTIAL"):
                    continue
                failed = core.rows(
                    "SELECT objective,error FROM research_tasks WHERE run_id=? AND status='FAILED' LIMIT 2",
                    (run["id"],),
                )
                if failed:
                    campaign = core.rows(
                        "SELECT name FROM research_campaigns WHERE id=?",
                        (run["campaign_id"],),
                    )
                    blockers.append(
                        {
                            "title": "Source watch: "
                            + (campaign[0]["name"] if campaign else run["campaign_id"]),
                            "reason": "; ".join(
                                (x["error"] or "Collection failed")[:200]
                                for x in failed
                            ),
                        }
                    )
        reviews = statuses["FAILED"] + statuses["PARTIAL"]
        if reviews:
            blockers.append(
                {
                    "title": f"{reviews} source profiles need review",
                    "reason": "Some compatible operations failed or exhausted their budgets. Successful results are retained.",
                }
            )
        return {
            "enabled": settings.get("enabled", False),
            "mode": "AUTOMATIC" if settings.get("enabled") else "PAUSED",
            "originals": originals["n"],
            "preserved_bytes": originals["bytes"],
            "sources_completed": statuses["COMPLETE"],
            "sources_in_progress": statuses["RUNNING"] + statuses["QUEUED"],
            "active": active[:4],
            "watches": watches["n"],
            "next_research_due": watches["next_due"],
            "acquisitions_in_progress": queue,
            "stories": core.visual["explanations"](),
            "media": core.media_reports["portfolio"]()
            if hasattr(core, "media_reports")
            else {"items": [], "total": 0},
            "media_sources": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "enabled": bool(r["enabled"]),
                    "next_run": r["next_run"],
                    "providers": json.loads(r["settings"]).get("providers", []),
                    "queries": json.loads(r["settings"]).get("queries", []),
                }
                for r in core.rows(
                    "SELECT id,name,enabled,next_run,settings FROM research_campaigns WHERE json_extract(settings,'$.collect_images')=1 ORDER BY created DESC"
                )
            ],
            "visual_reviews": visual_states,
            "attention": blockers,
            "last_activity": core.rows(
                "SELECT max(updated) AS utc FROM automation_runs"
            )[0]["utc"],
            "independent_actions_limit": 4,
            "service_scope": "Background services continue when this page is closed; this workspace must remain running.",
        }

    return {"overview": overview}
