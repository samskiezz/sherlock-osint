"""Automatic workspace result streams over existing durable workers and receipts."""

import json
from fastapi import HTTPException
from .receipt_sources import receipt_sources, derivative_binding_valid

SCOPES = {
    "lab": ("Automatic analysis", ("decoder.", "gematria.", "visual.", "forensics.")),
    "automation": ("Automatic workflows", ("",)),
    "knowledge": (
        "Automatic evidence reading",
        ("text.extractive_summary", "model.cited_note", "text.identifiers"),
    ),
    "patents": ("Patent intelligence", ("text.identifiers",)),
    "photos": ("Automatic photo review", ("visual.",)),
    "tradecraft": ("Evidence and competing explanations", ("model.cited_note",)),
    "research": ("Scheduled research", ("research.", "acquisition.")),
    "onion": ("Onion document research", ("onion.",)),
    "watch": ("Continuous source watches", ("research.", "acquisition.")),
    "cipher": (
        "Automatic cipher and gematria analysis",
        ("decoder.", "gematria.", "cipher.", "forensics.screen"),
    ),
    "archives": ("Historical archive review", ("archive.",)),
    "agents": ("Automatic investigator", ("model.cited_note",)),
}


def describe(tool, output):
    """Translate completed receipts into concise outcomes without inventing findings."""
    if not isinstance(output, dict):
        return str(output)[:500]
    if tool == "decoder.auto":
        useful = [c for c in output.get("candidates", []) if c.get("useful")]
        return (
            ("Candidate decoding: " + str(useful[0].get("data", ""))[:350])
            if useful
            else "Automatic decoder found no useful candidate in this tested input."
        )
    if tool == "gematria.all":
        sums = [
            f"{r.get('table', '').replace('_', ' ')}: {r.get('sum')}"
            for r in output.get("results", [])[:4]
        ]
        return (
            "Gematria comparison · "
            + "; ".join(sums)
            + ". Numerical matches do not establish a message."
        )
    if tool == "text.extractive_summary":
        return (
            "Source excerpts: "
            + " … ".join(r.get("quote", "") for r in output.get("result", [])[:2])[:600]
        )
    for key in ("summary", "assessment", "validation", "status", "transformed", "note"):
        if isinstance(output.get(key), str):
            return output[key][:600]
    if tool == "visual.search":
        return f"Compared with {output.get('compared', 0)} stored references. Candidate similarities require review; no inference of a prediction."
    return "Completed source-bound check. The saved receipt contains its method, output and limitations."


