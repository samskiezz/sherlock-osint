"""Known vectors, genuine parallel subprocess execution and explicit unconfigured-source behavior."""

# Imported pytest fixture names are also test parameters.
# ruff: noqa: F811
import hashlib, json, time
import pytest
import numpy as np
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from backend.gematria import analyse, calculate, TABLES
from backend.autopilot import candidate_spans
from backend.prediction_audit import Audit, evaluate
from backend.social_watch import normalise_posts, install as install_social
from backend.visual_intelligence import compare_features
from backend.sandbox import run as sandbox_run
from test_automation_controller import engine, plan  # noqa: F401


def test_gematria_known_vectors_ignores_nonletters_and_does_not_transliterate():
    a = analyse({"text": "Cole Allen", "targets": ["Allen Cole"]})
    sums = {x["table"]: x for x in a["results"]}
    assert (
        sums["english_ordinal"]["sum"] == 79 and sums["english_reverse"]["sum"] == 164
    )
    assert sums["english_ordinal"]["matches"] == [{"text": "Allen Cole", "sum": 79}]
    assert a["tables_attempted"] == 8 and a["target_comparisons_attempted"] == 8
    assert calculate("חַי", TABLES["hebrew_standard"])["sum"] == 18
    assert calculate("Ἰησοῦς", TABLES["greek_isopsephy"])["sum"] == 888
    assert calculate("ךםןףץ", TABLES["hebrew_final_extended"])["sum"] == 3500
    assert calculate("שלום", TABLES["english_ordinal"])["matched_letters"] == 0
    assert all(x["matched_letters"] == 0 for x in analyse({"text": "123 !"})["results"])


def test_gematria_normalisation_offsets_controls_and_reproducibility():
    x = analyse({"text": "Ａb!", "seed": 9})
    assert x == analyse({"text": "Ａb!", "seed": 9})
    result = x["results"][0]
    assert [(r["offset"], r["value"]) for r in result["contributions"]] == [
        (0, 1),
        (1, 2),
    ]
    assert result["ignored"] == [{"offset": 2, "character": "!"}]
    assert (
        result["toy_controls"]["n"] == 128
        and "not a meaningful negative control" in result["permutation_control"]
    )
    with pytest.raises(ValueError):
        analyse({"text": "a" * 4001})


def test_candidate_scanner_preserves_exact_source_spans():
    text = "Original Cole Allen; hexadecimal 436f6c6520416c6c656e and NDg2NTZjNmM2ZjIwNzc2ZjcyNmM2NA==."
    found = candidate_spans(text)
    assert any(x["kind"] == "hex" for x in found) and any(
        x["kind"] == "base64" for x in found
    )
    assert all(text[x["start"] : x["end"]] == x["text"] for x in found)
    assert all(x["kind"] != "person" for x in found)


def test_real_independent_actions_overlap_and_dependencies_wait(engine):
    core, controller, client = engine
    definition = plan(
        [
            {
                "id": name,
                "tool": "text.word_frequency",
                "inputs": {"text": "actual owned synthetic fixture"},
            }
            for name in ["a", "b", "c"]
        ]
        + [
            {
                "id": "join",
                "tool": "text.token_spans",
                "depends_on": ["a", "b", "c"],
                "inputs": {"text": "joined after predecessors"},
            }
        ]
    )
    definition["parallelism"] = 3
    w = client.post("/api/automation/workflows", json=definition).json()
    r = controller["launch"](w["id"])
    r = controller["advance"](r["id"])
    assert len(r["receipts"]) == 3 and all(
        x["status"] == "COMPLETE" for x in r["receipts"]
    )
    starts = [x["data"]["started_unix"] for x in r["receipts"]]
    ends = [x["data"]["finished_unix"] for x in r["receipts"]]
    assert max(starts) < min(ends), (
        "Independent real subprocess execution did not overlap"
    )
    r = controller["advance"](r["id"])
    assert r["status"] == "COMPLETE"
    joined = next(x for x in r["receipts"] if x["step_id"] == "join")
    assert joined["data"]["started_unix"] >= max(ends)


def test_x_fixture_normalisation_does_not_infer_identity_or_archive_date():
    payload = {
        "data": [
            {
                "id": "1738018409441308955",
                "text": "Cole Allen",
                "author_id": "111",
                "created_at": "2023-12-22T00:00:00Z",
                "attachments": {"media_keys": ["m1"]},
            }
        ],
        "includes": {
            "users": [{"id": "111", "username": "example"}],
            "media": [
                {
                    "media_key": "m1",
                    "type": "photo",
                    "url": "https://example.org/public.png",
                }
            ],
        },
    }
    p = normalise_posts(payload)[0]
    assert p["username_reported"] == "example" and p["author_id"] == "111"
    assert (
        p["post_created_at_reported"] == "2023-12-22T00:00:00Z"
        and "require independent evidence" in p["attribution"]
    )
    assert p["media"][0]["type"] == "photo" and "verified_identity" not in p


