import os, io, hashlib, json, importlib, time, zipfile
from pathlib import Path
import pytest, fitz
from PIL import Image
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def core(tmp_path_factory):
    os.environ["SHERLOCK_DATA"] = str(tmp_path_factory.mktemp("vault"))
    from backend import app as mod

    return mod


@pytest.fixture
def client(core):
    return TestClient(core.app)


def pdf_bytes():
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text(
        (40, 60), "The robotics team published this original technical record."
    )
    b = doc.tobytes()
    doc.close()
    return b


def test_import_hash_pdf_extraction_and_immutable_original(core, client):
    data = pdf_bytes()
    r = client.post(
        "/api/upload", files={"file": ("fixture.pdf", data, "application/pdf")}
    )
    assert r.status_code == 200
    e = r.json()
    assert e["status"] == "ORIGINAL VERIFIED"
    assert e["sha256"] == hashlib.sha256(data).hexdigest()
    assert "robotics team" in e["text"]
    assert e["metadata"]["page_count"] == 1
    original = core.ROOT / "originals" / e["sha256"]
    assert original.read_bytes() == data
    assert original.stat().st_mode & 0o222 == 0
    assert client.get(e["fileUrl"]).content == data
    assert client.get(e["previewUrl"]).headers["content-type"] == "image/png"


def test_image_real_pixels_metadata_thumbnail_ocr(core, client):
    im = Image.new("RGB", (100, 80), (23, 90, 130))
    out = io.BytesIO()
    im.save(out, format="PNG")
    r = client.post(
        "/api/upload", files={"file": ("fixture.png", out.getvalue(), "image/png")}
    )
    assert r.status_code == 200
    e = r.json()
    assert e["metadata"]["dimensions"] == [100, 80]
    assert len(e["metadata"]["histogram"]) == 768
    assert e["previewUrl"]
    assert e["sha256"] == hashlib.sha256(out.getvalue()).hexdigest()


def test_claim_requires_actual_acquired_passage(core, client):
    board = client.get("/api/boards/looking-glass").json()
    edge = board["edges"][0]
    edge["data"]["state"] = "DOCUMENTED"
    edge["data"]["evidence"] = []
    assert client.put("/api/boards/looking-glass", json=board).status_code == 422
    ev = next(
        e
        for e in client.get("/api/evidence").json()
        if e["fileUrl"]
        and e["mime"] == "application/pdf"
        and "The robotics team published this original technical record." in e["text"]
    )
    edge["data"]["evidence"] = [
        {"id": ev["id"], "quote": "a fabricated source passage"}
    ]
    assert client.put("/api/boards/looking-glass", json=board).status_code == 422
    edge["data"]["evidence"] = [
        {
            "id": ev["id"],
            "quote": "The robotics team published this original technical record.",
            "location": "Page 1",
        }
    ]
    assert client.put("/api/boards/looking-glass", json=board).status_code == 200


def test_layout_survives_reinitialize(core, client):
    b = client.get("/api/boards/looking-glass").json()
    b["nodes"][0]["position"] = {"x": 123, "y": 456}
    assert client.put("/api/boards/looking-glass", json=b).status_code == 200
    core.initialize()
    assert client.get("/api/boards/looking-glass").json()["nodes"][0]["position"] == {
        "x": 123,
        "y": 456,
    }


def test_search_returns_original_status(client):
    r = client.get("/api/search", params={"q": "robotics team"})
    assert r.status_code == 200
    assert any(h["evidence"]["fileUrl"] for h in r.json())


def test_cipher_records_control_attempts_and_no_authentication(client):
    r = client.post(
        "/api/cipher",
        json={
            "input": "436f6c6520416c6c656e",
            "method": "hex",
            "control": "52616e646f6d206e616d65",
        },
    ).json()
    assert r["output"] == "Cole Allen"
    assert r["control_output"] == "Random name"
    assert r["validation"] == "UNVALIDATED"
    assert r["attempt_number"] >= 1
    bad = client.post("/api/cipher", json={"input": "not hex", "method": "hex"})
    assert bad.status_code == 422


def test_ssrf_rejected(core):
    for url in [
        "http://127.0.0.1/test",
        "http://169.254.169.254/metadata",
        "file:///etc/passwd",
        "http://user:pass@example.com",
        "http://10.0.0.1",
    ]:
        with pytest.raises(ValueError):
            core.safe_url(url)


def test_export_declares_missing_originals(client):
    r = client.get("/api/export/zip")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert json.loads(z.read("original-omissions.json"))
        assert "SHA256SUMS" in z.namelist()
        assert "manifest.json" in z.namelist()


