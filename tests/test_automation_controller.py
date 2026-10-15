"""Real SQLite workflow state transitions and subprocess tools, independent of external services."""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.automation import install


@pytest.fixture()
def engine(tmp_path):
    """Use a real isolated SQLite database, actual routes and real analytical subprocesses."""
    file = tmp_path / "workflow.sqlite3"

    @contextmanager
    def db():
        connection = sqlite3.connect(file, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def execute(sql, args=()):
        with db() as c:
            c.execute(sql, args)

    def rows(sql, args=()):
        with db() as c:
            return [dict(r) for r in c.execute(sql, args)]

    core = SimpleNamespace(
        app=FastAPI(),
        db=db,
        execute=execute,
        rows=rows,
        ROOT=tmp_path,
        now=lambda: datetime.now(timezone.utc).isoformat(),
        uid=lambda p: p + "-" + uuid4().hex[:12],
        log=lambda *args: None,
        stopping=threading.Event(),
        heartbeat=lambda *args: None,
    )
    controller = install(core)
    return core, controller, TestClient(core.app)


def plan(steps):
    """Label fixture inputs as owned synthetic analytical data."""
    return {
        "name": "Synthetic acceptance workflow",
        "objective": "Exercise actual dependency execution on owned synthetic data",
        "authorisation": "Owned test data; no case allegations",
        "steps": steps,
    }


def test_real_subprocess_receipts_and_output_binding_persist_on_reinstall(engine):
    """Execute two actions, then recover the completed receipts from a new controller instance."""
    core, ctl, client = engine
    w = client.post(
        "/api/automation/workflows",
        json=plan(
            [
                {"id": "read", "tool": "cipher.hex", "inputs": {"text": "48454c4c4f"}},
                {
                    "id": "terms",
                    "tool": "text.word_frequency",
                    "depends_on": ["read"],
                    "inputs": {"text": {"$ref": "read.output.transformed"}},
                },
            ]
        ),
    )
    assert w.status_code == 200, w.text
    queued = client.post(
        "/api/automation/workflows/" + w.json()["id"] + "/run", json={}
    ).json()
    rid = queued["id"]
    first = ctl["advance"](rid)
    assert first["status"] == "RUNNING" and first["data"]["remaining_steps"] == 1
    last = ctl["advance"](rid)
    assert last["status"] == "COMPLETE" and last["data"]["remaining_steps"] == 0
    assert last["receipts"][1]["data"]["result"]["output"]["result"] == [["hello", 1]]
    assert all(r["data"]["output_sha256"] for r in last["receipts"])
    again = install(SimpleNamespace(**{**core.__dict__, "app": FastAPI()}))["get_run"](
        rid
    )
    assert again == last
    assert ctl["advance"](rid) == last  # Completed work is not repeated.


def test_failure_retry_history_stop_and_dependency_skip(engine):
    """Failed actions retain every attempt; dependent steps skip, independent steps continue."""
    core, ctl, client = engine
    w = client.post(
        "/api/automation/workflows",
        json=plan(
            [
                {
                    "id": "invalid",
                    "tool": "cipher.hex",
                    "inputs": {"text": "not hex"},
                    "attempts": 2,
                    "on_failure": "continue",
                },
                {
                    "id": "dependent",
                    "tool": "text.word_frequency",
                    "depends_on": ["invalid"],
                    "inputs": {"text": "not to be analysed"},
                },
                {"id": "independent", "tool": "cipher.hex", "inputs": {"text": "4849"}},
            ]
        ),
    ).json()
    r = ctl["launch"](w["id"])
    rid = r["id"]
    r = ctl["advance"](rid)
    assert (
        next(item for item in r["receipts"] if item["step_id"] == "invalid")["status"]
        == "RETRY"
    )
    receipt = next(item for item in r["receipts"] if item["step_id"] == "invalid")
    data = receipt["data"]
    data["next_attempt"] = 0
    core.execute(
        "UPDATE automation_receipts SET data=? WHERE id=?",
        (json.dumps(data), receipt["id"]),
    )
    for _ in range(3):
        r = ctl["advance"](rid)
    assert r["status"] == "PARTIAL" and r["data"]["failure_count"] == 2
    assert {x["step_id"]: x["status"] for x in r["receipts"]} == {
        "invalid": "FAILED",
        "dependent": "SKIPPED",
        "independent": "COMPLETE",
    }
    assert (
        len(
            next(item for item in r["receipts"] if item["step_id"] == "invalid")[
                "data"
            ]["attempt_history"]
        )
        == 2
    )
    assert all(
        a["error"]
        for a in next(item for item in r["receipts"] if item["step_id"] == "invalid")[
            "data"
        ]["attempt_history"]
    )


def test_pause_resume_cancel_and_illegal_controls(engine):
    """Paused/cancelled jobs perform no new steps; terminal outcomes cannot resume."""
    _, ctl, c = engine
    w = c.post(
        "/api/automation/workflows",
        json=plan([{"id": "one", "tool": "cipher.hex", "inputs": {"text": "4849"}}]),
    ).json()
    rid = ctl["launch"](w["id"])["id"]
    assert (
        c.post(f"/api/automation/runs/{rid}/pause", json={}).json()["status"]
        == "PAUSED"
    )
    assert not ctl["advance"](rid)["receipts"]
    assert (
        c.post(f"/api/automation/runs/{rid}/resume", json={}).json()["status"]
        == "QUEUED"
    )
    assert c.post(f"/api/automation/runs/{rid}/resume", json={}).status_code == 409
    assert (
        c.post(f"/api/automation/runs/{rid}/cancel", json={}).json()["status"]
        == "CANCELLED"
    )
    assert not ctl["advance"](rid)["receipts"]
    assert c.post(f"/api/automation/runs/{rid}/resume", json={}).status_code == 409
    assert c.post("/api/automation/runs/not-real/pause", json={}).status_code == 404


def test_interval_schedule_dedup_pause_and_source_binding_validation(engine):
    """A persisted schedule runs once per due slot and refuses a missing source binding."""
    core, ctl, c = engine
    w = c.post(
        "/api/automation/workflows",
        json=plan([{"id": "one", "tool": "cipher.hex", "inputs": {"text": "4849"}}]),
    ).json()
    s = c.post(
        "/api/automation/schedules",
        json={"workflow_id": w["id"], "interval_minutes": 5},
    ).json()
    ctl["tick"](10**10)
    ctl["tick"](10**10)
    assert len(core.rows("SELECT * FROM automation_runs")) == 1
    assert (
        c.post("/api/automation/schedules/" + s["id"] + "/pause", json={}).json()[
            "enabled"
        ]
        is False
    )
    ctl["tick"](10**10 + 1000)
    assert len(core.rows("SELECT * FROM automation_runs")) == 1
    invalid = c.post(
        "/api/automation/schedules", json={"workflow_id": w["id"], "cron": "not a cron"}
    )
    assert invalid.status_code == 422
    binding = c.post(
        "/api/automation/workflows",
        json=plan(
            [
                {
                    "id": "verify",
                    "tool": "evidence.verify",
                    "inputs": {"evidence_id": {"$binding": "evidence_id"}},
                }
            ]
        ),
    ).json()
    assert (
        c.post(
            "/api/automation/schedules", json={"workflow_id": binding["id"]}
        ).status_code
        == 422
    )


def test_api_refuses_host_commands_oversize_and_invalid_plans(engine):
    """No registered tool can be replaced by a caller-specified host command."""
    _, _, c = engine
    assert (
        c.post(
            "/api/automation/run",
            json={
                "tool": "shell.exec",
                "inputs": {"cmd": "id"},
                "authorisation": "Owned test",
            },
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/automation/workflows",
            json=plan(
                [{"id": "a", "tool": "text.word_frequency", "depends_on": ["a"]}]
            ),
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/automation/run",
            json={
                "tool": "cipher.hex",
                "inputs": {"text": "a" * 260000},
                "authorisation": "Owned test",
            },
        ).status_code
        == 422
    )
    assert c.get("/api/automation/catalogue").json()["count"] >= 200
