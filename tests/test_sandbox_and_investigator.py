"""Security and provenance integration tests. Probe uses a disposable test file only."""

import hashlib, json, time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.sandbox import run, read_result, SandboxError, availability


@pytest.fixture(scope="module")
def core(tmp_path_factory):
    # test_workflows owns the module-scoped test database when both suites run.
    import os

    if "backend.app" not in __import__("sys").modules:
        os.environ["SHERLOCK_DATA"] = str(tmp_path_factory.mktemp("investigator-vault"))
    from backend import app

    return app


@pytest.fixture
def client(core):
    return TestClient(core.app)


def test_real_sandbox_enforces_mounts_and_network(tmp_path):
    p = tmp_path / "fixture"
    p.write_bytes(b"Enforcement test original")
    p.chmod(0o400)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    result = run(p, "text/plain", sha, tmp_path / "derivatives", probe=True)
    assert all(
        result["metadata"]["probe"][k]
        for k in (
            "input_read_only",
            "network_blocked",
            "host_vault_absent",
            "root_read_only",
        )
    )
    assert result["sandbox"]["memory_bytes"] == 768 * 1024 * 1024
    assert result["sandbox"]["pids_limit"] == 64
    assert hashlib.sha256(p.read_bytes()).hexdigest() == sha


def test_unsafe_derivative_symlink_rejected(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("not an output")
    (output / "result.json").symlink_to(outside)
    with pytest.raises(SandboxError, match="unsafe derivative"):
        read_result(output)


def test_host_parsing_never_used_when_sandbox_missing(core, client, monkeypatch):
    from backend import sandbox

    monkeypatch.setattr(
        sandbox,
        "docker_args",
        lambda: (_ for _ in ()).throw(SandboxError("Sandbox unavailable test")),
    )
    e = client.post(
        "/api/upload",
        files={
            "file": (
                "no-host-fallback.txt",
                b"Read this only in isolation",
                "text/plain",
            )
        },
    ).json()
    assert e["status"] == "ORIGINAL ACQUIRED"
    assert e["text"] == ""
    assert e["metadata"]["processing_status"] == "BLOCKED"
    assert "Sandbox unavailable" in e["metadata"]["processing_failure"]


def test_integrity_rejects_tampered_indexed_text(core, client):
    e = client.post(
        "/api/upload",
        files={
            "file": (
                "attested.txt",
                b"The original mentions robotics and laboratories.",
                "text/plain",
            )
        },
    ).json()
    assert e["metadata"]["derivative_hashes"]["text.txt"]
    changed = {**e, "text": "An invented alternative passage"}
    good, reason = core.investigator["integrity"](changed)
    assert not good
    assert "Indexed text hash" in reason


def test_durable_workflow_exact_passages_and_no_automatic_edges(core, client):
    e = client.post(
        "/api/upload",
        files={
            "file": (
                "roster-source.txt",
                b"Monica Jacinto and Dallis Hardwick are printed as patent inventors. This does not establish a research team.",
                "text/plain",
            )
        },
    ).json()
    before = client.get("/api/boards/looking-glass").json()["edges"]
    r = client.post(
        "/api/investigations",
        json={"question": "Who are the patent inventors?", "evidence_ids": [e["id"]]},
    )
    assert r.status_code == 200
    run = r.json()
    assert len(run["tasks"]) == 7
    core.investigator["run"](run["id"])
    run = client.get("/api/investigations/" + run["id"]).json()
    assert run["status"] == "COMPLETE"
    assert all(t["status"] == "COMPLETE" for t in run["tasks"])
    assert run["result"]["sources"][0]["quote"] in e["text"]
    assert run["result"]["review_state"] == "REVIEW REQUIRED"
    assert run["result"]["findings"] == []
    assert client.get("/api/boards/looking-glass").json()["edges"] == before
    core.initialize()
    assert client.get("/api/investigations/" + run["id"]).json()["result"]["sources"]


def test_pause_resume_and_cancellation_are_checkpointed(core, client):
    run = client.post(
        "/api/investigations", json={"question": "A question with no source"}
    ).json()
    client.post("/api/investigations/" + run["id"] + "/pause")
    core.investigator["run"](run["id"])
    assert client.get("/api/investigations/" + run["id"]).json()["cursor"] == 0
    client.post("/api/investigations/" + run["id"] + "/resume")
    core.investigator["run"](run["id"])
    assert client.get("/api/investigations/" + run["id"]).json()["status"] == "COMPLETE"
    cancelled = client.post(
        "/api/investigations", json={"question": "Do not run this cancelled task"}
    ).json()
    client.post("/api/investigations/" + cancelled["id"] + "/cancel")
    core.investigator["run"](cancelled["id"])
    assert (
        client.get("/api/investigations/" + cancelled["id"]).json()["status"]
        == "CANCELLED"
    )


def test_fabricated_model_citation_rejected(core, client):
    e = client.post(
        "/api/upload",
        files={
            "file": (
                "citation.txt",
                b"The technical publication lists two named inventors.",
                "text/plain",
            )
        },
    ).json()
    result = core.investigator["validate"](
        {
            "findings": [
                {
                    "claim": "There are named inventors",
                    "evidence_id": e["id"],
                    "quote": "The technical publication lists two named inventors.",
                },
                {
                    "claim": "A secret project is proven",
                    "evidence_id": e["id"],
                    "quote": "There was a secret time travel project.",
                },
            ]
        },
        [e["id"]],
    )
    assert len(result["findings"]) == 1
    assert len(result["rejected"]) == 1
    assert result["findings"][0]["review_state"] == "REVIEW REQUIRED"


def test_missing_model_credentials_rejected(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post(
        "/api/investigations",
        json={
            "question": "Use an unavailable model",
            "provider": "anthropic",
            "model": "configured-model",
        },
    )
    assert r.status_code == 422


def test_cancelled_acquisition_status_not_overwritten(core):
    j = core.uid("TASK")
    core.execute(
        "INSERT INTO jobs(id,objective,url,status,progress,attempts,error,evidence_id,created,updated,result) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            j,
            "fixture",
            "https://example.org",
            "CANCELLED",
            10,
            1,
            None,
            None,
            core.now(),
            core.now(),
            None,
        ),
    )
    assert core.job_step(j, "COMPLETE", 100) is False
    assert (
        core.rows("SELECT status FROM jobs WHERE id=?", (j,))[0]["status"]
        == "CANCELLED"
    )


def test_model_quotes_must_be_in_supplied_passages(core, client):
    text = b"The supplied passage describes one inventor. Another passage outside the prompt describes a second inventor."
    e = client.post(
        "/api/upload", files={"file": ("supplied-window.txt", text, "text/plain")}
    ).json()
    candidate = {
        "claim": "There is a second inventor",
        "evidence_id": e["id"],
        "quote": "Another passage outside the prompt describes a second inventor.",
    }
    result = core.investigator["validate"](
        {"findings": [candidate]},
        [e["id"]],
        [{"id": e["id"], "quote": "The supplied passage describes one inventor."}],
    )
    assert result["findings"] == []
    assert "supplied" in result["rejected"][0]["reason"]


def test_model_adapter_receives_only_source_passages_and_auditor_rejects_fabrication(
    core, client, monkeypatch
):
    from backend import models

    e = client.post(
        "/api/upload",
        files={
            "file": (
                "model-fixture.txt",
                b"This acquired record names Monica and Dallis as inventors.",
                "text/plain",
            )
        },
    ).json()
    monkeypatch.setattr(
        models, "status", lambda: {"anthropic": {"ready": True, "model": "test-model"}}
    )
    calls = []

    def proposal(provider, model, question, sources):
        calls.append(sources)
        return {
            "summary": "Unverified draft",
            "limitations": [],
            "findings": [
                {
                    "claim": "This source names inventors",
                    "evidence_id": e["id"],
                    "quote": e["text"],
                    "location": "Wrong page 500",
                },
                {
                    "claim": "Secret research is proven",
                    "evidence_id": e["id"],
                    "quote": "A secret project certainly existed.",
                },
            ],
        }

    monkeypatch.setattr(models, "propose", proposal)
    r = client.post(
        "/api/investigations",
        json={
            "question": "Review these named inventors",
            "provider": "anthropic",
            "model": "test-model",
            "evidence_ids": [e["id"]],
        },
    ).json()
    core.investigator["run"](r["id"])
    result = client.get("/api/investigations/" + r["id"]).json()["result"]
    assert calls and calls[0][0]["quote"] == e["text"]
    assert len(result["findings"]) == 1
    assert len(result["rejected_findings"]) == 1
    assert result["findings"][0]["location"] != "Wrong page 500"
    assert result["findings"][0]["proposed_location"] == "Wrong page 500"
    assert result["review_state"] == "REVIEW REQUIRED"
    assert "No model finding is accepted" in result["summary"]


def test_case_file_paths_rebase_without_changing_evidence_identity(core, client):
    e = client.post(
        "/api/upload",
        files={
            "file": (
                "portable.txt",
                b"This original can move between case directories.",
                "text/plain",
            )
        },
    ).json()
    core.execute(
        "UPDATE evidence SET path=? WHERE id=?",
        ("/old-machine/nonexistent-vault/original", e["id"]),
    )
    core.initialize()
    restored = core.rows("SELECT * FROM evidence WHERE id=?", (e["id"],))[0]
    assert restored["sha256"] == e["sha256"]
    assert Path(restored["path"]).parent == core.ROOT / "originals"
    assert (
        client.get(e["fileUrl"]).content
        == b"This original can move between case directories."
    )


def test_task_graph_creation_rolls_back_atomically(core, client, monkeypatch):
    before = core.rows("SELECT count(*) n FROM investigations")[0]["n"]
    before_tasks = core.rows("SELECT count(*) n FROM investigator_tasks")[0]["n"]
    real = core.uid
    counter = [0]

    def interrupted(prefix):
        if prefix == "AGENT":
            counter[0] += 1
            if counter[0] == 3:
                raise RuntimeError("Fixture interruption while creating task graph")
        return real(prefix)

    monkeypatch.setattr(core, "uid", interrupted)
    with pytest.raises(RuntimeError, match="Fixture interruption"):
        client.post("/api/investigations", json={"question": "Atomic creation fixture"})
    assert core.rows("SELECT count(*) n FROM investigations")[0]["n"] == before
    assert (
        core.rows("SELECT count(*) n FROM investigator_tasks")[0]["n"] == before_tasks
    )


def test_auditor_rechecks_originals_even_without_model_findings(core, client):
    e = client.post(
        "/api/upload",
        files={
            "file": (
                "independent-audit.txt",
                b"A record for independent byte and text hash checking.",
                "text/plain",
            )
        },
    ).json()
    result = core.investigator["validate"]({"findings": []}, [e["id"]])
    assert result["integrity_checks"][0]["valid"]
    assert result["integrity_checks"][0]["original_sha256"] == e["sha256"]
    path = core.ROOT / "originals" / e["sha256"]
    path.chmod(0o600)
    path.write_bytes(b"Tampered fixture original")
    result = core.investigator["validate"]({"findings": []}, [e["id"]])
    assert not result["integrity_checks"][0]["valid"]
    assert result["integrity_checks"][0]["reason"] == "Original hash mismatch"


def test_requested_pdf_page_overrides_generic_keyword_scores(core, client):
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((40, 60), "Inventors: Alice Example and Dallis Demo.")
    doc.new_page().insert_text(
        (40, 60),
        "Inventors names patent documents inventor background technical notes.",
    )
    data = doc.tobytes()
    doc.close()
    e = client.post(
        "/api/upload", files={"file": ("page-selection.pdf", data, "application/pdf")}
    ).json()
    run = client.post(
        "/api/investigations",
        json={
            "question": "Which inventor names appear on page 1?",
            "evidence_ids": [e["id"]],
        },
    ).json()
    core.investigator["run"](run["id"])
    result = client.get("/api/investigations/" + run["id"]).json()["result"]
    assert result["sources"][0]["location"] == "Page 1"
    assert "Alice Example" in result["sources"][0]["quote"]


def test_question_boilerplate_does_not_displace_field_match(core, client):
    text = (
        "Inventor\nAlice Example\nDallis Demo\n"
        + "Technical background. " * 130
        + "which background commentary "
        + "Unrelated material. " * 100
    ).encode()
    e = client.post(
        "/api/upload", files={"file": ("field-selection.txt", text, "text/plain")}
    ).json()
    run = client.post(
        "/api/investigations",
        json={
            "question": "Which two names are listed under Inventor? Quote only each actual name.",
            "evidence_ids": [e["id"]],
        },
    ).json()
    core.investigator["run"](run["id"])
    result = client.get("/api/investigations/" + run["id"]).json()["result"]
    assert "Alice Example" in result["sources"][0]["quote"]
    assert result["sources"][0]["start"] == 0


def test_ollama_adapter_bounds_generation_and_enumerates_actual_source_ids(monkeypatch):
    from backend import models

    payloads = []

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "findings": [],
                            "limitations": ["No conclusion"],
                            "summary": "A proposal only",
                        }
                    )
                }
            }

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json):
            payloads.append(json)
            return Reply()

    monkeypatch.setattr(models.httpx, "Client", Client)
    response = models.propose(
        "ollama",
        "local-test",
        "Question",
        [
            {
                "id": "EV-real-source",
                "title": "Original",
                "quote": "Actual passage",
                "location": "Page 1",
            }
        ],
    )
    assert response["findings"] == []
    assert payloads[0]["options"] == {
        "temperature": 0,
        "num_predict": 600,
        "num_ctx": 4096,
        "num_thread": 4,
    }
    assert payloads[0]["format"]["properties"]["findings"]["items"]["properties"][
        "evidence_id"
    ]["enum"] == ["EV-real-source"]
    assert "tools" not in payloads[0]


