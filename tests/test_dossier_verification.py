"""A dossier's asserted certainty is never inherited as verified case evidence."""

# ruff: noqa: F401,F811
import json
import hashlib
from fastapi.testclient import TestClient
from backend.dossier_verification import install, split_claims
from test_case_briefing_automatic import case
from test_automation_controller import engine


def test_claim_units_preserve_verified_heading_without_endorsing_it():
    units = split_claims(
        "## 10. Assessment\n### 10.1 Verified Facts\n\n- A claimed connection in this supplied document is asserted to be true.\n- A second much longer assertion is still only supplied dossier material.\n"
    )
    assert len(units) == 2 and units[0]["subsection"] == "10.1 Verified Facts"
    assert units[0]["line"] == 4 and "status" not in units[0]


def setup(case):
    core, _, sha, digest = case
    meta = {
        "sandbox": True,
        "retrieval_method": "User upload",
        "derivative_hashes": {"text.txt": digest},
    }
    core.execute("UPDATE evidence SET metadata=? WHERE id=?", (json.dumps(meta), "E1"))
    core.execute(
        "CREATE TABLE jobs(id TEXT,url TEXT,status TEXT,error TEXT,evidence_id TEXT)"
    )
    controller = install(core)
    return core, TestClient(core.app), controller


def test_import_is_secondary_deduplicated_and_defaults_unverified(case):
    core, c, _ = setup(case)
    first = c.post("/api/dossiers/import", json={"evidence_id": "E1"})
    assert first.status_code == 200
    assert c.post("/api/dossiers/import", json={"evidence_id": "E1"}).json()[
        "deduplicated"
    ]
    report = c.get("/api/dossiers/verification").json()["dossiers"][0]
    assert (
        report["claims"][0]["status"] == "NOT VERIFIED"
        and report["claims"][0]["proof"] == []
    )
    assert (
        core.rows("SELECT status FROM evidence WHERE id='E1'")[0]["status"]
        == "SECONDARY SOURCE"
    )
    assert not core.rows("SELECT * FROM automation_runs")


def test_dossier_cannot_verify_itself_and_invalid_claim_ids_are_rejected(case):
    core, c, _ = setup(case)
    c.post("/api/dossiers/import", json={"evidence_id": "E1"})
    claim = c.get("/api/dossiers/verification").json()["dossiers"][0]["claims"][0]
    value = {
        "status": "SUPPORTED",
        "analysis": "Attempt to use the secondary dossier itself as primary proof.",
        "proof": [
            {
                "evidence_id": "E1",
                "quote": "Inventor Example Person",
                "sha256": core.rows("SELECT sha256 FROM evidence WHERE id='E1'")[0][
                    "sha256"
                ],
            }
        ],
    }
    assert (
        c.post(
            "/api/dossiers/claims/" + claim["id"] + "/review", json=value
        ).status_code
        == 422
    )
    assert c.post("/api/dossiers/claims/missing/review", json=value).status_code == 404


def test_review_needs_exact_current_original_and_is_invalidated_by_tampering(case):
    core, c, _ = setup(case)
    c.post("/api/dossiers/import", json={"evidence_id": "E1"})
    claim = c.get("/api/dossiers/verification").json()["dossiers"][0]["claims"][0]
    content = b"OWNED SYNTHETIC PRIMARY RECORD"
    sha = hashlib.sha256(content).hexdigest()
    path = core.ROOT / "originals" / sha
    path.write_bytes(content)
    text = "The official record lists Example Person in the inventor field."
    td = hashlib.sha256(text.encode()).hexdigest()
    folder = core.ROOT / "derivatives" / "E2"
    folder.mkdir()
    (folder / "text.txt").write_text(text)
    core.execute(
        "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "E2",
            "Owned primary record",
            "DOCUMENT",
            "ORIGINAL VERIFIED",
            "https://example.org/record",
            sha,
            str(path),
            "text/plain",
            len(content),
            core.now(),
            json.dumps({"sandbox": True, "derivative_hashes": {"text.txt": td}}),
            text,
            None,
        ),
    )
    value = {
        "status": "PARTIALLY SUPPORTED",
        "analysis": "The primary record supports only the printed inventor name, not the entire claim.",
        "proof": [
            {
                "evidence_id": "E2",
                "quote": "lists Example Person in the inventor field",
                "sha256": sha,
            }
        ],
    }
    assert (
        c.post(
            "/api/dossiers/claims/" + claim["id"] + "/review", json=value
        ).status_code
        == 200
    )
    result = c.get("/api/dossiers/verification").json()["dossiers"][0]["claims"][0]
    assert result["status"] == "PARTIALLY SUPPORTED"
    path.write_bytes(b"CHANGED")
    assert (
        c.get("/api/dossiers/verification").json()["dossiers"][0]["claims"][0]["status"]
        == "SUPPORT UNAVAILABLE"
    )


def test_failed_source_jobs_are_exposed_without_marking_claims_verified(case):
    core, c, _ = setup(case)
    did = c.post("/api/dossiers/import", json={"evidence_id": "E1"}).json()["id"]
    core.execute(
        "INSERT INTO jobs VALUES('J1','https://example.org/private','ACQUISITION FAILED','HTTP 403',NULL)"
    )
    assert (
        c.post(
            "/api/dossiers/" + did + "/sources", json={"job_ids": ["J1"]}
        ).status_code
        == 200
    )
    report = c.get("/api/dossiers/verification").json()["dossiers"][0]
    assert (
        report["acquisitions"][0]["error"] == "HTTP 403"
        and report["claims"][0]["status"] == "NOT VERIFIED"
    )


def test_new_source_candidates_do_not_approve_previously_unverified_claims(case):
    core, c, controller = setup(case)
    c.post("/api/dossiers/import", json={"evidence_id": "E1"})
    claim = c.get("/api/dossiers/verification").json()["dossiers"][0]["claims"][0]
    note = {
        "status": "NOT VERIFIED",
        "analysis": "The complete assertion is not supported by the currently preserved source collection.",
        "proof": [],
    }
    assert (
        c.post("/api/dossiers/claims/" + claim["id"] + "/review", json=note).status_code
        == 200
    )
    core.execute(
        "CREATE VIRTUAL TABLE evidence_fts USING fts5(id UNINDEXED,title,text)"
    )
    core.execute(
        "INSERT INTO evidence SELECT 'E2','Independent patent',kind,'ORIGINAL VERIFIED',url,sha256,path,mime,size,created,metadata,text,preview FROM evidence WHERE id='E1'"
    )
    core.execute(
        "INSERT INTO evidence_fts VALUES('E2','Independent patent','Original patent lists Inventor Example Person in an unrelated record.')"
    )
    controller["refresh_candidates"]()
    current = c.get("/api/dossiers/verification").json()["dossiers"][0]["claims"][0]
    assert (
        current["status"] == "NOT VERIFIED"
        and current["reviewed"]
        and current["candidates"]
    )
    unsupported = {**note, "status": "SUPPORTED"}
    assert (
        c.post(
            "/api/dossiers/claims/" + claim["id"] + "/review", json=unsupported
        ).status_code
        == 422
    )
