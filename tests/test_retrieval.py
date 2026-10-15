"""Known-vector segmentation tests and real local-store retrieval acceptance tests."""

import hashlib
import json
import math
from pathlib import Path
import time

import httpx
import pytest

from backend.retrieval import (
    split_passages,
    identifiers,
    reciprocal_rank_fusion,
    Services,
)


def test_exact_passages_preserve_pages_unicode_offsets_and_overlap():
    text = (
        "\n[Page 1]\n"
        + ("Ni–Cr alloy. " * 120)
        + "\n[Page 2]\nInventors: Monica A. Jacinto and Dallis Ann Hardwick."
    )
    chunks = split_passages(text)
    assert len(chunks) > 2
    assert all(text[c["start"] : c["end"]] == c["text"] for c in chunks)
    assert {c["page"] for c in chunks} == {1, 2}
    assert chunks[0]["end"] - chunks[1]["start"] == 100
    assert not any("[Page " in c["text"] for c in chunks)
    for i in range(len(text)):
        if text[i : i + 1].strip() and not any(
            m <= i < n
            for m, n in [
                (0, 10),
                (text.index("\n[Page 2]"), text.index("\n[Page 2]") + 10),
            ]
        ):
            assert any(c["start"] <= i < c["end"] for c in chunks)


def test_identifiers_are_literal_spans_and_do_not_infer_people_or_ownership():
    text = "US 20030053926A1 and US20030053926A1; @CForce3000; 2023-12-22. Cole Allen. DOI 10.1234/abc."
    found = identifiers(text)
    assert all(text[x["start"] : x["end"]] == x["value"] for x in found)
    patents = [x for x in found if x["kind"] == "PATENT"]
    assert len(patents) == 2 and patents[0]["normalized"] == patents[1]["normalized"]
    assert not any("Cole" in x["value"] for x in found)
    assert any(x["value"] == "10.1234/abc" for x in found)


def test_rrf_known_ranks_duplicates_and_no_probabilistic_confidence():
    ranking = reciprocal_rank_fusion([["a", "b", "b"], ["b", "c"]])
    assert ranking[0][0] == "b"
    assert ranking[0][1] == pytest.approx(1 / 62 + 1 / 61)
    assert sum(s for _, s in ranking) < 1
    assert reciprocal_rank_fusion([]) == []


@pytest.fixture(scope="module")
def live():
    """Use the running owned gateway and stores; do not mock a successful acquisition."""
    root = Path(__file__).resolve().parents[1]
    client = httpx.Client(
        base_url="http://127.0.0.1:8010", trust_env=False, timeout=120
    )
    for _ in range(100):
        try:
            health = client.get("/health", timeout=3)
            if health.status_code == 200 and health.json().get("status") == "ok":
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    else:
        raise AssertionError("The real gateway did not become healthy")
    login = client.post(
        "/api/v1/auth/login",
        json=json.loads(
            (root / "data/foundation-secrets/admin-login.json").read_text()
        ),
    )
    login.raise_for_status()
    client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    yield client, root
    client.close()


def test_real_embedding_manifest_vectors_and_semantic_paraphrase_ranking(live):
    _, root = live
    s = Services(root / "data")
    try:
        s.validate_model()
        vectors = s.embed(
            [
                "A nickel alloy resists burning in rocket engines.",
                "An oxygen resistant superalloy for propulsion.",
                "A recipe for chocolate sponge cake.",
            ]
        )
        assert len(vectors) == 3 and len(vectors[0]) == 384
        assert all(
            math.sqrt(sum(x * x for x in v)) == pytest.approx(1, abs=1e-5)
            for v in vectors
        )
        similarity = lambda a, b: sum(x * y for x, y in zip(a, b))
        assert similarity(vectors[0], vectors[1]) > similarity(vectors[0], vectors[2])
    finally:
        s.close()


def test_real_hybrid_search_returns_original_bytes_exact_offsets_and_pages(live):
    c, root = live
    # The durable indexer must finish at least the first acquired patent.
    for _ in range(90):
        r = c.post(
            "/api/knowledge/search",
            json={
                "query": "burn resistant high tensile strength metal alloys",
                "mode": "hybrid",
                "limit": 20,
            },
        )
        r.raise_for_status()
        hits = r.json()["results"]
        if any(
            "US20030053926A1" in h["title"] or "Mondaloy" in h["title"] for h in hits
        ):
            break
        time.sleep(0.5)
    assert hits
    assert any(
        "US20030053926A1" in h["title"] or "Mondaloy" in h["title"] for h in hits
    )
    for h in hits:
        assert h["citation_verified"]
        e = c.get("/api/evidence/" + h["evidence_id"]).json()
        assert e["text"][h["start"] : h["end"]] == h["text"]
        original = root / "data/originals" / h["original_sha256"]
        derivative = root / "data/derivatives" / h["evidence_id"] / "text.txt"
        assert hashlib.sha256(original.read_bytes()).hexdigest() == h["original_sha256"]
        assert hashlib.sha256(derivative.read_bytes()).hexdigest() == h["text_sha256"]
    assert r.json()["answer"]["type"] == "EXTRACTIVE EVIDENCE SET"
    assert not any(h["acquisition_status"] == "SECONDARY SOURCE" for h in hits)


