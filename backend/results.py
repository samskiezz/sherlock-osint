"""Source-centred reading and exports over durable analysis; GETs never run tools."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
import time

from fastapi import HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from .automation import catalogue
from .automatic_workspaces import describe
from .receipt_sources import receipt_sources, derivative_binding_valid

WORKSPACES = [
    ("library", "Originals and extracted text"),
    ("entities", "Entities and provenance"),
    ("autonomous", "Case threads and supporting evidence"),
    ("lab", "Forensic analysis"),
    ("automation", "Workflow execution and schedules"),
    ("knowledge", "Evidence retrieval"),
    ("patents", "Patent intelligence"),
    ("photos", "Image comparisons"),
    ("tradecraft", "Competing explanations"),
    ("queue", "Acquisition queue"),
    ("watch", "Continuous watches"),
    ("research", "Source discovery"),
    ("onion", "Onion research"),
    ("timeline", "Chronology"),
    ("archives", "Archive comparison"),
    ("maps", "Map"),
    ("review", "Claim review"),
    ("cipher", "Ciphers and gematria"),
    ("graph", "Graph analysis"),
    ("agents", "Investigator"),
    ("vault", "Vault inventory"),
]
TERMINAL = {"COMPLETE", "PARTIAL", "FAILED", "CANCELLED"}


def readable(value, depth=0):
    """Plain-text export of arbitrary typed outputs, preserving negative results."""
    if depth > 12:
        return "[Nested output; use the JSON report for the full structure]"
    if value is None:
        return "No value reported"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dict):
        return (
            "\n".join(
                f"{k.replace('_', ' ')}: {readable(v, depth + 1)}"
                for k, v in value.items()
            )
            or "No entries reported"
        )
    if isinstance(value, list):
        return (
            "\n".join("- " + readable(v, depth + 1) for v in value)
            or "No matches in the tested input"
        )
    return str(value)


def install(core):
    tools = {t["id"]: t for t in catalogue()}

    def bound(data, checked, require_source=True):
        saved = data.get("result") or {}
        sources = receipt_sources(data)
        if require_source and not sources:
            return False
        for s in sources:
            if s.get("board_id") and data.get("tool", "").startswith("graph."):
                try:
                    graph = core.workspaces["graph"](
                        s["board_id"], documented_only=True
                    )
                    if hashlib.sha256(
                        json.dumps(graph, sort_keys=True).encode()
                    ).hexdigest() != s.get("graph_sha256"):
                        return False
                    continue
                except (ValueError, OSError, HTTPException):
                    return False
            sid = s.get("evidence_id")
            if sid not in checked:
                try:
                    other, _, digest = core.forensics["source"](sid)
                    checked[sid] = (other, digest)
                except (ValueError, OSError):
                    checked[sid] = None
            actual = checked[sid]
            if (
                not actual
                or actual[0]["sha256"] != s.get("original_sha256")
                or actual[1] != s.get("text_sha256")
            ):
                return False
            if not derivative_binding_valid(core, s):
                return False
        expected = data.get("output_sha256")
        try:
            return (
                not expected
                or hashlib.sha256(
                    json.dumps(saved, sort_keys=True, allow_nan=False).encode()
                ).hexdigest()
                == expected
            )
        except (ValueError, TypeError):
            return False

    def original(eid):
        found = core.rows("SELECT * FROM evidence WHERE id=?", (eid,))
        if not found:
            raise HTTPException(404, "Source not found")
        e = found[0]
        meta = json.loads(e["metadata"])
        source = {
            k: e[k]
            for k in (
                "id",
                "title",
                "kind",
                "mime",
                "status",
                "sha256",
                "size",
                "created",
                "url",
            )
        }
        source["file_url"] = f"/api/evidence/{eid}/file" if e["path"] else None
        source["preview_url"] = f"/api/evidence/{eid}/preview" if e["preview"] else None
        return e, meta, source

    def dispatch(eid):
        rows = core.rows(
            "SELECT * FROM autopilot_dispatch WHERE evidence_id=? ORDER BY created DESC,rowid DESC LIMIT 1",
            (eid,),
        )
        if not rows:
            return None, None
        item = rows[0]
        item["data"] = json.loads(item["data"])
        run = core.rows("SELECT * FROM automation_runs WHERE id=?", (item["run_id"],))
        if not run:
            return item, None
        run = run[0]
        run["data"] = json.loads(run["data"])
        return item, run

    def report(eid, include_outputs=True):
        e, meta, source = original(eid)
        d, run = dispatch(eid)
        result = {
            "source": source,
            "state": "PENDING",
            "reading": [],
            "information": [],
            "checks": [],
            "issues": [],
            "run_id": run["id"] if run else None,
            "coverage": d["data"].get("coverage", []) if d else [],
            "progress": {"complete": 0, "failed": 0, "skipped": 0, "total": 0},
            "scope": "Source excerpts and reproducible checks. Extracted names, dates and similarities require interpretation; they do not establish identity, causation or a verified allegation.",
        }
        try:
            current, _, digest = core.forensics["source"](eid)
        except (ValueError, OSError) as ex:
            result.update(state="BLOCKED", integrity="UNAVAILABLE", reason=str(ex))
            result["can_reprocess"] = str(ex) in {
                "Attested text derivative is required",
                "Indexed text differs from derivative",
            }
            result["issues"].append(meta.get("processing_failure") or str(ex))
            return result
        source["text_sha256"] = digest
        result["integrity"] = "VERIFIED"
        text = current["text"]
        result["text_characters"] = len(text)
        if not d or not run:
            result["reason"] = (
                "Waiting for automatic analysis"
                if core.autopilot["settings"]().get("enabled")
                else "Automatic analysis is paused"
            )
        elif (
            d["data"].get("source_sha256") != e["sha256"]
            or d["data"].get("text_sha256") != digest
        ):
            result["reason"] = (
                "Saved analysis used an older source version; waiting for fresh analysis"
            )
            result["coverage"] = []
            run = None
        else:
            result["state"] = run["status"]
            result["updated"] = run["updated"]
            result["active_pass"] = {
                "total": len(run["data"].get("plan", {}).get("steps", [])),
                "remaining": run["data"].get("remaining_steps", 0),
            }

        checked = {eid: (current, digest)}

        receipts = []
        if run:
            receipts = core.rows(
                "SELECT * FROM automation_receipts WHERE run_id=? ORDER BY rowid",
                (run["id"],),
            )
        # Keep valid previous results readable during a new pass or profile upgrade.
        extra = core.rows(
            "SELECT r.* FROM automation_receipts r WHERE "
            "(json_extract(r.data,'$.inputs.evidence_id')=? OR json_extract(r.data,'$.result.sources[0].evidence_id')=? "
            "OR json_extract(r.data,'$.result.output.evidence_id')=? OR EXISTS (SELECT 1 FROM autopilot_dispatch d WHERE d.run_id=r.run_id AND d.evidence_id=?)) "
            "AND r.run_id<>? "
            "ORDER BY r.rowid DESC LIMIT 101",
            (eid, eid, eid, eid, run["id"] if run else ""),
        )
        result["extra_results_truncated"] = len(extra) > 100
        receipts.extend(extra[:100])
        summaries, information, seen = [], {}, set()
        for receipt in receipts:
            receipt["data"] = json.loads(receipt["data"])
            data = receipt["data"]
            saved = data.get("result") or {}
            tool = data.get("tool", "unknown")
            key = (tool, json.dumps(data.get("inputs", {}), sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            state = receipt["status"]
            if state == "COMPLETE" and not bound(data, checked):
                result["issues"].append(
                    f"Withheld {tools.get(tool, {}).get('title', tool)}: saved source or output binding no longer verifies"
                )
                state = "WITHHELD"
            output = saved.get("output") if state == "COMPLETE" else None
            title = tools.get(tool, {}).get(
                "title", tool.replace(".", " · ").replace("_", " ")
            )
            summary = (
                describe(tool, output)
                if state == "COMPLETE"
                else data.get("error") or state.replace("_", " ").capitalize()
            )
            if (
                tool.startswith("text.")
                and isinstance(output, dict)
                and "result" in output
            ):
                value = output["result"]
                summary = (
                    (
                        f"{len(value)} entries in the tested source window"
                        if value
                        else "No matches in the tested source window"
                    )
                    if isinstance(value, list)
                    else readable(value)[:600]
                )
                if tool in {
                    "text.dates",
                    "text.identifiers",
                    "text.urls",
                    "text.emails",
                    "text.word_frequency",
                }:
                    information[tool] = {
                        "label": title,
                        "value": value,
                        "receipt_id": receipt["id"],
                    }
                if tool == "text.extractive_summary" and isinstance(value, list):
                    summaries.extend(
                        v["quote"]
                        for v in value
                        if isinstance(v, dict)
                        and isinstance(v.get("quote"), str)
                        and v["quote"] in text
                    )
            if tool == "evidence.verify" and state == "COMPLETE":
                summary = (
                    "Original bytes and extracted text both passed their SHA-256 checks"
                )
            if tool == "forensics.screen" and isinstance(output, dict):
                screen = output.get("data", output)
                summary = f"{screen.get('attempt_count', 0)} bounded transformation trials; {screen.get('validation', 'interpretation unvalidated')}"
            check = {
                "id": receipt["id"],
                "tool": tool,
                "title": title,
                "status": state,
                "summary": summary,
                "finished": data.get("finished_utc"),
                "error": data.get("error") if state != "COMPLETE" else None,
                "limitations": saved.get("limitations"),
                "sources": receipt_sources(data) if state == "COMPLETE" else [],
            }
            if include_outputs:
                check["output"] = output
            result["checks"].append(check)
        counts = Counter(c["status"] for c in result["checks"])
        if counts["WITHHELD"] and result["state"] == "COMPLETE":
            result["state"] = "PARTIAL"
        planned = len(run["data"].get("plan", {}).get("steps", [])) if run else 0
        result["progress"] = {
            "complete": counts["COMPLETE"],
            "failed": counts["FAILED"] + counts["WITHHELD"],
            "skipped": counts["SKIPPED"],
            "total": max(planned, len(result["checks"])),
        }
        # A useful reading exists even before the optional statistical/model tools finish.
        if not summaries and text.strip():
            summaries = [
                m.group().strip()
                for m in re.finditer(r"[^\n]+", text[:6000])
                if m.group().strip()
            ][:4]
        for quote in dict.fromkeys(summaries):
            quote = quote[:1200]
            start = text.find(quote)
            if start >= 0:
                result["reading"].append(
                    {
                        "quote": quote,
                        "start": start,
                        "end": start + len(quote),
                        "evidence_id": eid,
                    }
                )
            if len(result["reading"]) == 6:
                break
        result["reading_method"] = (
            "Saved extractive summary"
            if any(
                c["tool"] == "text.extractive_summary" and c["status"] == "COMPLETE"
                for c in result["checks"]
            )
            else "Opening source excerpts"
        )
        result["information"] = list(information.values())
        if not text.strip():
            result["issues"].append(
                "No text was extracted. Image/media diagnostics may still be available; a transcript or OCR is needed for text analysis."
            )
        return result

    def markdown(r):
        s = r["source"]
        lines = [
            f"# {s['title']}",
            "",
            f"Analysis: {r['state']}",
            f"Source integrity: {r.get('integrity', 'UNAVAILABLE')}",
            f"Evidence ID: {s['id']}",
            f"Original SHA-256: {s['sha256'] or 'Not acquired'}",
            f"Source URL: {s['url'] or 'User import'}",
            "",
            r["scope"],
            "",
            "## Source reading",
            "",
        ]
        for p in r["reading"]:
            lines.extend(
                [
                    f"> {p['quote'].replace(chr(10), chr(10) + '> ')}",
                    f"Characters {p['start']}–{p['end']} in the attested extract.",
                    "",
                ]
            )
        if r.get("reason"):
            lines.extend([r["reason"], ""])
        lines.extend(
            [
                "## Attention needed",
                "",
                *(r["issues"] or ["No additional source-integrity issues reported."]),
                "",
                "## Saved checks",
                "",
            ]
        )
        for c in r["checks"]:
            lines.extend(
                [
                    f"### {c['title']} — {c['status']}",
                    "",
                    c["summary"],
                    "",
                    readable(c.get("output"))
                    if c["status"] == "COMPLETE"
                    else c.get("error") or c["status"],
                    "",
                    readable(c.get("limitations")) if c.get("limitations") else "",
                    "",
                ]
            )
        if r.get("extra_results_truncated"):
            lines.append(
                "Only the newest 100 additional specialist checks are included; older receipts remain in workflow history."
            )
        return "\n".join(lines)

    @core.app.get("/api/results")
    def index(
        q: str = Query("", max_length=200),
        offset: int = Query(0, ge=0),
        limit: int = Query(12, ge=1, le=100),
    ):
        count = core.rows("SELECT count(*) n FROM evidence WHERE path IS NOT NULL")[0][
            "n"
        ]
        notes = core.rows("SELECT count(*) n FROM evidence WHERE path IS NULL")[0]["n"]
        pattern = (
            "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        )
        filtered = core.rows(
            "SELECT count(*) n FROM evidence WHERE path IS NOT NULL AND (title LIKE ? ESCAPE '\\' OR text LIKE ? ESCAPE '\\')",
            (pattern, pattern),
        )[0]["n"]
        items = [
            report(r["id"], False)
            for r in core.rows(
                "SELECT id FROM evidence WHERE path IS NOT NULL AND (title LIKE ? ESCAPE '\\' OR text LIKE ? ESCAPE '\\') ORDER BY created DESC,id LIMIT ? OFFSET ?",
                (pattern, pattern, limit, offset),
            )
        ]
        failures = core.rows(
            "SELECT id,objective,status,error,evidence_id FROM jobs WHERE status IN ('ACQUISITION FAILED','PROCESSING FAILED') ORDER BY created DESC LIMIT 20"
        )
        pending = core.rows(
            "SELECT count(*) n FROM jobs WHERE status IN ('QUEUED','FETCHING','PRESERVING','EXTRACTING')"
        )[0]["n"]
        heartbeat = core.rows(
            "SELECT updated FROM worker_heartbeats WHERE name='autopilot'"
        )
        settings = core.autopilot["settings"]()
        return {
            "items": items,
            "total": filtered,
            "offset": offset,
            "next_offset": offset + limit if offset + limit < filtered else None,
            "summary": {
                "originals": count,
                "notes_without_originals": notes,
                "pending_acquisitions": pending,
                "saved_checks": core.rows(
                    "SELECT count(*) n FROM automation_receipts WHERE status='COMPLETE'"
                )[0]["n"],
            },
            "automation": {
                "enabled": settings.get("enabled", False),
                "model_notes": settings.get("model_notes", False),
                "worker_alive": bool(
                    heartbeat and time.time() - heartbeat[0]["updated"] < 90
                ),
            },
            "acquisition_failures": failures,
            "scope": "Only preserved originals appear as analysable sources. Notes and missing historical originals are not completed research. Each listed source and saved output is rechecked before display.",
        }

    @core.app.get("/api/results/tools")
    def capabilities(evidence_id: str = Query("", max_length=100)):
        current = report(evidence_id, False) if evidence_id else None
        coverage = {v["tool"]: v for v in current["coverage"]} if current else {}
        states = {c["tool"]: c["status"] for c in current["checks"]} if current else {}
        return {
            "tools": [
                {
                    **t,
                    "automatic": coverage.get(t["id"]),
                    "saved_status": states.get(t["id"]),
                }
                for t in tools.values()
            ],
            "workspaces": [{"id": k, "label": v} for k, v in WORKSPACES],
            "source": current["source"] if current else None,
            "source_state": current["state"] if current else None,
        }

    @core.app.get("/api/results/report")
    def case_report():
        sources = core.rows(
            "SELECT id FROM evidence WHERE path IS NOT NULL ORDER BY created,id LIMIT 101"
        )
        content = "# Case analysis report\n\nSource readings, saved checks and explicit gaps. No source claim is automatically endorsed.\n\n"
        notes = core.rows("SELECT count(*) n FROM evidence WHERE path IS NULL")[0]["n"]
        content += f"## Case gaps\n\n{notes} notes or proposed claims have no acquired original.\n\n"
        for job in core.rows(
            "SELECT objective,status,error FROM jobs WHERE status IN ('ACQUISITION FAILED','PROCESSING FAILED') ORDER BY created DESC LIMIT 100"
        ):
            content += f"- {job['objective']}: {job['status']} — {job['error'] or 'No usable original produced'}\n"
        content += "\n"
        briefing = getattr(core, "case_briefing", {}).get("briefing")
        if briefing:
            brief = briefing()
            content += "## Saved case findings\n\n"
            for finding in brief["findings"]:
                content += f"### {finding['kind']}: {finding['statement']}\n\n{finding.get('limits') or ''}\n\n"
                for citation in finding["sources"]:
                    content += f"> {citation['quote']}\n\nSource: {citation['title']} ({citation['evidence_id']})\n\n"
            if not brief["findings"]:
                content += "No source-verified case findings are currently saved.\n\n"
            content += "## Open case questions\n\n"
            for question in brief["open_questions"]:
                content += f"- {question['statement']} — {question['reason']}\n"
            content += "\n"

        def sections():
            yield content
            for source in sources[:100]:
                yield markdown(report(source["id"])) + "\n\n---\n\n"
            if not sources:
                yield "No originals have been acquired. Import a file or queue an authorised public source to begin.\n"
            if len(sources) > 100:
                yield "\nExport limited to the first 100 originals. Download individual source reports for the remainder.\n"

        return StreamingResponse(
            sections(),
            media_type="text/markdown",
            headers={
                "Content-Disposition": 'attachment; filename="sherlock-case-results.md"'
            },
        )

    @core.app.get("/api/results/runs")
    def run_history(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
        return {
            "items": core.rows(
                "SELECT id,status,created,updated,json_extract(data,'$.plan.name') name FROM automation_runs ORDER BY created DESC,id LIMIT ? OFFSET ?",
                (limit, offset),
            ),
            "total": core.rows("SELECT count(*) n FROM automation_runs")[0]["n"],
            "offset": offset,
        }

    @core.app.get("/api/results/runs/{run_id}")
    def read_run(run_id: str):
        # Keep immutable raw audit records in the workflow API. This reading view
        # withholds outputs whose current sources or saved digest fail verification.
        run = core.automation["get_run"](run_id)
        checked = {}
        withheld = False
        for receipt in run["receipts"]:
            if receipt["status"] == "COMPLETE" and not bound(
                receipt["data"], checked, False
            ):
                receipt["status"] = "WITHHELD"
                receipt["data"]["result"] = None
                receipt["data"]["error"] = (
                    "Saved source or output integrity no longer verifies"
                )
                withheld = True
        if withheld:
            run["status"] = "PARTIAL"
        return run

    @core.app.get("/api/results/{evidence_id}/report")
    def export_report(evidence_id: str, format: str = "markdown"):
        if format not in {"markdown", "json"}:
            raise HTTPException(422, "Choose markdown or json")
        r = report(evidence_id)
        content = (
            json.dumps(r, indent=2, ensure_ascii=False)
            if format == "json"
            else markdown(r)
        )
        # Never put an uploaded title or unvalidated identifier in an HTTP header.
        name = hashlib.sha256(evidence_id.encode()).hexdigest()[:12]
        return Response(
            content,
            media_type="application/json" if format == "json" else "text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="source-results-{name}.{"json" if format == "json" else "md"}"'
            },
        )

    @core.app.get("/api/results/{evidence_id}")
    def source_report(evidence_id: str):
        return report(evidence_id)

    return {"report": report, "index": index}