def test_proposal_attachment_is_idempotent_and_remains_hypothesis(
    core, client, monkeypatch
):
    from backend import models

    e = client.post(
        "/api/upload",
        files={
            "file": (
                "proposal-source.txt",
                b"The record names Alice Example as an inventor.",
                "text/plain",
            )
        },
    ).json()
    monkeypatch.setattr(
        models, "status", lambda: {"anthropic": {"ready": True, "model": "fixture"}}
    )
    monkeypatch.setattr(
        models,
        "propose",
        lambda *args: {
            "summary": "Unverified draft",
            "limitations": [],
            "findings": [
                {
                    "claim": "This record names Alice Example",
                    "evidence_id": e["id"],
                    "quote": e["text"],
                    "location": "Source paragraph",
                }
            ],
        },
    )
    r = client.post(
        "/api/investigations",
        json={
            "question": "Inspect the named inventor",
            "provider": "anthropic",
            "model": "fixture",
            "evidence_ids": [e["id"]],
        },
    ).json()
    core.investigator["run"](r["id"])
    path = "/api/investigation-findings/" + r["id"] + "/0/attach"
    first = client.post(path, json={"board_id": "looking-glass"})
    assert first.status_code == 200
    note = client.get("/api/evidence/" + first.json()["evidence_id"]).json()
    assert note["status"] == "HYPOTHESIS"
    assert not note["fileUrl"]
    assert note["metadata"]["actor"].startswith("AI")
    second = client.post(path, json={"board_id": "looking-glass"})
    assert second.json()["already_attached"]
    board = client.get("/api/boards/looking-glass").json()
    edge = next(e for e in board["edges"] if e["id"] == "support-" + note["id"])
    assert edge["data"]["state"] == "HYPOTHESIS"
    assert edge["data"]["evidence"][0]["quote"] == e["text"]
    assert (
        len([n for n in board["nodes"] if n["data"].get("evidenceId") == note["id"]])
        == 1
    )