def test_keyword_search_query_validation_and_real_index_inventory(live):
    c, _ = live
    assert c.post("/api/knowledge/search", json={"query": "x"}).status_code == 422
    assert (
        c.post(
            "/api/knowledge/search", json={"query": "metal", "mode": "invent"}
        ).status_code
        == 422
    )
    response = c.post(
        "/api/knowledge/search", json={"query": "metal alloys", "mode": "keyword"}
    )
    response.raise_for_status()
    assert response.json()["results"]
    s = c.get("/api/knowledge/status").json()
    assert s["chunks"] > 2 and s["dimensions"] == 384 and s["interval_seconds"] == 60
    response = c.get("/api/knowledge/identifiers?kind=FAKE")
    assert response.status_code == 422


def test_shared_identifiers_have_exact_source_spans_and_no_factual_graph_edges(live):
    c, _ = live
    r = c.get("/api/knowledge/identifiers?kind=PATENT")
    r.raise_for_status()
    assert "No graph edge" in r.json()["interpretation"]
    for group in r.json()["results"]:
        assert group["independent_source_count"] == "NOT ESTABLISHED"
        for m in group["occurrences"]:
            e = c.get("/api/evidence/" + m["evidence_id"]).json()
            assert (
                e["text"][m["start"] : m["end"]] == m["value"]
                and m["citation_verified"]
            )


def test_saved_query_history_export_and_priority_queue_are_real(live):
    c, _ = live
    r = c.post(
        "/api/knowledge/search", json={"query": "metal alloys", "mode": "hybrid"}
    )
    r.raise_for_status()
    record = r.json()
    saved = c.get("/api/knowledge/queries/" + record["id"])
    saved.raise_for_status()
    assert saved.json() == record
    data = c.get("/api/export/json").json()
    assert any(row["id"] == record["id"] for row in data["retrieval_queries"])
    assert data["retrieval_chunks"] and "retrieval_requests" in data
    assert c.get("/api/knowledge/queries/NOT-PRESENT").status_code == 404
    assert (
        c.post("/api/knowledge/index", json={"evidence_id": "NOT-PRESENT"}).status_code
        == 404
    )


def test_viewer_can_search_but_cannot_queue_index_or_change_rights(live):
    import secrets

    c, _ = live
    username = "query-viewer-" + secrets.token_hex(4)
    password = secrets.token_urlsafe(24)
    r = c.post(
        "/api/v1/users",
        json={"username": username, "password": password, "role": "Viewer"},
    )
    r.raise_for_status()
    with httpx.Client(
        base_url="http://127.0.0.1:8010", trust_env=False, timeout=120
    ) as viewer:
        r = viewer.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        r.raise_for_status()
        viewer.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        r = viewer.post("/api/knowledge/search", json={"query": "metal alloys"})
        r.raise_for_status()
        assert r.json()["results"]
        assert viewer.post("/api/knowledge/index", json={}).status_code == 403
        assert (
            viewer.post(
                "/api/evidence/EV-32234078df6a/licence-review",
                json={
                    "redistributable": True,
                    "licence": "not authorised",
                    "basis": "This must be rejected by the reading role",
                },
            ).status_code
            == 403
        )


def test_full_platform_launchd_configuration_is_generated_without_claiming_mac_execution():
    from scripts.install_macos_service import mac_plist

    r = mac_plist(Path("/example/sherlock"), full_platform=True)
    assert r["ProgramArguments"] == [
        "/example/sherlock/.venv/bin/python",
        "/example/sherlock/scripts/run_platform.py",
        "--services",
    ]
    assert r["KeepAlive"] and r["RunAtLoad"]


def test_metadata_catalogue_is_paginated_and_preserves_source_provenance(live):
    c, _ = live
    first = c.get("/api/vault/catalogue", params={"limit": 2}).json()
    assert len(first["records"]) == 2 and first["next_cursor"]
    second = c.get(
        "/api/vault/catalogue", params={"limit": 2, "after": first["next_cursor"]}
    ).json()
    assert not (
        {e["id"] for e in first["records"]} & {e["id"] for e in second["records"]}
    )
    for row in first["records"] + second["records"]:
        full = c.get("/api/evidence/" + row["id"]).json()
        assert row["sha256"] == full["sha256"] and row["status"] == full["status"]
        assert "text" not in row and "pages" not in row["metadata"]
        for key in ("original_url", "retrieved_utc", "derivative_hashes"):
            if key in full["metadata"]:
                assert row["metadata"][key] == full["metadata"][key]
    assert c.get("/api/vault/catalogue", params={"limit": 1000}).status_code == 422
