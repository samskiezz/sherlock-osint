"""Result-first workspaces must preserve evidence integrity and never enqueue work on reads."""

# ruff: noqa: F811

import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from backend.forensics import install as forensic_install
from backend.case_briefing import install as briefing_install
from backend.automatic_workspaces import install as workspaces_install
from test_automation_controller import engine  # noqa: F401


@pytest.fixture
def case(engine):
    """Use actual original/derivative files and the production integrity checker."""
    core, _, client = engine
    core.execute(
        "CREATE TABLE evidence(id TEXT PRIMARY KEY,title TEXT,kind TEXT,status TEXT,url TEXT,sha256 TEXT,path TEXT,mime TEXT,size INTEGER,created TEXT,metadata TEXT,text TEXT,preview TEXT)"
    )
    core.execute("CREATE TABLE boards(id TEXT,name TEXT,data TEXT)")
    core.execute(
        "CREATE TABLE investigations(id TEXT,created TEXT,updated TEXT,status TEXT,result TEXT)"
    )
    core.execute(
        "CREATE TABLE research_campaigns(id TEXT,name TEXT,enabled INTEGER,next_run REAL,settings TEXT,created TEXT)"
    )
    core.execute(
        "CREATE TABLE autopilot_dispatch(evidence_id TEXT,data TEXT,run_id TEXT,created TEXT)"
    )
    core.execute("CREATE TABLE patent_records(evidence_id TEXT,updated TEXT,data TEXT)")
    core.ROOT.joinpath("originals").mkdir()
    text = "Original patent lists Inventor Example Person. This is a synthetic source."
    original = b"SYNTHETIC OWNED DOCUMENT ORIGINAL"
    sha = hashlib.sha256(original).hexdigest()
    path = core.ROOT / "originals" / sha
    path.write_bytes(original)
    derivative = core.ROOT / "derivatives" / "E1"
    derivative.mkdir(parents=True)
    derivative.joinpath("text.txt").write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    core.execute(
        "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "E1",
            "Owned patent",
            "DOCUMENT",
            "ORIGINAL VERIFIED",
            "https://example.org/patent",
            sha,
            str(path),
            "application/pdf",
            len(original),
            "2026-10-01T12:00:00+00:00",
            json.dumps({"sandbox": True, "derivative_hashes": {"text.txt": digest}}),
            text,
            None,
        ),
    )
    core.forensics = forensic_install(core)
    core.visual = {"explanations": lambda: []}
    core.autopilot = {"settings": lambda: {"enabled": True}}
    core.onion = {"status": lambda: {"ready": False}}
    briefing_install(core)
    workspaces_install(core)
    return core, TestClient(core.app), sha, digest


def board(
    core,
    state="DOCUMENTED",
    quote="Inventor Example Person",
    claim="The patent lists Example Person as inventor.",
):
    """Store a synthetic source-supported board relationship."""
    core.execute(
        "INSERT INTO boards VALUES(?,?,?)",
        (
            "B1",
            "Owned patent board",
            json.dumps(
                {
                    "edges": [
                        {
                            "id": "edge",
                            "data": {
                                "state": state,
                                "claim": claim,
                                "evidence": [{"id": "E1", "quote": quote, "page": 1}],
                                "method": "Reviewed acquired page",
                                "confidence": "Name transcription only",
                            },
                        }
                    ]
                }
            ),
        ),
    )


def test_documented_statements_are_cited_and_repeated_reads_stable(case):
    core, c, _, _ = case
    board(core)
    first = c.get("/api/case/briefing").json()
    second = c.get("/api/case/briefing").json()
    assert first == second
    assert (
        first["documented_count"] == 1
        and first["findings"][0]["sources"][0]["location"] == "Page 1"
    )
    assert first["findings"][0]["recorded_at"] == "2026-10-01T12:00:00+00:00"
    assert not core.rows("SELECT * FROM automation_runs")
    assert not core.rows("SELECT * FROM automation_receipts")


