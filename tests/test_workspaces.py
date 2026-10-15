"""Integration checks for evidence review, graph layers and recurring acquisition."""

import xml.etree.ElementTree as ET
import os

import pytest
from fastapi.testclient import TestClient

from backend.scheduler import archive_captures, nasa_downloads


@pytest.fixture(scope="module")
def case(tmp_path_factory):
    os.environ["SHERLOCK_DATA"] = str(tmp_path_factory.mktemp("workspaces"))
    from backend import app as core

    client = TestClient(core.app)
    r = client.post(
        "/api/upload",
        files={
            "file": (
                "review-record.txt",
                b"The public institution published its research report in 2016. The review remains unresolved.",
                "text/plain",
            )
        },
    )
    assert r.status_code == 200, r.text
    source = r.json()
    board = client.post(
        "/api/boards", json={"name": "Review integration fixture"}
    ).json()
    nodes = [
        {
            "id": x,
            "type": "evidence",
            "position": {"x": i * 300, "y": 0},
            "data": {"evidenceId": source["id"]},
        }
        for i, x in enumerate("abc")
    ]
    assert (
        client.put(
            f"/api/boards/{board['id']}",
            json={
                "nodes": nodes,
                "edges": [
                    {
                        "id": "lead",
                        "source": "b",
                        "target": "c",
                        "label": "Hypothesised",
                        "data": {"state": "HYPOTHESIS"},
                    }
                ],
            },
        ).status_code
        == 200
    )
    return core, client, source, board["id"]


def proposal(source, bid, **extra):
    return {
        "board_id": bid,
        "source": "a",
        "target": "b",
        "relationship": "References",
        "claim": "The source records a public research publication.",
        "supporting": [
            {
                "id": source["id"],
                "quote": "The public institution published its research report in 2016.",
            }
        ],
        **extra,
    }


