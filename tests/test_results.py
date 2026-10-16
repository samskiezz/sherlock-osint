"""Actual durable tools -> source reading -> export, without external providers."""

# ruff: noqa: F811
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.autopilot import Scan, Settings, install as install_autopilot
from backend.automation import Workflow
from backend.forensics import install as install_forensics
from backend.results import install as install_results
from test_automation_controller import engine  # noqa: F401


@pytest.fixture
def case(engine):
    core, controller, _ = engine
    core.lock = threading.RLock()
    core.automation = controller
    core.execute(
        "CREATE TABLE evidence(id TEXT PRIMARY KEY,title TEXT,kind TEXT,status TEXT,url TEXT,sha256 TEXT,path TEXT,mime TEXT,size INTEGER,created TEXT,metadata TEXT,text TEXT,preview TEXT)"
    )
    core.execute(
        "CREATE TABLE jobs(id TEXT,objective TEXT,status TEXT,error TEXT,evidence_id TEXT,created TEXT)"
    )
    core.execute(
        "CREATE TABLE worker_heartbeats(name TEXT PRIMARY KEY,updated REAL,data TEXT)"
    )
    (core.ROOT / "originals").mkdir()
    text = "Owned synthetic research memo. Example Project began on 2026-10-16. Contact analyst@example.org. The reported identifier is US1234567B2. No allegation is established by this fixture."
    sha = hashlib.sha256(text.encode()).hexdigest()
    path = core.ROOT / "originals" / sha
    path.write_text(text)
    der = core.ROOT / "derivatives" / "SOURCE1"
    der.mkdir(parents=True)
    (der / "text.txt").write_text(text)
    metadata = {
        "processing_status": "COMPLETE",
        "sandbox": True,
        "derivative_hashes": {"text.txt": sha},
    }
    core.execute(
        "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "SOURCE1",
            "Owned synthetic research memo",
            "document",
            "ORIGINAL VERIFIED",
            "",
            sha,
            str(path),
            "text/plain",
            len(text),
            "2026-10-01",
            json.dumps(metadata),
            text,
            None,
        ),
    )
    core.forensics = install_forensics(core)
    core.autopilot = install_autopilot(core)
    projection = install_results(core)
    return core, controller, TestClient(core.app), projection, sha


def completed(case):
    core, ctl, _, _, sha = case
    plan = Workflow(
        name="Owned automatic source reading",
        objective="Read a preserved test source with actual registered tools",
        authorisation="Owned synthetic source for acceptance",
        parallelism=1,
        steps=[
            {"id": key, "tool": tool, "inputs": {"evidence_id": "SOURCE1"}}
            for key, tool in [
                ("summary", "text.extractive_summary"),
                ("dates", "text.dates"),
                ("identifiers", "text.identifiers"),
                ("emails", "text.emails"),
            ]
        ],
    )
    run = ctl["launch"](ctl["create"](plan)["id"])
    core.execute(
        "INSERT INTO autopilot_dispatch VALUES(?,?,?,?,?)",
        (
            "SOURCE1",
            "owned-acceptance",
            core.now(),
            run["id"],
            json.dumps({"source_sha256": sha, "text_sha256": sha, "coverage": []}),
        ),
    )
    for _ in range(8):
        run = ctl["advance"](run["id"])
        if run["status"] in ("COMPLETE", "FAILED", "PARTIAL"):
            break
    assert run["status"] == "COMPLETE"
    return run


def test_actual_tools_are_readable_and_exported_without_rerunning(case):
    core, _, client, _, sha = case
    completed(case)
    before = core.rows("SELECT count(*) n FROM automation_runs")[0]["n"]
    report = client.get("/api/results/SOURCE1").json()
    assert report["state"] == "COMPLETE" and report["integrity"] == "VERIFIED"
    assert report["progress"] == {"complete": 4, "failed": 0, "skipped": 0, "total": 4}
    assert report["source"]["sha256"] == sha
    assert any("2026-10-16" in p["quote"] for p in report["reading"])
    text = core.rows("SELECT text FROM evidence WHERE id='SOURCE1'")[0]["text"]
    assert all(text[p["start"] : p["end"]] == p["quote"] for p in report["reading"])
    assert any(
        "analyst@example.org" in json.dumps(v["value"]) for v in report["information"]
    )
    assert all(c["output"] is not None for c in report["checks"])
    for _ in range(2):
        assert client.get("/api/results/SOURCE1").json() == report
    md = client.get("/api/results/SOURCE1/report")
    assert md.status_code == 200 and "attachment" in md.headers["content-disposition"]
    assert "2026-10-16" in md.text and "analyst@example.org" in md.text
    assert "Source reading" in md.text and sha in md.text
    assert client.get("/api/results/SOURCE1/report?format=json").json() == report
    assert (
        client.get("/api/results/SOURCE1/report?format=executable").status_code == 422
    )
    assert core.rows("SELECT count(*) n FROM automation_runs")[0]["n"] == before


