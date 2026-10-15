"""Durable source-board analysis monitors; rerun only when the cited graph changes."""

import hashlib
import json
from typing import Any
import threading
import time
from fastapi import HTTPException
from pydantic import BaseModel, Field
from .analytical_methods import GRAPH_METHODS
from .scheduler import validate_schedule, next_scheduled


def install(core: Any) -> dict[str, Any]:
    """Register persistent analysis or audit endpoints and workers."""
    core.execute(
        "CREATE TABLE IF NOT EXISTS analysis_monitors(id TEXT PRIMARY KEY,board_id TEXT,method TEXT,enabled INTEGER,next_due REAL,data TEXT,UNIQUE(board_id,method))"
    )

    class Schedule(BaseModel):
        interval_minutes: int = Field(default=15, ge=5, le=10080)
        cron: str = Field(default="", max_length=100)

    def list_monitors() -> list[dict[str, Any]]:
        """Read durable monitor schedules and their last outcomes."""
        return [
            {**r, "data": json.loads(r["data"])}
            for r in core.rows("SELECT * FROM analysis_monitors ORDER BY rowid DESC")
        ]

    def fingerprint(board_id: str) -> str:
        """Hash cited topology and citations while ignoring board positions."""
        g = core.workspaces["graph"](board_id, documented_only=True)
        value = {
            "nodes": sorted((n["id"], n["evidence_id"]) for n in g["nodes"]),
            "edges": sorted(
                (e["source"], e["target"], json.dumps(e["data"], sort_keys=True))
                for e in g["edges"]
            ),
        }
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    monitor_lock = threading.Lock()

    def tick(timestamp: float | None = None, only: str | None = None) -> None:
        """Serialise manual and background monitor checks."""
        with monitor_lock:
            return advance(timestamp, only)

    def advance(timestamp: float | None = None, only: str | None = None) -> None:
        """Recompute changed source graphs and preserve failures and next due dates."""
        stamp = time.time() if timestamp is None else timestamp
        for monitor in list_monitors():
            if only and monitor["id"] != only:
                continue
            if not monitor["enabled"] or (not only and monitor["next_due"] > stamp):
                continue
            data = monitor["data"]
            try:
                current = fingerprint(monitor["board_id"])
                if current != data.get("fingerprint"):
                    result = core.tradecraft["run"](
                        {
                            "method": monitor["method"],
                            "inputs": data["inputs"],
                            "citations": [],
                            "notes": "Automatically recomputed after source-verified board graph changed.",
                            "authorisation": data["authorisation"],
                        }
                    )
                    data.update(
                        {
                            "fingerprint": current,
                            "last_record_id": result["id"],
                            "status": "UPDATED",
                            "error": None,
                        }
                    )
                    core.log(
                        "graph_monitor_updated",
                        {
                            "id": monitor["id"],
                            "record": result["id"],
                            "fingerprint": current,
                        },
                    )
                else:
                    data.update({"status": "UNCHANGED", "error": None})
            except Exception as ex:
                data.update(
                    {
                        "status": "FAILED",
                        "error": str(
                            ex.detail if isinstance(ex, HTTPException) else ex
                        )[:1000],
                    }
                )
                core.log(
                    "graph_monitor_failed",
                    {"id": monitor["id"], "reason": data["error"]},
                )
            data["checked_utc"] = core.now()
            due = next_scheduled(data.get("cron", ""), stamp, data["interval_minutes"])
            core.execute(
                "UPDATE analysis_monitors SET next_due=?,data=? WHERE id=?",
                (due, json.dumps(data), monitor["id"]),
            )

    @core.app.get("/api/analysis-monitors")
    def listing() -> list[dict[str, Any]]:
        """List persisted graph-analysis monitors."""
        return list_monitors()

    @core.app.post("/api/tradecraft/records/{rid}/monitor")
    def create(rid: str, value: Schedule) -> dict[str, Any]:
        """Schedule an existing source-bound graph analysis."""
        try:
            validate_schedule(value.cron)
        except ValueError as ex:
            raise HTTPException(422, str(ex))
        records = core.rows("SELECT * FROM analytic_records WHERE id=?", (rid,))
        if not records:
            raise HTTPException(404, "Analysis not found")
        record = records[0]
        data = json.loads(record["data"])
        board_id = data["inputs"].get("board_id")
        method = next(
            (m for m in core.tradecraft["registry"]() if m["id"] == record["method"]),
            {},
        )
        if not board_id or method.get("engine") not in GRAPH_METHODS:
            raise HTTPException(
                422, "Only source-board graph analyses can be monitored"
            )
        existing = core.rows(
            "SELECT id FROM analysis_monitors WHERE board_id=? AND method=?",
            (board_id, record["method"]),
        )
        if not existing and len(list_monitors()) >= 100:
            raise HTTPException(422, "Monitor limit reached")
        mid = existing[0]["id"] if existing else core.uid("MONITOR")
        config = {
            **value.model_dump(),
            "inputs": {
                k: v
                for k, v in data["inputs"].items()
                if k not in ("nodes", "edges", "layer")
            },
            "authorisation": data["authorisation"],
            "status": "SCHEDULED",
            "fingerprint": None,
            "last_record_id": rid,
            "error": None,
        }
        core.execute(
            "INSERT INTO analysis_monitors VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET enabled=1,next_due=excluded.next_due,data=excluded.data",
            (mid, board_id, record["method"], 1, time.time(), json.dumps(config)),
        )
        core.log(
            "graph_monitor_scheduled",
            {
                "id": mid,
                "board": board_id,
                "method": record["method"],
                "cron": value.cron,
                "interval_minutes": value.interval_minutes,
            },
        )
        return next(m for m in list_monitors() if m["id"] == mid)

    @core.app.patch("/api/analysis-monitors/{mid}")
    def control(mid: str, value: dict) -> dict[str, Any]:
        """Pause or resume a persisted monitor."""
        if not isinstance(value.get("enabled"), bool):
            raise HTTPException(422, "enabled must be boolean")
        if not core.rows("SELECT 1 FROM analysis_monitors WHERE id=?", (mid,)):
            raise HTTPException(404, "Monitor not found")
        core.execute(
            "UPDATE analysis_monitors SET enabled=?,next_due=? WHERE id=?",
            (int(value["enabled"]), time.time(), mid),
        )
        core.log("graph_monitor_control", {"id": mid, "enabled": value["enabled"]})
        return {"id": mid, "enabled": value["enabled"]}

    @core.app.post("/api/analysis-monitors/{mid}/run")
    def run_now(mid: str) -> dict[str, Any]:
        """Run a selected enabled monitor immediately."""
        if not core.rows("SELECT 1 FROM analysis_monitors WHERE id=?", (mid,)):
            raise HTTPException(404, "Monitor not found")
        tick(only=mid)
        return next(m for m in list_monitors() if m["id"] == mid)

    def loop() -> None:
        """Maintain the worker heartbeat and check due analysis monitors."""
        while not core.stopping.is_set():
            try:
                core.heartbeat("graph-analysis-monitor")
                tick()
            except Exception as ex:
                core.log("graph_monitor_worker_failed", {"reason": str(ex)[:500]})
            core.stopping.wait(30)

    @core.app.on_event("startup")
    def start() -> None:
        """Start the bounded background monitoring thread."""
        threading.Thread(
            target=loop, name="graph-analysis-monitor", daemon=True
        ).start()

    return {"tick": tick, "fingerprint": fingerprint}