def test_review_rechecks_quotes_and_records_human_decision(case):
    core, client, source, bid = case
    bad = proposal(
        source,
        bid,
        supporting=[
            {"id": source["id"], "quote": "An invented quotation absent from this file"}
        ],
    )
    assert client.post("/api/claims", json=bad).status_code == 422
    claim = client.post("/api/claims", json=proposal(source, bid)).json()
    assert claim["status"] == "REVIEW REQUIRED"
    r = client.post(
        f"/api/claims/{claim['id']}/review",
        json={
            "decision": "ACCEPT",
            "reason": "The acquired original contains the exact source passage.",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["review"]["reviewer"] == "Local human investigator"
    edge = next(
        e
        for e in client.get(f"/api/boards/{bid}").json()["edges"]
        if e["id"] == claim["id"]
    )
    assert edge["data"]["state"] == "DOCUMENTED"
    assert edge["data"]["evidence"][0]["sha256"] == source["sha256"]


def test_graph_path_distinguishes_hypotheses_from_verified_edges(case):
    _, client, _, bid = case
    factual = client.get(
        f"/api/graph/{bid}?documented_only=true&source=a&target=c"
    ).json()
    assert factual["path"] == []
    assert len(factual["edges"]) == 1
    assert len(factual["components"]) == 2
    leads = client.get(f"/api/graph/{bid}?source=a&target=c").json()
    assert leads["path"] == ["a", "b", "c"]
    assert len(leads["path_edges"]) == 2
    assert client.get(f"/api/graph/{bid}?source=missing").status_code == 404


def test_contradiction_blocks_acceptance_and_remains_visible(case):
    _, client, source, bid = case
    value = proposal(
        source,
        bid,
        contradicting=[{"id": source["id"], "quote": "The review remains unresolved."}],
    )
    claim = client.post("/api/claims", json=value).json()
    endpoint = f"/api/claims/{claim['id']}/review"
    assert (
        client.post(
            endpoint,
            json={
                "decision": "ACCEPT",
                "reason": "Attempting to ignore an unresolved contradiction.",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            endpoint,
            json={
                "decision": "DISPUTE",
                "reason": "The source also records an unresolved review.",
            },
        ).status_code
        == 200
    )
    edge = next(
        e
        for e in client.get(f"/api/boards/{bid}").json()["edges"]
        if e["id"] == claim["id"]
    )
    assert edge["data"]["contradicting"]
    assert edge["data"]["state"] == "CONTRADICTED"
    assert (
        client.post(
            endpoint,
            json={
                "decision": "REJECT",
                "reason": "This proposed relationship is insufficiently established.",
            },
        ).status_code
        == 200
    )
    assert not any(
        e["id"] == claim["id"] for e in client.get(f"/api/boards/{bid}").json()["edges"]
    )


def test_review_refuses_modified_original(case):
    core, client, source, bid = case
    claim = client.post("/api/claims", json=proposal(source, bid)).json()
    original = core.ROOT / "originals" / source["sha256"]
    preserved = original.read_bytes()
    try:
        original.chmod(0o600)
        original.write_bytes(b"tampered")
        assert (
            client.post(
                f"/api/claims/{claim['id']}/review",
                json={
                    "decision": "ACCEPT",
                    "reason": "The original was modified after proposal.",
                },
            ).status_code
            == 422
        )
        graph = client.get(f"/api/graph/{bid}?documented_only=true").json()
        assert not graph["edges"]
    finally:
        original.write_bytes(preserved)
        original.chmod(0o400)


def test_dates_preserve_type_and_uncertainty_and_reject_wrong_year(case):
    _, client, source, _ = case
    data = {
        "title": "Source-linked research publication",
        "start": "2016-01-01",
        "end": "2016-12-31",
        "date_type": "Publication",
        "evidence_id": source["id"],
        "quote": "The public institution published its research report in 2016.",
    }
    r = client.post("/api/chronology", json=data)
    assert r.status_code == 200, r.text
    assert r.json()["start"] != r.json()["end"]
    assert r.json()["date_type"] == "Publication"
    assert (
        client.post(
            "/api/chronology", json={**data, "start": "2020-01-01", "end": "2020-12-31"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/chronology", json={**data, "end": "2015-01-01"}).status_code
        == 422
    )
    events = client.get("/api/chronology").json()
    assert any(
        e["date_type"] == "Retrieval" and e["evidence_id"] == source["id"]
        for e in events
    )


def test_map_only_accepts_public_categories_and_exact_source(case):
    _, client, source, _ = case
    place = {
        "title": "Public institution",
        "longitude": -118.125,
        "latitude": 34.137,
        "category": "Public institution",
        "evidence_id": source["id"],
        "quote": "The public institution published its research report in 2016.",
    }
    r = client.post("/api/places", json=place)
    assert r.status_code == 200
    assert "not independently authenticated" in r.json()["coordinate_method"]
    assert (
        client.post(
            "/api/places", json={**place, "category": "Private home"}
        ).status_code
        == 422
    )
    assert client.post("/api/places", json={**place, "latitude": 95}).status_code == 422


def test_graph_exports_preserve_citations_and_states(case):
    _, client, _, bid = case
    for fmt in ("graphml", "gexf"):
        r = client.get(f"/api/graph/{bid}/export/{fmt}")
        assert r.status_code == 200
        ET.fromstring(r.content)
        assert b"DOCUMENTED" in r.content and b"HYPOTHESIS" in r.content
        assert b"public institution published" in r.content


def test_version_comparison_persists_actual_hashes_and_limits_interpretation(case):
    _, client, source, _ = case
    other = client.post(
        "/api/upload",
        files={
            "file": (
                "revised-record.txt",
                b"The public institution published its research report in 2016. The review was completed in 2020.",
                "text/plain",
            )
        },
    ).json()
    r = client.post(
        "/api/comparisons", json={"left_id": source["id"], "right_id": other["id"]}
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["original_hashes"] == [source["sha256"], other["sha256"]]
    assert result["changed"] and any(line.startswith("+") for line in result["diff"])
    assert "do not establish changes to a game binary" in result["interpretation"]
    assert any(x["id"] == result["id"] for x in client.get("/api/comparisons").json())
    assert (
        client.post(
            "/api/comparisons", json={"left_id": source["id"], "right_id": source["id"]}
        ).status_code
        == 422
    )


def test_discovery_selects_actual_originals_and_valid_captures():
    data = {
        "results": [
            {
                "distribution": "PUBLIC",
                "title": "Public technical paper",
                "downloads": [
                    {
                        "mimetype": "application/pdf",
                        "links": {"pdf": "/api/citations/123/downloads/123.pdf"},
                    }
                ],
            },
            {
                "distribution": "RESTRICTED",
                "downloads": [
                    {
                        "mimetype": "application/pdf",
                        "links": {"pdf": "/api/citations/999/downloads/999.pdf"},
                    }
                ],
            },
            {"distribution": "PUBLIC", "title": "Catalogue only", "downloads": []},
        ]
    }
    assert nasa_downloads(data) == [
        (
            "https://ntrs.nasa.gov/api/citations/123/downloads/123.pdf",
            "Public technical paper",
        )
    ]
    captures = [
        ["timestamp", "original", "statuscode"],
        ["20190404194645", "https://example.com/", "200"],
        ["invalid", "https://example.com/", "200"],
        ["20200101000000", "https://example.com/", "403"],
    ]
    found = archive_captures(captures)
    assert len(found) == 1 and "/20190404194645id_/" in found[0][0]


def test_scheduler_audits_completed_job_and_still_runs_due_watch(case):
    core, client, source, _ = case
    enabled = core.rows("SELECT id,enabled,next_run FROM watches")
    core.execute("UPDATE watches SET enabled=0")
    try:
        watch = client.post(
            "/api/watches",
            json={
                "name": "Scheduler regression fixture",
                "mode": "url",
                "target": "https://example.com/",
                "interval_minutes": 60,
            },
        ).json()["id"]
        jid = core.uid("TASK")
        core.execute(
            "INSERT INTO jobs(id,objective,url,status,progress,attempts,evidence_id,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                jid,
                "Completed acquisition",
                "https://example.com/previous",
                "COMPLETE",
                100,
                1,
                source["id"],
                core.now(),
                core.now(),
            ),
        )
        core.execute(
            "INSERT INTO discovery VALUES(?,?,?,?,?)",
            (watch, "https://example.com/previous", "Prior source", core.now(), jid),
        )
        core.scheduler["tick"]()
        audit = core.rows("SELECT * FROM watch_analyses WHERE job_id=?", (jid,))[0]
        assert audit["run_id"] and audit["status"] == "QUEUED"
        assert (
            core.rows("SELECT * FROM watch_runs WHERE watch_id=?", (watch,))[0][
                "status"
            ]
            == "COMPLETE"
        )
        core.scheduler["tick"]()
        assert (
            len(core.rows("SELECT * FROM watch_analyses WHERE job_id=?", (jid,))) == 1
        )
    finally:
        core.execute(
            "UPDATE watches SET enabled=0 WHERE name='Scheduler regression fixture'"
        )
        for w in enabled:
            core.execute(
                "UPDATE watches SET enabled=?,next_run=? WHERE id=?",
                (w["enabled"], w["next_run"], w["id"]),
            )


def test_cron_utc_schedule_and_rate_floor():
    from datetime import datetime, timezone
    from backend.scheduler import next_scheduled, validate_schedule

    base = datetime(2026, 10, 13, 23, 55, tzinfo=timezone.utc).timestamp()
    validate_schedule("0 */6 * * *")
    assert (
        next_scheduled("0 */6 * * *", base, 60)
        == datetime(2026, 10, 14, tzinfo=timezone.utc).timestamp()
    )
    assert next_scheduled("", base, 60) == base + 3600
    for expression in ("* * * * *", "not a schedule", "0 0 30 2 *", "0 0 * * * *"):
        with pytest.raises(ValueError):
            validate_schedule(expression)


def test_cron_persists_in_watch_api(case):
    _, client, _, _ = case
    value = {
        "name": "UTC cron fixture",
        "mode": "nasa",
        "target": "superalloy",
        "cron_expression": "0 */6 * * *",
    }
    r = client.post("/api/watches", json=value)
    assert r.status_code == 200
    watch = next(
        w
        for w in client.get("/api/watches").json()["watches"]
        if w["id"] == r.json()["id"]
    )
    assert watch["cron_expression"] == value["cron_expression"]
    assert (
        client.post(
            "/api/watches", json={**value, "cron_expression": "* * * * *"}
        ).status_code
        == 422
    )
    client.post(f"/api/watches/{watch['id']}/pause")