def test_x_missing_credential_is_visible_and_no_original_is_claimed(
    engine, monkeypatch
):
    core, _, _ = engine
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    install_social(core)
    c = TestClient(core.app)
    f = c.post(
        "/api/social/feeds",
        json={"name": "Owned fixture query", "query": "from:example"},
    ).json()
    r = c.post("/api/social/feeds/" + f["id"] + "/poll", json={})
    assert r.status_code == 200 and r.json()["status"] == "NOT_CONFIGURED"
    assert not r.json()["captures"] and r.json()["posts_received"] == 0
    assert c.get("/api/social").json()["configured"] is False


def test_prediction_audit_rejects_postevent_unspecific_and_uncorroborated_claims():
    value = Audit(
        artefact_id="EV-one",
        artefact_quote="Cole Allen",
        claimed_publication_utc="2023-12-22T00:00:00Z",
        event_utc="2026-04-25T00:00:00Z",
        specific_outcome="An explicitly described attack at a named event",
        specificity_terms=["attack", "2026"],
    )
    result = evaluate(value, "Cole Allen")
    assert result["assessment"] == "NOT ESTABLISHED" and result[
        "missing_specificity_terms"
    ] == ["attack", "2026"]
    assert (
        not result["forecast_claim"]
        and not result["independent_timestamp_quote_present"]
    )
    with pytest.raises(ValueError):
        evaluate(value, "A different name")
    with pytest.raises(ValueError):
        evaluate(value.model_copy(update={"event_utc": "2026-04-25"}), "Cole Allen")


def test_distinct_timestamp_quote_is_not_certification_of_foreknowledge():
    value = Audit(
        artefact_id="a",
        artefact_quote="Example event in 2030",
        claimed_publication_utc="2025-01-01T00:00:00Z",
        event_utc="2030-01-01T00:00:00Z",
        specific_outcome="Example event in 2030",
        specificity_terms=["event", "2030"],
        timestamp_source_id="b",
        timestamp_quote="Archive record",
    )
    r = evaluate(value, "Example event in 2030", "Archive record")
    assert (
        r["assessment"] == "CHRONOLOGY CANDIDATE / HUMAN REVIEW REQUIRED"
        and not r["forecast_claim"]
    )