def snapshot(core, workspace):
    """Read existing automation, appropriate source watches and completed results."""
    title, prefixes = SCOPES[workspace]
    case_sources = set()
    for board in core.rows("SELECT data FROM boards"):
        for edge in json.loads(board["data"]).get("edges", []):
            relationship = edge.get("data", {})
            if (
                relationship.get("state") in ("DOCUMENTED", "CORROBORATED")
                and relationship.get("proposed_by") != "Acquisition organiser"
            ):
                case_sources.update(
                    c["id"] for c in relationship.get("evidence", []) if c.get("id")
                )
    receipts = core.rows(
        "SELECT id,status,data FROM automation_receipts "
        "WHERE EXISTS (SELECT 1 FROM json_each(?) p WHERE json_extract(data,'$.tool') LIKE p.value || '%') "
        "ORDER BY CASE WHEN json_extract(data,'$.inputs.evidence_id') IN (SELECT value FROM json_each(?)) THEN 0 ELSE 1 END,rowid DESC LIMIT 120",
        (json.dumps(prefixes), json.dumps(sorted(case_sources))),
    )
    results, seen, checked = [], set(), {}
    for row in receipts:
        if row["status"] != "COMPLETE":
            continue
        d = json.loads(row["data"])
        result = d.get("result", {})
        sources = receipt_sources(d)
        source = next(iter(sources), None)
        if not source or not source.get("evidence_id"):
            continue
        eid = source["evidence_id"]
        if eid not in checked:
            try:
                checked[eid] = core.forensics["source"](eid)
            except (ValueError, OSError):
                checked[eid] = None
        if not checked[eid]:
            continue
        e, _, text_digest = checked[eid]
        if (
            source.get("original_sha256") != e["sha256"]
            or source.get("text_sha256") != text_digest
            or not derivative_binding_valid(core, source)
        ):
            continue
        all_sources_valid = True
        for bound in sources[1:]:
            other_id = bound.get("evidence_id")
            if other_id not in checked:
                try:
                    checked[other_id] = core.forensics["source"](other_id)
                except (ValueError, OSError):
                    checked[other_id] = None
            other = checked[other_id]
            if (
                not other
                or bound.get("original_sha256") != other[0]["sha256"]
                or bound.get("text_sha256") != other[2]
                or not derivative_binding_valid(core, bound)
            ):
                all_sources_valid = False
                break
        if not all_sources_valid:
            continue
        key = (eid, d["tool"])
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "id": row["id"],
                "evidence_id": eid,
                "title": e["title"],
                "method": d["tool"],
                "summary": describe(d["tool"], result.get("output", {})),
                "completed_at": d.get("finished_utc"),
                "limitations": result.get("limitations"),
                "status": row["status"],
                "source_scope": "Evidence supporting a documented case statement"
                if eid in case_sources
                else "Other collected material · interpretation not established",
            }
        )
        if len(results) >= 24:
            break
    records = []
    if workspace == "patents":
        for row in core.rows(
            "SELECT p.* FROM patent_records p JOIN evidence e ON e.id=p.evidence_id WHERE e.sha256=json_extract(p.data,'$.sha256') ORDER BY updated DESC LIMIT 24"
        ):
            d = json.loads(row["data"])
            records.append(
                {
                    "id": row["evidence_id"],
                    "evidence_id": row["evidence_id"],
                    "title": " · ".join(d.get("title", [])),
                    "summary": "Inventors: "
                    + ", ".join(d.get("inventors", []))
                    + ". Priority: "
                    + str(d.get("priority_date") or "unknown")
                    + ". "
                    + (d.get("abstract") or "")[:450],
                    "status": "PATENT DISCLOSURE · NOT EXPERIMENTAL PROOF",
                }
            )
        results = []
    if workspace == "archives":
        for row in core.rows(
            "SELECT id,title,created,metadata FROM evidence WHERE path IS NOT NULL AND title LIKE 'Historical capture%' ORDER BY created DESC LIMIT 24"
        ):
            records.append(
                {
                    "id": row["id"],
                    "evidence_id": row["id"],
                    "title": row["title"],
                    "summary": "Preserved historical webpage. Capture, publication and retrieval dates remain distinct; this does not establish that a game binary changed.",
                    "status": "ARCHIVED SOURCE",
                }
            )
    campaigns = []
    for row in core.rows(
        "SELECT id,name,enabled,next_run,settings FROM research_campaigns ORDER BY created DESC"
    ):
        s = json.loads(row["settings"])
        relevant = (
            workspace
            in (
                "research",
                "watch",
                "automation",
                "lab",
                "knowledge",
                "agents",
                "tradecraft",
            )
            or (workspace == "patents" and "patent" in row["name"].lower())
            or (workspace == "photos" and s.get("collect_images"))
            or (workspace == "onion" and "onion" in row["name"].lower())
            or (workspace == "archives" and "archive" in row["name"].lower())
        )
        if relevant:
            campaigns.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "enabled": bool(row["enabled"]),
                    "next_due": row["next_run"],
                    "cron": s.get("cron_expression"),
                    "providers": s.get("providers", []),
                }
            )
    if workspace in ("research", "watch", "onion") and campaigns:
        campaign_ids = tuple(c["id"] for c in campaigns)
        acquired = core.rows(
            "SELECT DISTINCT e.id,e.title,e.mime,e.created,e.status FROM research_discovery d "
            "JOIN jobs j ON j.id=d.job_id JOIN evidence e ON e.id=j.evidence_id "
            "WHERE d.campaign_id IN (SELECT value FROM json_each(?)) AND e.path IS NOT NULL "
            "AND e.mime!='application/json' ORDER BY e.created DESC LIMIT 24",
            (json.dumps(campaign_ids),),
        )
        records.extend(
            {
                "id": e["id"],
                "evidence_id": e["id"],
                "title": e["title"],
                "summary": "Original file preserved by scheduled research. Collected "
                + e["created"]
                + ". Acquisition is not confirmation of the claims in its content.",
                "status": "ACQUIRED SOURCE · " + e["mime"],
            }
            for e in acquired
        )
    dispatches = core.rows(
        "SELECT d.evidence_id,d.data,r.status FROM autopilot_dispatch d JOIN automation_runs r ON r.id=d.run_id ORDER BY d.created DESC LIMIT 100"
    )
    pending, skipped, dedup = [], {}, set()
    for d in dispatches:
        if d["evidence_id"] in dedup:
            continue
        dedup.add(d["evidence_id"])
        coverage = [
            c
            for c in json.loads(d["data"]).get("coverage", [])
            if any(c["tool"].startswith(p) for p in prefixes)
        ]
        if d["status"] in ("QUEUED", "RUNNING") and any(
            c["state"] == "SCHEDULED" for c in coverage
        ):
            pending.append({"evidence_id": d["evidence_id"], "status": d["status"]})
        for c in coverage:
            if c["state"] != "SCHEDULED":
                skipped.setdefault(c["tool"], c["reason"])
    blockers = []
    if workspace in ("onion", "watch", "research"):
        import os

        if not os.environ.get("X_BEARER_TOKEN"):
            blockers.append(
                "Live X collection is waiting for an authorised API credential."
            )
        tor = core.onion["status"]()
        if not tor.get("ready"):
            blockers.append(
                "Tor transport is unavailable; onion downloads cannot run. Publicly indexed leads are kept separate from acquired onion documents."
            )
    return {
        "workspace": workspace,
        "title": title,
        "enabled": core.autopilot["settings"]().get("enabled", False),
        "results": records + results,
        "watches": campaigns,
        "pending": pending,
        "blockers": blockers,
        "unavailable": [{"method": k, "reason": v} for k, v in skipped.items()],
        "scope": "Automatically selected compatible analyses of acquired originals. Showing up to 24 source-bound results from 120 matching receipts, prioritising sources of documented case statements; pending coverage uses the latest 100 source profiles. Methods requiring missing keys, baselines, labels or human judgments cannot be run meaningfully without them.",
    }


