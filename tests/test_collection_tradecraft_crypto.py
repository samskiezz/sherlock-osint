import json
import os
import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.extended_ciphers import run
from backend.crypto_lab import operate, ALGORITHMS
from backend.tradecraft import analyse


@pytest.mark.parametrize("algorithm", list(ALGORITHMS))
def test_authenticated_crypto_round_trip_and_tamper_rejection(algorithm):
    key = os.urandom(64 if algorithm == "aes_siv" else 32)
    plain = b"Authorised forensic fixture"
    encrypted, nonce = operate(algorithm, "encrypt", key, plain, aad=b"case-1")
    recovered, _ = operate(algorithm, "decrypt", key, encrypted, nonce, b"case-1")
    assert recovered == plain
    tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    with pytest.raises(Exception):
        operate(algorithm, "decrypt", key, tampered, nonce, b"case-1")


def test_nist_aes_gcm_known_vector():
    result, _ = operate(
        "aes_gcm",
        "decrypt",
        bytes(16),
        bytes.fromhex(
            "0388dace60b6a392f328c2b971b2fe78ab6e47d42cec13bdf53a67b21257bddf"
        ),
        bytes(12),
    )
    assert result == bytes(16)


def test_classical_cryptanalysis_vectors_and_english_assumptions():
    assert run("GATLMZCLRQXA", "playfair", {"key": "MONARCHY"}) == "INSTRUMENTSX"
    assert run("HIAT", "hill2", {"key": "3,3,2,5"}) == "HELP"
    assert run("QNXEPVYTWTWP", "autokey", {"key": "QUEENLY"}) == "ATTACKATDAWN"
    report = json.loads(run("ABCABCABCABC", "kasiski", {}))
    assert report["repeats"] and "3" in report["factor_counts"]
    assert json.loads(run("SHORT", "friedman", {}))["estimated_key_length"] is None
    assert (
        json.loads(
            run("Wklv lv d frqyhqwlrqdo hqjolvk whvw phvvdjh", "caesar_scan", {})
        )["attempts"]
        == 26
    )


def test_statistical_baseline_missing_dispersion_and_information_gain():
    with pytest.raises(ValueError):
        analyse("mad", {"values": [1, 2, 3, 4]})
    r = analyse(
        "mad",
        {"values": [7, 7, 7, 7, 100], "reference_population": "Synthetic fixture"},
    )
    assert r["mad"] == 0 and r["outlier_indices"] == []
    r = analyse(
        "bayes", {"prior": 0.1, "likelihood_if_true": 0.8, "likelihood_if_false": 0.2}
    )
    assert r["posterior"] == pytest.approx(0.30769230769)
    r = analyse(
        "information_gain", {"prior": [0.5, 0.5], "outcomes": [[0.9, 0.1], [0.1, 0.9]]}
    )
    assert r["expected_information_gain_bits"] == pytest.approx(0.5310044064)
    r = analyse(
        "calibration",
        {
            "predictions": [
                {"probability": 0.8, "outcome": 1},
                {"probability": 0.2, "outcome": 0},
            ]
        },
    )
    assert r["brier_score"] == pytest.approx(0.04)


@pytest.fixture(scope="module")
def core(tmp_path_factory):
    os.environ["SHERLOCK_DATA"] = str(tmp_path_factory.mktemp("collection-vault"))
    from backend import app

    return app


@pytest.fixture(scope="module")
def source(core):
    client = TestClient(core.app)
    html = b"""<html><head><meta name="DC.type" content="patent"><meta name="DC.title" content="Alloy fixture"><meta name="citation_patent_publication_number" content="US:1234567:A1"><meta name="citation_pdf_url" content="https://example.com/fixture.pdf"><meta name="DC.contributor" content="Test Inventor" scheme="inventor"><meta property="og:image" content="https://example.com/photo.jpg"></head><body><h1>Cole Allen fixture: not real case evidence</h1><time itemprop="priorityDate" datetime="2001-09-18"></time><section itemprop="claims"><claim>The alloy fixture contains nickel.</claim></section></body></html>"""
    response = client.post(
        "/api/upload", files={"file": ("patent-fixture.html", html, "text/html")}
    )
    assert response.status_code == 200, response.text
    e = response.json()
    assert e["metadata"].get("patent"), e
    return e