def test_scheduler_persists_pause_resume_and_deduplicates_discovery(
    core, client, monkeypatch
):
    r = client.post(
        "/api/watches",
        json={
            "name": "Literature watch",
            "mode": "crossref",
            "target": "nickel superalloy",
            "interval_minutes": 5,
        },
    )
    assert r.status_code == 200
    wid = r.json()["id"]
    assert client.post(f"/api/watches/{wid}/pause").status_code == 200
    assert (
        next(w for w in client.get("/api/watches").json()["watches"] if w["id"] == wid)[
            "enabled"
        ]
        == 0
    )
    assert client.post(f"/api/watches/{wid}/resume").status_code == 200
    core.initialize()
    assert core.rows("SELECT * FROM watches WHERE id=?", (wid,))
    monkeypatch.setattr(core, "robots_allowed", lambda u: None)
    monkeypatch.setattr(core, "safe_url", lambda u: None)
    monkeypatch.setattr(
        core,
        "fetch",
        lambda u: (
            json.dumps(
                {
                    "message": {
                        "items": [
                            {
                                "URL": "https://doi.org/10.123/test",
                                "title": ["Nickel superalloy technical original"],
                            }
                        ]
                    }
                }
            ).encode(),
            u,
            {},
            200,
        ),
    )
    core.scheduler["tick"]()
    assert len(core.rows("SELECT * FROM discovery WHERE watch_id=?", (wid,))) == 1
    client.post(f"/api/watches/{wid}/run")
    core.scheduler["tick"]()
    assert len(core.rows("SELECT * FROM discovery WHERE watch_id=?", (wid,))) == 1
    runs = core.rows(
        "SELECT * FROM watch_runs WHERE watch_id=? ORDER BY started", (wid,)
    )
    assert runs[0]["queued"] == 1
    assert runs[1]["queued"] == 0


def test_secondary_summary_not_used_as_original_answer(client):
    r = client.post("/api/investigate", json={"question": "quantum hypothesis"}).json()
    assert r["sources"] == []
    assert r["unsupported_notes"] > 0
    assert "No factual conclusion" in r["conclusion"]


def test_untrusted_html_is_download_only(client):
    r = client.post(
        "/api/upload",
        files={
            "file": (
                "page.html",
                b"<html><script>alert(1)</script><p>public record</p></html>",
                "text/html",
            )
        },
    )
    e = r.json()
    original = client.get(e["fileUrl"])
    assert original.headers["content-type"] == "application/octet-stream"
    assert original.headers["content-disposition"] == "attachment"
    assert "sandbox" in original.headers["content-security-policy"]
    assert "alert" not in e["text"]


def test_duplicate_download_keeps_id_and_records_retrieval(core, client):
    data = pdf_bytes()
    first = client.post(
        "/api/upload", files={"file": ("one.pdf", data, "application/pdf")}
    ).json()
    second = client.post(
        "/api/upload", files={"file": ("two.pdf", data, "application/pdf")}
    ).json()
    assert first["id"] == second["id"]
    assert second["metadata"]["subsequent_acquisitions"]
    assert first["sha256"] == second["sha256"]


def test_scheduler_failure_is_visible_and_retries_later(core, client, monkeypatch):
    r = client.post(
        "/api/watches",
        json={
            "name": "Failure watch",
            "mode": "crossref",
            "target": "test failure",
            "interval_minutes": 60,
        },
    ).json()
    wid = r["id"]
    monkeypatch.setattr(core, "robots_allowed", lambda u: None)

    def broken(url):
        raise RuntimeError("fixture source unavailable")

    monkeypatch.setattr(core, "fetch", broken)
    core.scheduler["tick"]()
    w = core.rows("SELECT * FROM watches WHERE id=?", (wid,))[0]
    assert w["last_error"] == "fixture source unavailable"
    assert time.time() < w["next_run"] <= time.time() + 301
    assert (
        core.rows("SELECT * FROM watch_runs WHERE watch_id=?", (wid,))[0]["status"]
        == "FAILED"
    )


def test_static_code_processor_never_executes_download(client, tmp_path):
    sentinel = tmp_path / "must_not_exist"
    source = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n".encode()
    e = client.post(
        "/api/upload", files={"file": ("untrusted.py", source, "text/plain")}
    ).json()
    assert e["metadata"]["static_only"]
    assert "write_text" in e["text"]
    assert not sentinel.exists()


def test_content_type_mismatch_and_cross_origin_writes_rejected(client):
    r = client.post(
        "/api/upload",
        files={"file": ("fake.pdf", b"<html>Not a PDF</html>", "application/pdf")},
    )
    assert r.status_code == 500 or r.status_code == 422
    r = client.post(
        "/api/cipher",
        json={"input": "4142", "method": "hex"},
        headers={"Origin": "https://unrelated.example"},
    )
    assert r.status_code == 403


def test_video_static_probe_and_keyframe(client, tmp_path):
    import shutil, subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not installed")
    fixture = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x120:d=1",
            "-c:v",
            "mpeg4",
            str(fixture),
        ],
        check=True,
        capture_output=True,
    )
    e = client.post(
        "/api/upload",
        files={"file": ("fixture.mp4", fixture.read_bytes(), "video/mp4")},
    ).json()
    assert e["status"] == "ORIGINAL VERIFIED"
    assert float(e["metadata"]["media_probe"]["format"]["duration"]) > 0
    assert e["previewUrl"]
    assert e["metadata"]["transcript_status"].startswith("Not generated")