def install(core):
    """Register read-only result streams; opening tabs never launches duplicate work."""

    @core.app.get("/api/case/workspaces/{workspace}")
    def workspace_results(workspace: str):
        """Return the saved outputs for a supported automatic workspace."""
        if workspace not in SCOPES:
            raise HTTPException(404, "Unknown automatic workspace")
        return snapshot(core, workspace)

    @core.app.get("/api/case/receipts/{receipt_id}")
    def saved_receipt(receipt_id: str):
        """Open an existing receipt only if its original and text bindings still hold."""
        rows = core.rows(
            "SELECT status,data FROM automation_receipts WHERE id=?", (receipt_id,)
        )
        if not rows or rows[0]["status"] != "COMPLETE":
            raise HTTPException(404, "Completed receipt not found")
        data = json.loads(rows[0]["data"])
        result = data.get("result", {})
        sources = receipt_sources(data)
        if not sources:
            raise HTTPException(409, "Receipt has no source binding")
        for source in sources:
            try:
                original, _, digest = core.forensics["source"](
                    source.get("evidence_id")
                )
            except (OSError, ValueError) as error:
                raise HTTPException(
                    409, "Receipt source integrity could not be verified"
                ) from error
            if (
                source.get("original_sha256") != original["sha256"]
                or source.get("text_sha256") != digest
                or not derivative_binding_valid(core, source)
            ):
                raise HTTPException(409, "Receipt source binding is stale")
        return {
            "tool": data["tool"],
            "output": result.get("output"),
            "sources": sources,
            "limitations": result.get("limitations"),
            "finished_at": data.get("finished_utc"),
            "output_sha256": data.get("output_sha256"),
        }

    return {"snapshot": lambda workspace: snapshot(core, workspace)}