def test_isolated_image_signatures_and_known_resize_vs_unrelated_control(tmp_path):
    im = Image.new("RGB", (420, 420), "white")
    draw = ImageDraw.Draw(im)
    rng = np.random.default_rng(42)
    for i in range(60):
        x, y = map(int, rng.integers(5, 380, size=2))
        color = tuple(map(int, rng.integers(0, 255, size=3)))
        draw.rectangle((x, y, x + 20, y + 20), fill=color)
        draw.text((x, y), str(i), fill="black")
    originals = [
        im,
        im.resize((630, 630)),
        Image.fromarray(rng.integers(0, 256, (420, 420, 3), dtype=np.uint8)),
    ]
    features = []
    for i, image in enumerate(originals):
        path = tmp_path / f"owned-{i}.png"
        image.save(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result = sandbox_run(path, "image/png", digest, tmp_path / f"derivative-{i}")
        features.append(result["metadata"]["visual_features"])
        assert (tmp_path / f"derivative-{i}" / "visual-blur-8.png").is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    same = compare_features(features[0], features[1])
    control = compare_features(features[0], features[2])
    assert same["hash_distances"]["phash"] < 8 and same["ransac_inliers"] >= 10
    assert same["ransac_inliers"] > control["ransac_inliers"]
    assert control["hash_distances"]["phash"] > 8
    assert same["assessment"] == "SIMILARITY LEAD / HUMAN REVIEW REQUIRED"


def test_automatic_profile_keeps_multilingual_corpus_references_bounded(engine):
    """Large multilingual sources must not inflate each workflow by repeating corpus bytes."""
    from backend.autopilot import install

    core, controller, _ = engine
    core.automation = controller
    core.execute(
        "CREATE TABLE evidence(id TEXT PRIMARY KEY,path TEXT,created TEXT,metadata TEXT)"
    )
    sources = {}
    for i in range(10):
        eid = "OWNED-" + str(i)
        text = ("😀 科學資料 " * 1000) + " distinct study data."
        digest = hashlib.sha256(text.encode()).hexdigest()
        sources[eid] = {
            "id": eid,
            "title": "Owned multilingual profile fixture " + str(i),
            "mime": "text/plain",
            "sha256": digest,
            "text": text,
        }
        core.execute(
            "INSERT INTO evidence VALUES(?,?,?,?)",
            (eid, "owned-fixture", core.now(), "{}"),
        )
    core.forensics = {"source": lambda eid: (sources[eid], {}, sources[eid]["sha256"])}
    automatic = install(core)
    dispatched = automatic["dispatch"]("OWNED-0")
    run = controller["get_run"](dispatched["run_id"])
    definition = run["data"]["plan"]
    corpus = [s for s in definition["steps"] if s["id"].startswith("corpus_")]
    assert len(corpus) == 8 and all(
        len(s["inputs"]["corpus_sources"]) == 8 for s in corpus
    )
    assert all("texts" not in s["inputs"] for s in corpus)
    assert len(json.dumps(definition).encode()) < 256000
    assert automatic["dispatch"]("OWNED-0")["deduplicated"] is True


def test_authorised_archive_import_preserves_observations_and_never_executes_js(engine):
    """Imported archive text is parsed as JSON; edits retain distinct original-source observations."""
    core, _, _ = engine
    payloads = {
        "owned-first": "window.YTD.tweets.part0 = "
        + json.dumps(
            [{"tweet": {"id_str": "1234", "full_text": "owned first version"}}]
        )
        + ";",
        "owned-second": json.dumps(
            {"data": [{"id": "1234", "text": "owned second version"}]}
        ),
        "invalid-js": 'window.YTD.tweets.part0 = __import__("os").system("false");',
        "oversized": json.dumps(
            {"data": [{"id": str(i), "text": "owned"} for i in range(10001)]}
        ),
    }

    def source(eid):
        """Provide explicitly synthetic acquired-text fixtures for the JSON parser boundary."""
        text = payloads[eid]
        digest = hashlib.sha256(text.encode()).hexdigest()
        return {"text": text, "sha256": digest}, {}, digest

    core.forensics = {"source": source}
    install_social(core)
    c = TestClient(core.app)
    for eid in ["owned-first", "owned-second"]:
        r = c.post("/api/social/import", json={"evidence_id": eid})
        assert r.status_code == 200 and r.json()["posts_imported"] == 1
        assert r.json()["live_collection"] is False
    observed = core.rows("SELECT * FROM social_observations WHERE post_id=?", ("1234",))
    assert len(observed) == 2
    latest = core.rows("SELECT * FROM social_posts WHERE id=?", ("1234",))[0]
    assert latest["source_evidence_id"] == "owned-second"
    assert "USER-SUPPLIED" in json.loads(latest["data"])["attribution"]
    feeds_before = len(core.rows("SELECT * FROM social_feeds"))
    for eid in ["invalid-js", "oversized"]:
        assert (
            c.post("/api/social/import", json={"evidence_id": eid}).status_code == 422
        )
    assert len(core.rows("SELECT * FROM social_feeds")) == feeds_before


def test_x_stream_routes_owned_rule_and_reconnects_without_normal_poll_delay(
    engine, monkeypatch, tmp_path
):
    """Synthetic official-format frames test rule isolation and raw preservation without live X claims."""
    import httpx
    import backend.social_watch as sw

    core, _, _ = engine
    install_social(core)
    c = TestClient(core.app)
    feed = c.post(
        "/api/social/feeds",
        json={
            "name": "Owned stream fixture",
            "query": "from:owned_fixture",
            "mode": "filtered_stream",
        },
    ).json()
    fid = feed["id"]
    captured = []

    def preserve(raw, *args):
        """Preserve actual synthetic response bytes for the ingestion boundary test."""
        eid = "FIXTURE-" + str(len(captured))
        (tmp_path / (eid + ".json")).write_bytes(raw)
        captured.append(raw)
        return eid

    core.preserve = preserve
    core.process = lambda eid: None
    frames = [
        {
            "data": {"id": "11", "text": "other application rule"},
            "matching_rules": [{"id": "other"}],
        },
        {
            "data": {"id": "12", "text": "owned rule frame"},
            "matching_rules": [{"id": "owned-rule"}],
        },
    ]

    def handler(request):
        """Return only explicitly synthetic X-formatted service responses."""
        if request.url.path.endswith("/rules"):
            assert request.method == "GET"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "owned-rule",
                            "tag": "sherlock:" + fid,
                            "value": "from:owned_fixture",
                        }
                    ]
                },
            )
        assert request.url.host == "api.x.com"
        return httpx.Response(
            200, content=("\n".join(json.dumps(x) for x in frames) + "\n").encode()
        )

    original_client = httpx.Client
    monkeypatch.setenv("X_BEARER_TOKEN", "owned-synthetic-test-token")
    monkeypatch.setattr(
        sw.httpx,
        "Client",
        lambda **kw: original_client(transport=httpx.MockTransport(handler), **kw),
    )
    result = c.post("/api/social/feeds/" + fid + "/poll", json={})
    assert result.status_code == 200 and result.json()["status"] == "COMPLETE"
    assert (
        result.json()["posts_received"] == 1
        and result.json()["other_rule_messages_ignored"] == 1
    )
    assert len(captured) == 1 and json.loads(captured[0]) == frames[1]
    assert [r["id"] for r in core.rows("SELECT id FROM social_posts")] == ["12"]
    due = core.rows("SELECT next_due FROM social_feeds WHERE id=?", (fid,))[0][
        "next_due"
    ]
    assert 0 <= due - time.time() <= 3
