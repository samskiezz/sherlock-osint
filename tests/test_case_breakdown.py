"""Case reports must expose the proof and uncertainty behind each saved connection."""

# ruff: noqa: F401, F811
import json
from fastapi.testclient import TestClient
from backend.case_breakdown import install, build_breakdown
from backend.case_briefing import build_briefing
from test_case_briefing_automatic import case, board
from test_automation_controller import engine


def setup_case(case):
    """Add the investigation fields needed by the actual saved-report reader."""
    core, client, sha, digest = case
    core.execute("ALTER TABLE investigations ADD COLUMN question TEXT")
    core.execute("ALTER TABLE investigations ADD COLUMN provider TEXT")
    install(core)
    return core, TestClient(core.app), sha, digest


def test_connection_has_exact_proof_and_no_shared_name_inference(case):
    core, c, _, _ = setup_case(case)
    board(
        core,
        claim="The Caltech record names Example Person, without wider identity resolution.",
    )
    d = c.get("/api/case/breakdown").json()
    t = next(t for t in d["topics"] if t["id"] == "caltech")
    assert t["supported_connections"] == 1
    assert t["connections"][0]["proof"][0]["quote"] == "Inventor Example Person"
    assert t["connections"][0]["source_checked"] is True
    roster = next(t for t in d["topics"] if t["id"] == "scientists")
    assert not roster["supported_connections"] and roster["status"] == "UNRESOLVED"
    assert not core.rows("SELECT * FROM automation_runs")


def test_missing_support_remains_visible_as_a_gap(case):
    core, c, _, _ = setup_case(case)
    board(
        core,
        quote="A nonexistent quotation",
        claim="The Caltech person is connected to JPL.",
    )
    d = c.get("/api/case/breakdown").json()
    t = next(t for t in d["topics"] if t["id"] == "caltech")
    assert t["connections"][0]["state"] == "SUPPORT COULD NOT BE VERIFIED"
    assert t["connections"][0]["proof"] == [] and t["supported_connections"] == 0


def test_duplicate_saved_analysis_is_grouped_and_full_report_links_validate_sources(
    case,
):
    core, c, sha, digest = setup_case(case)
    source = {
        "id": "E1",
        "sha256": sha,
        "text_sha256": digest,
        "quote": "Inventor Example Person",
        "title": "Owned patent",
    }
    result = {
        "sources": [source],
        "summary": "A saved source review, not a verified prediction.",
        "findings": [],
    }
    for i in range(2):
        core.execute(
            "INSERT INTO investigations(id,created,updated,status,result,question,provider) VALUES(?,?,?,?,?,?,?)",
            (
                str(i),
                "2026-10-01",
                "2026-10-02",
                "COMPLETE",
                json.dumps(result),
                "Which Mondaloy inventor name is printed?",
                "deterministic",
            ),
        )
    t = next(
        t
        for t in c.get("/api/case/breakdown").json()["topics"]
        if t["id"] == "mondaloy"
    )
    assert len(t["analyses"]) == 1 and t["status"] == "UNRESOLVED"
    href = t["analyses"][0]["href"]
    saved = c.get("/api" + href)
    assert (
        saved.status_code == 200
        and saved.json()["data"]["sources"][0]["quote"] == "Inventor Example Person"
    )
    core.ROOT.joinpath("originals", sha).write_bytes(b"CHANGED")
    assert c.get("/api" + href).status_code == 409
    assert c.get("/api/case/breakdown/analysis/arbitrary/0").status_code == 404


def test_original_record_and_secondary_note_are_distinct(case):
    core, c, _, _ = setup_case(case)
    core.execute("UPDATE evidence SET title='Mondaloy original patent'")
    core.execute(
        "INSERT INTO evidence(id,title,status,metadata) VALUES('N1','Fourteen-person proposed roster','SECONDARY SOURCE','{}')"
    )
    data = c.get("/api/case/breakdown").json()
    patent = next(t for t in data["topics"] if t["id"] == "mondaloy")
    roster = next(t for t in data["topics"] if t["id"] == "scientists")
    assert patent["documents"][0]["id"] == "E1"
    assert roster["notes"][0]["id"] == "N1" and not roster["documents"]
    assert not patent["supported_connections"]


def test_discovery_catalogues_do_not_count_as_proof_files(case):
    core, c, _, _ = setup_case(case)
    core.execute(
        "UPDATE evidence SET title='Mondaloy patent search response',mime='application/json'"
    )
    t = next(
        t
        for t in c.get("/api/case/breakdown").json()["topics"]
        if t["id"] == "mondaloy"
    )
    assert not t["documents"] and len(t["discovery_records"]) == 1
    assert t["supported_connections"] == 0


def test_unclassified_connections_are_not_silently_dropped(case):
    core, c, _, _ = setup_case(case)
    board(core, claim="The record explicitly names Example Person.")
    topics = c.get("/api/case/breakdown").json()["topics"]
    other = next(t for t in topics if t["id"] == "other")
    assert (
        other["supported_connections"] == 1
        and other["status"] == "DOCUMENTED CONNECTIONS"
    )
    assert other["takeaway"] == "The record explicitly names Example Person."


def test_identical_originals_are_not_multiple_proof_files(case):
    core, c, _, _ = setup_case(case)
    core.execute("UPDATE evidence SET title='Mondaloy original patent'")
    core.execute(
        "INSERT INTO evidence SELECT 'E2',title,kind,status,url,sha256,path,mime,size,created,metadata,text,preview FROM evidence WHERE id='E1'"
    )
    topic = next(
        t
        for t in c.get("/api/case/breakdown").json()["topics"]
        if t["id"] == "mondaloy"
    )
    assert len(topic["documents"]) == 1


def test_preserved_secondary_dossier_is_not_counted_as_original_proof(case):
    core, c, _, _ = setup_case(case)
    core.execute(
        "UPDATE evidence SET title='Expanded dossier legal claims',status='SECONDARY SOURCE'"
    )
    topic = next(
        t for t in c.get("/api/case/breakdown").json()["topics"] if t["id"] == "legal"
    )
    assert not topic["documents"] and topic["notes"][0]["status"] == "SECONDARY SOURCE"