@pytest.mark.parametrize("corruption", ["original", "derivative", "index"])
def test_tampered_sources_never_display_or_export_stale_results(case, corruption):
    core, _, client, _, sha = case
    completed(case)
    if corruption == "original":
        (core.ROOT / "originals" / sha).write_text("Changed bytes")
    elif corruption == "derivative":
        (core.ROOT / "derivatives/SOURCE1/text.txt").write_text("Changed extract")
    else:
        core.execute("UPDATE evidence SET text='Changed index' WHERE id='SOURCE1'")
    r = client.get("/api/results/SOURCE1").json()
    assert r["state"] == "BLOCKED" and r["reading"] == r["checks"] == []
    assert r["can_reprocess"] is (corruption != "original")
    exported = client.get("/api/results/SOURCE1/report").text
    assert "analyst@example.org" not in exported and "BLOCKED" in exported
    assert client.get("/api/results").json()["items"][0]["state"] == "BLOCKED"


def test_output_and_comparison_tampering_are_withheld(case):
    core, _, client, _, _ = case
    run = completed(case)
    row = core.rows(
        "SELECT * FROM automation_receipts WHERE run_id=? ORDER BY rowid LIMIT 1",
        (run["id"],),
    )[0]
    saved = json.loads(row["data"])
    saved["result"]["output"] = {"result": "FORGED OUTPUT"}
    core.execute(
        "UPDATE automation_receipts SET data=? WHERE id=?",
        (json.dumps(saved), row["id"]),
    )
    r = client.get("/api/results/SOURCE1").json()
    assert r["state"] == "PARTIAL" and r["progress"]["failed"] == 1
    assert next(c for c in r["checks"] if c["id"] == row["id"])["output"] is None
    assert "FORGED OUTPUT" not in client.get("/api/results/SOURCE1/report").text
    history = client.get(f"/api/results/runs/{run['id']}").json()
    assert history["status"] == "PARTIAL"
    assert history["receipts"][0]["status"] == "WITHHELD"
    assert history["receipts"][0]["data"]["result"] is None
    saved["result"]["sources"].append(
        {
            "evidence_id": "UNACQUIRED",
            "original_sha256": "missing",
            "text_sha256": "missing",
        }
    )
    saved["output_sha256"] = hashlib.sha256(
        json.dumps(saved["result"], sort_keys=True).encode()
    ).hexdigest()
    core.execute(
        "UPDATE automation_receipts SET data=? WHERE id=?",
        (json.dumps(saved), row["id"]),
    )
    assert (
        next(
            c
            for c in client.get("/api/results/SOURCE1").json()["checks"]
            if c["id"] == row["id"]
        )["status"]
        == "WITHHELD"
    )


def test_search_pagination_gaps_and_all_tool_access(case):
    core, _, client, _, _ = case
    core.execute(
        "INSERT INTO evidence SELECT 'NOTE1','Unacquired proposed claim',kind,'SECONDARY SOURCE',url,NULL,NULL,mime,0,created,'{}','Unverified',NULL FROM evidence WHERE id='SOURCE1'"
    )
    core.execute(
        "INSERT INTO jobs VALUES('FAILED1','Owned blocked source','ACQUISITION FAILED','DNS validation prevented acquisition',NULL,'2026-10-16')"
    )
    index = client.get("/api/results?q=research&limit=1").json()
    assert (
        index["summary"]["originals"] == 1
        and index["summary"]["notes_without_originals"] == 1
    )
    assert index["acquisition_failures"][0]["id"] == "FAILED1"
    assert index["total"] == 1 and index["next_offset"] is None
    assert client.get("/api/results?q=%").json()["total"] == 0
    assert client.get("/api/results?q=' OR 1=1 --").json()["total"] == 0
    assert client.get("/api/results?offset=-1").status_code == 422
    assert client.get("/api/results?limit=101").status_code == 422
    assert client.get("/api/results/unknown").status_code == 404
    assert client.get("/api/results/NOTE1").json()["state"] == "BLOCKED"
    directory = client.get("/api/results/tools?evidence_id=SOURCE1").json()
    catalogue = client.get("/api/automation/catalogue").json()
    assert {t["id"] for t in directory["tools"]} == {
        t["id"] for t in catalogue["tools"]
    }
    assert len(directory["workspaces"]) >= 20
    export = client.get("/api/results/report").text
    assert "1 notes or proposed claims" in export and "DNS validation" in export


