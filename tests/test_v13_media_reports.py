"""General media coverage must preserve negatives, independent inputs and paging."""

# ruff: noqa: F811
import json
import pytest
from fastapi.testclient import TestClient
from backend.media_reports import build_report, install
from test_automation_controller import engine  # noqa: F401


def test_different_images_have_independent_negative_and_positive_receipts():
    """A broad scanner cannot require an artwork, a name, or a known target to report."""
    comparison = {
        "id": "R1",
        "results": [],
        "compared": 8,
        "unavailable": [],
        "corpus_limit": 500,
        "corpus_truncated": False,
        "scope": "Stored originals",
    }
    first = build_report(
        {
            "id": "A",
            "title": "Uncaptioned meme",
            "url": "https://example.org/a.jpg",
            "sha256": "a",
            "text": "",
        },
        {"panel_analysis": {"status": "NO_MIXTURE_DETECTED"}},
        comparison,
        {},
    )
    assert first["assessment"] == "NO_MATCH_IN_TESTED_CORPUS"
    assert first["checks"][1]["status"] == "NO_TEXT_EXTRACTED"
    assert first["evidence_id"] == "A" and first["coverage"]["compared"] == 8
    second = build_report(
        {
            "id": "B",
            "title": "Different post",
            "url": "https://other.example/b.png",
            "sha256": "b",
            "text": "Caption text",
        },
        {
            "panel_analysis": {
                "status": "MIXTURE_SEQUENCE_DETECTED",
                "pairs_attempted": 6,
            }
        },
        comparison,
        {"image_forensics": {"anomaly_indicators": [{"indicator": "NO EXIF"}]}},
    )
    assert second["assessment"] == "REVIEW_LEADS"
    assert second["source_domain"] != first["source_domain"]
    assert second["checks"][1]["status"] == "TEXT_EXTRACTED"
    # An EXIF indicator alone must never produce a hidden-message finding.
    third = build_report(
        {
            "id": "C",
            "title": "Photo",
            "url": "https://example.org/c.jpg",
            "sha256": "c",
        },
        {},
        comparison,
        {"image_forensics": {"anomaly_indicators": [{"indicator": "NO EXIF"}]}},
    )
    assert third["assessment"] == "NO_MATCH_IN_TESTED_CORPUS"


def test_exact_reuse_and_geometric_candidates_are_distinct():
    """Hash identity and heuristic matches must retain different evidence states."""
    ref = {
        "id": "A",
        "title": "Owned",
        "url": "https://example.org/a",
        "sha256": "same",
    }
    results = [
        {
            "evidence_id": eid,
            "title": eid,
            "original_sha256": sha,
            "ransac_inliers": n,
            "hash_distances": {"phash": d},
        }
        for eid, sha, n, d in [
            ("B", "same", 0, 0),
            ("C", "other", 14, 25),
            ("D", "different", 0, 5),
            ("E", "unrelated", 0, 50),
        ]
    ]
    report = build_report(ref, {}, {"id": "R", "results": results, "compared": 4}, {})
    assert [lead["kind"] for lead in report["similarity_leads"]] == [
        "EXACT_BYTES",
        "GEOMETRIC_REUSE_CANDIDATE",
        "PERCEPTUAL_SIMILARITY_CANDIDATE",
    ]