@pytest.mark.parametrize(
    "corruption", ["original", "text", "index", "quote", "secondary"]
)
def test_corrupted_or_unsupported_material_never_becomes_a_fact(case, corruption):
    core, c, sha, _ = case
    board(
        core,
        quote="Not in this source"
        if corruption == "quote"
        else "Inventor Example Person",
    )
    if corruption == "original":
        core.ROOT.joinpath("originals", sha).write_bytes(b"CORRUPTED")
    if corruption == "text":
        core.ROOT.joinpath("derivatives", "E1", "text.txt").write_text("CORRUPTED")
    if corruption == "index":
        core.execute("UPDATE evidence SET text='CORRUPTED'")
    if corruption == "secondary":
        core.execute("UPDATE evidence SET status='SECONDARY SOURCE'")
    result = c.get("/api/case/briefing").json()
    assert result["documented_count"] == 0 and not result["findings"]
    assert len(result["withheld"]) == 1


def test_model_proposal_stays_provisional_and_hypothesis_stays_unresolved(case):
    core, c, sha, _ = case
    board(core, state="HYPOTHESIS", claim="Does this establish a second identity?")
    result = {
        "findings": [
            {
                "claim": "The inventor travelled through time.",
                "evidence_id": "E1",
                "quote": "Inventor Example Person",
                "original_sha256": sha,
            }
        ]
    }
    for i in range(2):
        core.execute(
            "INSERT INTO investigations VALUES(?,?,?,?,?)",
            (str(i), "2026-10-01", "2026-10-02", "COMPLETE", json.dumps(result)),
        )
    brief = c.get("/api/case/briefing").json()
    assert brief["documented_count"] == 0 and brief["proposal_count"] == 1
    assert brief["findings"][0]["kind"] == "AI PROPOSAL"
    assert len(brief["open_questions"]) == 1


def test_workspace_receipts_are_automatic_source_bound_and_do_not_relaunch(case):
    core, c, sha, digest = case
    data = {
        "tool": "decoder.auto",
        "finished_utc": "2026-10-02",
        "result": {
            "sources": [
                {"evidence_id": "E1", "original_sha256": sha, "text_sha256": digest}
            ],
            "output": {"candidates": [{"useful": True, "data": "HELLO"}]},
        },
    }
    core.execute(
        "INSERT INTO automation_receipts VALUES(?,?,?,?,?)",
        ("R1", "RUN1", "STEP", "COMPLETE", json.dumps(data)),
    )
    first = c.get("/api/case/workspaces/cipher").json()
    assert (
        first["enabled"]
        and first["results"][0]["summary"] == "Candidate decoding: HELLO"
    )
    assert first == c.get("/api/case/workspaces/cipher").json()
    assert c.get("/api/case/receipts/R1").json()["tool"] == "decoder.auto"
    assert c.get("/api/case/receipts/missing").status_code == 404
    assert not core.rows("SELECT * FROM automation_runs")
    assert c.get("/api/case/workspaces/nonexistent").status_code == 404
    core.ROOT.joinpath("originals", sha).write_bytes(b"CHANGED")
    assert not c.get("/api/case/workspaces/cipher").json()["results"]
    assert c.get("/api/case/receipts/R1").status_code == 409


def test_negative_decoder_output_does_not_become_a_hidden_message(case):
    from backend.automatic_workspaces import describe

    assert "no useful candidate" in describe(
        "decoder.auto", {"candidates": [{"data": "readable", "useful": False}]}
    )
    assert "do not establish" in describe(
        "gematria.all", {"results": [{"table": "ordinal", "sum": 42}]}
    )


def test_missing_comparison_source_withholds_entire_receipt(case):
    """A valid first source cannot hide a missing corpus/comparison input."""
    core, c, sha, digest = case
    data = {
        "tool": "decoder.auto",
        "result": {
            "sources": [
                {"evidence_id": "E1", "original_sha256": sha, "text_sha256": digest},
                {
                    "evidence_id": "MISSING",
                    "original_sha256": "missing",
                    "text_sha256": "missing",
                },
            ],
            "output": {"candidates": []},
        },
    }
    core.execute(
        "INSERT INTO automation_receipts VALUES(?,?,?,?,?)",
        ("R2", "RUN2", "STEP", "COMPLETE", json.dumps(data)),
    )
    assert not c.get("/api/case/workspaces/cipher").json()["results"]
    assert c.get("/api/case/receipts/R2").status_code == 409