def test_immediate_dispatch_is_idempotent_and_respects_pause(case):
    core, _, client, _, _ = case
    client.put(
        "/api/autopilot/settings", json=Settings(enabled=False).model_dump()
    ).raise_for_status()
    assert core.autopilot["on_extracted"]("SOURCE1")["status"] == "PAUSED"
    assert not core.rows("SELECT id FROM automation_runs")
    client.put(
        "/api/autopilot/settings", json=Settings().model_dump()
    ).raise_for_status()
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(
            pool.map(lambda _: core.autopilot["on_extracted"]("SOURCE1"), range(2))
        )
    assert values[0]["run_id"] == values[1]["run_id"]
    assert len(core.rows("SELECT id FROM automation_runs")) == 1
    assert len(core.rows("SELECT id FROM automation_workflows")) == 1
    assert client.get("/api/results/SOURCE1").json()["state"] == "QUEUED"
    history = client.get("/api/results/runs?limit=1").json()
    assert history["total"] == 1 and history["items"][0]["id"] == values[0]["run_id"]


def test_real_failed_tool_without_result_remains_readable(case):
    core, ctl, client, _, _ = case
    run = client.post(
        "/api/automation/run",
        json={
            "tool": "cipher.hex",
            "inputs": {"evidence_id": "SOURCE1"},
            "authorisation": "Owned negative-path test",
        },
    ).json()
    failed = ctl["advance"](run["id"])
    assert failed["status"] in {"FAILED", "PARTIAL"}
    assert failed["receipts"][0]["data"]["result"] is None
    assert failed["receipts"][0]["data"]["inputs"]["evidence_id"] == "SOURCE1"
    report = client.get("/api/results/SOURCE1").json()
    assert report["checks"][0]["status"] == "FAILED" and report["checks"][0]["error"]
    assert client.get("/api/results").status_code == 200
    assert "FAILED" in client.get("/api/results/SOURCE1/report").text


def test_recovery_scan_reaches_a_source_older_than_newest_500(case):
    core, _, _, _, _ = case
    # A source-only copy may contain newer records with omitted originals.
    # Those records must not permanently hide an older acquired original.
    with core.db() as db:
        for i in range(502):
            db.execute(
                "INSERT INTO evidence SELECT ?,?,kind,status,url,sha256,'/missing-original',mime,size,'2026-10-16',metadata,text,NULL FROM evidence WHERE id='SOURCE1'",
                (f"OMITTED-{i}", f"Omitted synthetic original {i}"),
            )
    outcome = core.autopilot["scan"](Scan(limit=1))
    assert len(outcome["dispatches"]) == 1
    assert outcome["dispatches"][0]["evidence_id"] == "SOURCE1"
    assert not core.autopilot["scan"](Scan(limit=1))["dispatches"]


def test_explicit_retry_retains_history_and_does_not_duplicate_an_active_run(case):
    core, _, client, _, _ = case
    previous = completed(case)
    response = client.post(
        "/api/autopilot/scan", json={"evidence_id": "SOURCE1", "force": True}
    )
    assert response.status_code == 200
    current = response.json()["dispatches"][0]["run_id"]
    assert current != previous["id"]
    pending = client.get("/api/results/SOURCE1").json()
    assert pending["state"] == "QUEUED"
    assert sum(c["status"] == "COMPLETE" for c in pending["checks"]) == 4
    assert not client.post(
        "/api/autopilot/scan", json={"evidence_id": "SOURCE1", "force": True}
    ).json()["dispatches"]
    assert len(core.rows("SELECT id FROM automation_runs")) == 2
    assert (
        len(
            core.rows(
                "SELECT id FROM automation_receipts WHERE run_id=?", (previous["id"],)
            )
        )
        == 4
    )
    assert client.post("/api/autopilot/scan", json={"force": True}).status_code == 422