def test_portfolio_includes_pending_failed_negative_and_older_images(engine):
    """Paging must expose the entire corpus, not only positive findings or newest 500 inputs."""
    core, _, _ = engine
    core.execute(
        "CREATE TABLE evidence(id TEXT,title TEXT,url TEXT,sha256 TEXT,created TEXT,path TEXT,mime TEXT)"
    )
    core.execute(
        "CREATE TABLE visual_review_state(evidence_id TEXT,status TEXT,error TEXT)"
    )
    reports = install(core)
    for i in range(503):
        core.execute(
            "INSERT INTO evidence VALUES(?,?,?,?,?,?,?)",
            (
                str(i),
                f"Image {i}",
                "https://example.org/a",
                str(i),
                f"{i:04}",
                "fixture",
                "image/png",
            ),
        )
    core.execute(
        "INSERT INTO visual_review_state VALUES('502','FAILED','Fixture failure')"
    )
    core.execute(
        "INSERT INTO media_reports VALUES(?,?,?)",
        (
            "501",
            core.now(),
            json.dumps(
                {"original_sha256": "501", "assessment": "NO_MATCH_IN_TESTED_CORPUS"}
            ),
        ),
    )
    c = TestClient(core.app)
    first = c.get("/api/media/reports?limit=2").json()
    assert first["total"] == 503 and first["has_more"]
    assert first["items"][0]["status"] == "FAILED"
    assert first["items"][1]["report"]["assessment"] == "NO_MATCH_IN_TESTED_CORPUS"
    last = c.get("/api/media/reports?limit=10&offset=500").json()
    assert len(last["items"]) == 3 and not last["has_more"]
    assert all(x["status"] == "PENDING" for x in last["items"])
    assert c.get("/api/media/reports?limit=101").status_code == 422
    assert c.get("/api/media/reports?offset=-1").status_code == 422
    assert len(core.rows("SELECT * FROM media_reports")) == 1
    core.execute("UPDATE evidence SET sha256='changed' WHERE id='501'")
    stale = reports["portfolio"](2)["items"][1]
    assert stale["status"] == "STALE" and stale["report"] is None