def test_patent_media_metadata_and_declared_photo_attribution(core, source):
    client = TestClient(core.app)
    p = source["metadata"]["patent"]
    assert p["publication_number"] == ["US:1234567:A1"] and p["inventors"] == [
        "Test Inventor"
    ]
    assert p["claims"] == ["The alloy fixture contains nickel."]
    assert (
        source["metadata"]["media"][0]["attribution"]
        == "PUBLISHER ASSERTED / SUBJECT UNVERIFIED"
    )
    records = client.get("/api/patents").json()["records"]
    assert any(r["evidence_id"] == source["id"] for r in records)
    assert (
        client.post(
            "/api/photo-corpus/queue",
            json={
                "url": "https://example.com/invented.jpg",
                "parent_evidence_id": source["id"],
            },
        ).status_code
        == 422
    )


def test_vault_physical_bytes_and_consistent_database_snapshot(core, source, tmp_path):
    client = TestClient(core.app)
    inventory = client.get("/api/vault").json()
    assert (
        inventory["original_files"] >= 1
        and inventory["original_bytes"] >= source["size"]
    )
    manifest = client.get("/api/vault/manifest").json()
    assert all(r.get("hash_matches") for r in manifest["records"] if r["file_exists"])
    response = client.get("/api/vault/database")
    assert response.content.startswith(b"SQLite format 3")
    target = tmp_path / "snapshot.db"
    target.write_bytes(response.content)
    with sqlite3.connect(target) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM evidence WHERE id=?", (source["id"],)
            ).fetchone()[0]
            == 1
        )