def test_forensic_adapter_and_legacy_attestation_are_readable_without_weakening_integrity(
    case,
):
    core, ctl, client, _, sha = case
    run = client.post(
        "/api/automation/run",
        json={
            "tool": "forensics.screen",
            "inputs": {"evidence_id": "SOURCE1"},
            "authorisation": "Owned forensic receipt regression",
        },
    ).json()
    actual = ctl["advance"](run["id"])
    assert actual["status"] == "COMPLETE"
    receipt = actual["receipts"][0]
    assert receipt["data"]["result"]["sources"][0]["original_sha256"] == sha
    assert (
        client.get("/api/results/SOURCE1").json()["checks"][0]["status"] == "COMPLETE"
    )
    # Reproduce the old adapter's exact wire shape; its embedded attestation is hashed.
    legacy = receipt["data"]
    del legacy["result"]["sources"]
    legacy["output_sha256"] = hashlib.sha256(
        json.dumps(legacy["result"], sort_keys=True).encode()
    ).hexdigest()
    core.execute(
        "UPDATE automation_receipts SET data=? WHERE id=?",
        (json.dumps(legacy), receipt["id"]),
    )
    recovered = client.get("/api/results/SOURCE1").json()
    assert recovered["checks"][0]["status"] == "COMPLETE"
    assert recovered["checks"][0]["sources"][0]["original_sha256"] == sha
    (core.ROOT / "originals" / sha).write_text("Changed original")
    history = client.get(f"/api/results/runs/{run['id']}").json()
    assert history["receipts"][0]["status"] == "WITHHELD"


def test_visual_receipt_derivative_binding_detects_changed_feature_receipt(case):
    core, _, client, _, _ = case
    run = completed(case)
    derivative = core.ROOT / "derivatives/SOURCE1/result.json"
    derivative.write_text('{"owned_synthetic_feature_receipt": true}')
    row = core.rows(
        "SELECT * FROM automation_receipts WHERE run_id=? ORDER BY rowid LIMIT 1",
        (run["id"],),
    )[0]
    data = json.loads(row["data"])
    data["result"]["sources"][0]["derivative_hashes"] = {
        "result.json": hashlib.sha256(derivative.read_bytes()).hexdigest()
    }
    data["output_sha256"] = hashlib.sha256(
        json.dumps(data["result"], sort_keys=True).encode()
    ).hexdigest()
    core.execute(
        "UPDATE automation_receipts SET data=? WHERE id=?",
        (json.dumps(data), row["id"]),
    )
    assert (
        client.get(f"/api/results/runs/{run['id']}").json()["receipts"][0]["status"]
        == "COMPLETE"
    )
    derivative.write_text("Changed feature receipt")
    assert (
        client.get(f"/api/results/runs/{run['id']}").json()["receipts"][0]["status"]
        == "WITHHELD"
    )


def test_graph_bound_history_revalidates_the_documented_graph(case):
    core, _, client, _, _ = case
    previous = completed(case)
    graph = {
        "nodes": [{"id": "A"}, {"id": "B"}],
        "edges": [{"source": "A", "target": "B"}],
    }
    core.workspaces = {"graph": lambda board, documented_only: graph}
    row = core.rows(
        "SELECT * FROM automation_receipts WHERE run_id=? ORDER BY rowid LIMIT 1",
        (previous["id"],),
    )[0]
    data = json.loads(row["data"])
    data["tool"] = "graph.owned_regression"
    data["result"] = {
        "sources": [
            {
                "board_id": "OWNED",
                "graph_sha256": hashlib.sha256(
                    json.dumps(graph, sort_keys=True).encode()
                ).hexdigest(),
            }
        ],
        "output": {"node_count": 2},
    }
    data["output_sha256"] = hashlib.sha256(
        json.dumps(data["result"], sort_keys=True).encode()
    ).hexdigest()
    core.execute(
        "UPDATE automation_receipts SET data=? WHERE id=?",
        (json.dumps(data), row["id"]),
    )
    assert (
        client.get(f"/api/results/runs/{previous['id']}").json()["receipts"][0][
            "status"
        ]
        == "COMPLETE"
    )
    graph["edges"] = []
    assert (
        client.get(f"/api/results/runs/{previous['id']}").json()["receipts"][0][
            "status"
        ]
        == "WITHHELD"
    )