def test_rss_and_atom_media_keep_post_provenance_and_relative_urls():
    """Recurring feed discovery can acquire images instead of merely listing post URLs."""
    from backend.discovery import feed_links

    rss = b"""<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>Owned meme</title><link>/post/one</link><media:content url="/img/one.jpg" type="image/jpeg"/><media:thumbnail url="/img/thumb.png"/><enclosure url="/private.bin" type="application/octet-stream"/></item></channel></rss>"""
    hits = feed_links(rss, "https://example.org/feed", include_images=True)
    images = [h for h in hits if h["kind"] == "image"]
    assert len(images) == 2
    assert {h["url"] for h in images} == {
        "https://example.org/img/one.jpg",
        "https://example.org/img/thumb.png",
    }
    assert all(h["parent_post_url"] == "https://example.org/post/one" for h in images)
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Owned photo</title><link href="/post/two"/><link rel="enclosure" type="image/png" href="/img/two.png"/></entry></feed>"""
    image = next(
        h
        for h in feed_links(atom, "https://example.org/feed", True)
        if h["kind"] == "image"
    )
    assert image["parent_post_url"].endswith("/post/two")
    assert image["url"].endswith("/img/two.png")


def test_media_origins_preserve_multiple_posts_without_duplicate_registration(engine):
    """The same image can have independent feed origins without being conflated with one case."""
    core, _, _ = engine
    media = install(core)
    context = {
        "kind": "X_PLATFORM_MEDIA_ATTACHMENT",
        "post_url": "https://x.com/i/web/status/123",
        "parent_evidence_id": "OWNED-RESPONSE-A",
    }
    media["register"]("https://example.org/image.jpg", context)
    media["register"]("https://example.org/image.jpg", context)
    media["register"](
        "https://example.org/image.jpg",
        {**context, "post_url": "https://x.com/i/web/status/124"},
    )
    assert len(core.rows("SELECT * FROM media_origins")) == 2


def test_nasa_library_discovery_preserves_catalogue_and_marks_rendition(monkeypatch):
    """A documented multi-image API returns separate source-bound acquisition leads."""
    from backend import discovery
    from types import SimpleNamespace

    captured = []
    payload = {
        "collection": {
            "items": [
                {
                    "data": [
                        {
                            "title": "Owned optical illusion fixture",
                            "nasa_id": "OWNED",
                            "date_created": "2000-01-01",
                        }
                    ],
                    "links": [
                        {
                            "render": "image",
                            "href": "https://images-assets.nasa.gov/image/OWNED/thumb.jpg",
                        }
                    ],
                }
            ]
        }
    }

    def preserve(core, url, title):
        """Use an explicitly owned catalogue fixture; live acquisition is checked separately."""
        captured.append(url)
        return "OWNED-CATALOGUE", json.dumps(payload).encode(), url

    monkeypatch.setattr(discovery, "preserve_response", preserve)
    result = discovery.search(
        SimpleNamespace(validate_url=lambda url: None),
        "nasa_images",
        "optical illusion",
        limit=3,
    )
    assert captured[0].startswith("https://images-api.nasa.gov/search?")
    assert "page_size=3" in captured[0]
    assert result["hits"][0]["catalogue_id"] == "OWNED-CATALOGUE"
    assert result["hits"][0]["kind"] == "image"
    assert result["hits"][0]["catalogue_date_created_reported"] == "2000-01-01"
    assert "publication_date_reported" not in result["hits"][0]
    assert "not a camera original" in result["hits"][0]["attribution"]
    assert result["hits"][0]["status"] == "DISCOVERED · ORIGINAL NOT YET ACQUIRED"

    payload["collection"]["items"].append(
        {
            "data": [{"title": "Hybrid Wing Body Particle Image Velocimetry"}],
            "links": [
                {
                    "render": "image",
                    "href": "https://images-assets.nasa.gov/aircraft.jpg",
                }
            ],
        }
    )
    off_topic = discovery.search(
        SimpleNamespace(validate_url=lambda url: None),
        "nasa_images",
        "hybrid image",
        limit=3,
    )
    assert off_topic["hits"] == []


def test_background_worker_reviews_new_arrivals_without_manual_requests(engine):
    """Two independent arrivals are dispatched by the running worker without a UI action."""
    import time
    from backend.visual_watch import install as install_watch

    core, _, _ = engine
    core.execute(
        "CREATE TABLE evidence(id TEXT,path TEXT,mime TEXT,created TEXT,sha256 TEXT)"
    )
    core.execute(
        "INSERT INTO evidence VALUES('FIRST','owned','image/png','1','hash-a')"
    )
    core.autopilot = {"settings": lambda: {"enabled": True}}
    reviewed = []
    core.visual = {
        "source": lambda eid: ({}, {"version": "0.12.0", "panel_analysis": {}}),
        "search": lambda eid, limit: reviewed.append(eid)
        or {"id": "OWNED-COMPARISON", "explanation_ids": []},
    }
    core.process = lambda eid: pytest.fail("Current image should not be reparsed")
    install_watch(core)
    try:
        with TestClient(core.app):
            deadline = time.monotonic() + 8
            while "FIRST" not in reviewed and time.monotonic() < deadline:
                time.sleep(0.1)
            assert "FIRST" in reviewed
            core.execute(
                "INSERT INTO evidence VALUES('SECOND','owned','image/jpeg','2','hash-b')"
            )
            deadline = time.monotonic() + 8
            while "SECOND" not in reviewed and time.monotonic() < deadline:
                time.sleep(0.1)
            assert "SECOND" in reviewed
            assert {
                r["evidence_id"]
                for r in core.rows(
                    "SELECT * FROM visual_review_state WHERE status='COMPLETE'"
                )
            } == {"FIRST", "SECOND"}
    finally:
        core.stopping.set()


def test_source_balancing_prevents_one_download_batch_hiding_other_feeds(engine):
    """Six newest images from one publisher cannot displace all other watched sources."""
    core, _, _ = engine
    core.execute(
        "CREATE TABLE evidence(id TEXT,title TEXT,url TEXT,sha256 TEXT,created TEXT,path TEXT,mime TEXT)"
    )
    core.execute(
        "CREATE TABLE visual_review_state(evidence_id TEXT,status TEXT,error TEXT)"
    )
    reports = install(core)
    for i in range(6):
        core.execute(
            "INSERT INTO evidence VALUES(?,?,?,?,?,?,?)",
            (
                f"A{i}",
                "Fixture",
                f"https://a.example/{i}.jpg",
                str(i),
                str(10 + i),
                "owned",
                "image/jpeg",
            ),
        )
    core.execute(
        "INSERT INTO evidence VALUES('B','Other feed','https://b.example/1.jpg','b','1','owned','image/jpeg')"
    )
    core.execute(
        "INSERT INTO evidence VALUES('C','Third feed','https://c.example/1.jpg','c','2','owned','image/jpeg')"
    )
    first = reports["portfolio"](3)["items"]
    assert {x["source_domain"] for x in first} == {
        "a.example",
        "b.example",
        "c.example",
    }