def test_ach_requires_original_passages_and_dependency_groups_count_once(core, source):
    client = TestClient(core.app)
    payload = {
        "method": "ach",
        "inputs": {
            "hypotheses": ["H1", "H2"],
            "matrix": [
                {
                    "evidence_id": source["id"],
                    "ratings": [-2, 0],
                    "dependency_group": "same-newswire",
                },
                {
                    "evidence_id": source["id"],
                    "ratings": [-2, 0],
                    "dependency_group": "same-newswire",
                },
            ],
        },
        "citations": [
            {"evidence_id": source["id"], "quote": "The alloy fixture contains nickel."}
        ],
        "authorisation": "Public synthetic fixture",
    }
    response = client.post("/api/tradecraft/run", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert (
        result["output"]["hypotheses"][0]["inconsistency"] == 2
        and result["output"]["independent_groups"] == 1
    )
    assert (
        result["validation"] == "PROVISIONAL"
        and result["output"]["probability"] is None
    )
    payload["citations"][0]["quote"] = "Invented statement"
    assert client.post("/api/tradecraft/run", json=payload).status_code == 422


def test_registry_preserves_families_unimplemented_methods_and_dissent(core, source):
    client = TestClient(core.app)
    methods = client.get("/api/tradecraft").json()["methods"]
    assert sum(m["classification"] == "TECHNIQUE FAMILY" for m in methods) == 3
    assert any(
        m["implementation"] == "NOT IMPLEMENTED"
        and m["verification"] == "UNVERIFIED TAXONOMY ENTRY"
        for m in methods
    )
    r = client.post(
        "/api/tradecraft/run",
        json={
            "method": "devil",
            "inputs": {
                "answers": [
                    "Strong alternative is conventional publication context.",
                    "Need an independent contemporaneous record.",
                ],
                "dissent": ["Do not infer a common research team."],
            },
            "citations": [
                {
                    "evidence_id": source["id"],
                    "quote": "The alloy fixture contains nickel.",
                }
            ],
            "authorisation": "Public fixture study",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["output"]["dissent"] == ["Do not infer a common research team."]
    assert (
        client.post(
            "/api/tradecraft/run",
            json={"method": "diagnostic_family", "authorisation": "Fixture"},
        ).status_code
        == 422
    )


def test_crypto_api_never_persists_key_or_plaintext(core):
    client = TestClient(core.app)
    key = os.urandom(32).hex()
    plain = "Secret fixture string that must not appear in history"
    r = client.post(
        "/api/crypto/run",
        json={
            "algorithm": "aes_gcm",
            "operation": "encrypt",
            "key_hex": key,
            "input": plain,
            "encoding": "utf8",
            "authorisation": "Owned test material",
        },
    )
    assert r.status_code == 200, r.text
    ciphertext = r.json()
    r = client.post(
        "/api/crypto/run",
        json={
            "algorithm": "aes_gcm",
            "operation": "decrypt",
            "key_hex": key,
            "input": ciphertext["output_base64"],
            "encoding": "base64",
            "nonce_hex": ciphertext["nonce_hex"],
            "authorisation": "Owned test material",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["output_text"] == plain
    history = json.dumps(client.get("/api/crypto").json()["records"])
    assert key not in history and plain not in history
    stored = json.dumps(core.rows("SELECT data FROM crypto_records"))
    assert key not in stored and plain not in stored


def test_public_discovery_connectors_use_recorded_catalogues_and_do_not_claim_acquisition(
    core, monkeypatch
):
    from backend import discovery

    def mock(url, payload):
        monkeypatch.setattr(
            discovery,
            "preserve_response",
            lambda *args, **kwargs: ("CATALOGUE", payload, url),
        )

    mock(
        "https://www.bing.com/search",
        b"<rss><channel><item><title>Public Cole Allen report</title><link>https://example.com/report</link></item></channel></rss>",
    )
    result = discovery.search(core, "public_web", "Cole Allen")
    assert result["hits"][0]["status"] == "DISCOVERED · ORIGINAL NOT YET ACQUIRED"
    mock(
        "https://patents.google.com/xhr/query",
        json.dumps(
            {
                "results": {
                    "cluster": [
                        {
                            "result": [
                                {
                                    "patent": {
                                        "publication_number": "US20100266442A1",
                                        "title": "Burn-resistant alloys",
                                    }
                                }
                            ]
                        }
                    ]
                }
            }
        ).encode(),
    )
    result = discovery.search(core, "patents", "Mondaloy")
    assert (
        result["hits"][0]["url"]
        == "https://patents.google.com/patent/US20100266442A1/en"
    )
    mock(
        "https://commons.wikimedia.org/w/api.php",
        json.dumps(
            {
                "query": {
                    "pages": {
                        "1": {
                            "title": "File:Cole Allen.jpg",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/photo.jpg",
                                    "extmetadata": {
                                        "LicenseShortName": {"value": "CC BY"}
                                    },
                                }
                            ],
                        }
                    }
                }
            }
        ).encode(),
    )
    result = discovery.search(core, "commons", "Cole Allen")
    assert (
        result["hits"][0]["licence"] == "CC BY"
        and "identity review" in result["hits"][0]["attribution"]
    )


def test_campaign_edit_and_source_refresh_checkpoint(core, source, monkeypatch):
    from backend import research

    client = TestClient(core.app)
    value = {
        "name": "Refresh fixture campaign",
        "question": "Follow changes in this authorised fixture source",
        "queries": ["Cole Allen"],
        "providers": ["source_pages"],
        "seeds": ["https://example.com/source"],
        "max_downloads": 2,
        "cron_expression": "0 */6 * * *",
    }
    created = client.post("/api/research", json=value)
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    value["collect_images"] = True
    assert (
        client.patch("/api/research/" + cid, json=value).json()["current_run_unchanged"]
        is True
    )
    # Provider captures an actual already-preserved fixture. Pipeline does not refetch or claim a missing file.
    monkeypatch.setattr(
        research,
        "search",
        lambda *args, **kwargs: {
            "catalogues": [source["id"]],
            "hits": [
                {
                    "url": "https://example.com/source",
                    "title": "Fixture source",
                    "kind": "webpage",
                    "pre_acquired_id": source["id"],
                }
            ],
        },
    )
    result = client.post("/api/research/" + cid + "/run", json={})
    assert result.status_code == 200, result.text
    rid = core.research["launch"](cid)["id"]
    core.research["advance"](rid)
    core.research["advance"](rid)
    jobs = core.rows("SELECT * FROM research_run_jobs WHERE run_id=?", (rid,))
    assert jobs
    acquired = core.rows("SELECT * FROM jobs WHERE id=?", (jobs[0]["job_id"],))[0]
    assert acquired["status"] == "COMPLETE" and acquired["evidence_id"] == source["id"]


def test_provisional_analysis_pin_is_idempotent_and_never_factual(core, source):
    client = TestClient(core.app)
    result = client.post(
        "/api/tradecraft/run",
        json={
            "method": "bayes",
            "inputs": {
                "prior": 0.1,
                "likelihood_if_true": 0.8,
                "likelihood_if_false": 0.2,
            },
            "citations": [
                {
                    "evidence_id": source["id"],
                    "quote": "The alloy fixture contains nickel.",
                }
            ],
            "authorisation": "Owned synthetic fixture",
        },
    ).json()
    board = client.post(
        "/api/boards", json={"name": "Provisional analysis test"}
    ).json()
    first = client.post(
        "/api/tradecraft/records/" + result["id"] + "/pin",
        json={"board_id": board["id"]},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/tradecraft/records/" + result["id"] + "/pin",
        json={"board_id": board["id"]},
    ).json()
    assert (
        first.json()["evidence_id"] == second["evidence_id"]
        and second["reused"] is True
    )
    saved = client.get("/api/boards/" + board["id"]).json()
    assert all(e["data"]["state"] == "HYPOTHESIS" for e in saved["edges"])
    note = client.get("/api/evidence/" + second["evidence_id"]).json()
    assert note["status"] == "HYPOTHESIS" and note["fileUrl"] is None


def test_screening_lists_summaries_and_preserves_full_results_on_demand(core, source):
    client = TestClient(core.app)
    result = client.post("/api/forensics/" + source["id"] + "/screen").json()
    overview = client.get("/api/forensics").json()
    row = next(r for r in overview["runs"] if r["id"] == result["id"])
    assert "attempts" not in row["data"]
    full = client.get("/api/forensics/runs/" + result["id"]).json()
    assert full["data"]["rule_count"] == 51
    assert len(full["data"]["attempts"]) == 51


def test_provider_configuration_is_private_and_rejects_arbitrary_environment_fields(
    tmp_path, monkeypatch
):
    from backend.service_config import load

    path = tmp_path / "provider.json"
    path.write_text(json.dumps({"BRAVE_SEARCH_API_KEY": "owned-fixture-key"}))
    path.chmod(0o644)
    with pytest.raises(RuntimeError):
        load(path)
    path.chmod(0o600)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    load(path)
    assert os.environ["BRAVE_SEARCH_API_KEY"] == "owned-fixture-key"
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "injected-fixture")
    load(path)
    assert os.environ["BRAVE_SEARCH_API_KEY"] == "injected-fixture"
    path.write_text(json.dumps({"HOME": "untrusted override"}))
    with pytest.raises(RuntimeError):
        load(path)


def test_expected_image_does_not_accept_preserved_html_as_the_original(
    core, source, monkeypatch
):
    from backend import research

    client = TestClient(core.app)
    value = {
        "name": "Expected image fixture",
        "question": "Acquire the expected public image original",
        "queries": ["fixture"],
        "providers": ["public_web"],
        "max_downloads": 2,
        "cron_expression": "0 */6 * * *",
    }
    cid = client.post("/api/research", json=value).json()["id"]
    monkeypatch.setattr(
        research,
        "search",
        lambda *args, **kwargs: {
            "catalogues": [source["id"]],
            "hits": [
                {
                    "url": "https://example.com/photo.jpg",
                    "title": "Expected photograph fixture",
                    "kind": "image",
                    "pre_acquired_id": source["id"],
                }
            ],
        },
    )
    rid = core.research["launch"](cid)["id"]
    for _ in range(3):
        core.research["advance"](rid)
    registered = core.rows(
        "SELECT job_id FROM research_run_jobs WHERE run_id=?", (rid,)
    )
    assert registered
    job = core.rows("SELECT * FROM jobs WHERE id=?", (registered[0]["job_id"],))[0]
    assert job["status"] == "ACQUISITION FAILED" and "not returned" in job["error"]
    assert client.get("/api/evidence/" + source["id"]).json()["mime"] == "text/html"


def test_new_graph_analytics_bind_every_edge_and_preserve_snapshot(core, source):
    client = TestClient(core.app)
    methods = client.get("/api/tradecraft").json()["methods"]
    method = next(m["id"] for m in methods if m["name"] == "Betweenness centrality")
    payload = {
        "method": method,
        "inputs": {
            "nodes": ["a", "b", "c"],
            "edges": [
                {
                    "source": "a",
                    "target": "b",
                    "evidence_id": source["id"],
                    "state": "DOCUMENTED",
                },
                {
                    "source": "b",
                    "target": "c",
                    "evidence_id": source["id"],
                    "state": "DOCUMENTED",
                },
            ],
        },
        "citations": [
            {"evidence_id": source["id"], "quote": "The alloy fixture contains nickel."}
        ],
        "authorisation": "Owned synthetic fixture; graph is not a real case relationship",
    }
    result = client.post("/api/tradecraft/run", json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["output"]["centrality"]["b"] == 1
    assert result.json()["inputs"]["edges"] == payload["inputs"]["edges"]
    assert result.json()["citations"][0]["sha256"] == source["sha256"]
    payload["inputs"]["edges"][0]["state"] = "HYPOTHESIS"
    assert client.post("/api/tradecraft/run", json=payload).status_code == 422
    payload["inputs"]["edges"][0]["state"] = "DOCUMENTED"
    payload["citations"] = []
    assert client.post("/api/tradecraft/run", json=payload).status_code == 422


def test_integrated_classical_analysis_rejects_unsourced_input(core, source):
    client = TestClient(core.app)
    methods = client.get("/api/tradecraft").json()["methods"]
    method = next(m["id"] for m in methods if m["name"] == "Kasiski examination")
    payload = {
        "method": method,
        "inputs": {"text": "ABCABCABCABC"},
        "authorisation": "Owned fixture",
        "citations": [
            {"evidence_id": source["id"], "quote": "The alloy fixture contains nickel."}
        ],
    }
    assert client.post("/api/tradecraft/run", json=payload).status_code == 422
    payload["inputs"]["text"] = "The alloy fixture contains nickel."
    result = client.post("/api/tradecraft/run", json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["method_version"] == "1.1"
    assert (
        result.json()["output"]["normalised_input"] == "THEALLOYFIXTURECONTAINSNICKEL"
    )


def test_board_graph_monitor_deduplicates_changes_and_pause_persists(core, source):
    client = TestClient(core.app)
    method = next(
        m["id"]
        for m in client.get("/api/tradecraft").json()["methods"]
        if m["name"] == "Louvain community detection"
    )
    bid = core.uid("BOARD")
    board = {
        "id": bid,
        "name": "Synthetic monitor fixture",
        "nodes": [
            {
                "id": "a",
                "position": {"x": 0, "y": 0},
                "data": {"evidenceId": source["id"]},
            },
            {
                "id": "b",
                "position": {"x": 100, "y": 0},
                "data": {"evidenceId": source["id"]},
            },
        ],
        "edges": [
            {
                "id": "edge",
                "source": "a",
                "target": "b",
                "data": {
                    "state": "DOCUMENTED",
                    "evidence": [
                        {
                            "id": source["id"],
                            "quote": "The alloy fixture contains nickel.",
                        }
                    ],
                },
            }
        ],
    }
    core.execute(
        "INSERT INTO boards VALUES(?,?,?)", (bid, board["name"], json.dumps(board))
    )
    result = client.post(
        "/api/tradecraft/run",
        json={
            "method": method,
            "inputs": {"board_id": bid},
            "authorisation": "Synthetic authorised fixture",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["citations"][0]["sha256"] == source["sha256"]
    mid = client.post(
        f"/api/tradecraft/records/{result.json()['id']}/monitor",
        json={"interval_minutes": 15},
    ).json()["id"]
    initial = client.post(f"/api/analysis-monitors/{mid}/run").json()
    count = core.rows("SELECT count(*) n FROM analytic_records")[0]["n"]
    assert initial["data"]["status"] == "UPDATED"
    unchanged = client.post(f"/api/analysis-monitors/{mid}/run").json()
    assert unchanged["data"]["status"] == "UNCHANGED"
    assert core.rows("SELECT count(*) n FROM analytic_records")[0]["n"] == count
    board["edges"] = []
    core.execute("UPDATE boards SET data=? WHERE id=?", (json.dumps(board), bid))
    changed = client.post(f"/api/analysis-monitors/{mid}/run").json()
    assert (
        changed["data"]["status"] == "UPDATED"
        and changed["data"]["last_record_id"] != initial["data"]["last_record_id"]
    )
    client.patch(
        f"/api/analysis-monitors/{mid}", json={"enabled": False}
    ).raise_for_status()
    core.analysis_monitors["tick"](timestamp=10**12)
    assert (
        next(m for m in client.get("/api/analysis-monitors").json() if m["id"] == mid)[
            "enabled"
        ]
        == 0
    )
    assert (
        client.post(
            f"/api/tradecraft/records/{result.json()['id']}/monitor",
            json={"cron": "* * * * *"},
        ).status_code
        == 422
    )


def test_report_api_and_access_audit_chain(core, source):
    import fitz, zipfile, io

    client = TestClient(core.app)
    r = client.get("/api/export/pdf")
    assert r.status_code == 200
    with fitz.open(stream=r.content, filetype="pdf") as d:
        assert source["id"] in "".join(p.get_text() for p in d)
    r = client.get("/api/export/docx")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert source["id"].encode() in z.read("word/document.xml")
    verified = client.get("/api/audit/verify").json()
    assert verified["valid"] and verified["events_checked"] > 0
    assert any(
        json.loads(e["detail"]).get("path") == "/api/export/docx"
        for e in core.rows("SELECT detail FROM audit WHERE action='api_access'")
    )
