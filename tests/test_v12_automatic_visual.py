"""Owned holdout images, real isolated processing, background scheduling and read-only results."""

# Imported pytest fixture names are also test parameters.
# ruff: noqa: F811
import hashlib
import time
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from backend.sandbox import run
from backend.visual_explanation import explain
from backend.visual_watch import install as install_watch
from backend.case_overview import install as install_overview
from test_automation_controller import engine  # noqa:F401


@pytest.fixture(scope="module")
def images(tmp_path_factory):
    """Create independent synthetic known blends and unrelated controls; process real bytes in Docker."""
    folder = tmp_path_factory.mktemp("owned-v12-panels")
    rng = np.random.default_rng(123987)
    endpoints = []
    for k in range(2):
        im = Image.new("RGB", (256, 256), (35 + 70 * k, 70, 155 - 50 * k))
        d = ImageDraw.Draw(im)
        for i in range(80):
            x, y = map(int, rng.integers(3, 225, 2))
            color = tuple(map(int, rng.integers(15, 230, 3)))
            d.rectangle(
                (x, y, x + int(rng.integers(10, 25)), y + int(rng.integers(10, 25))),
                fill=color,
            )
            d.text((x, y), str(i), fill="white")
        endpoints.append(im)

    def collage(parts):
        """Use equal panels without dividers to test the general quadrant candidate, not a specific case layout."""
        im = Image.new("RGB", (512, 512))
        for p, pos in zip(parts, [(0, 0), (256, 0), (0, 256), (256, 256)]):
            im.paste(p, pos)
        return im

    a, b = endpoints
    fixtures = {
        "photo": a,
        "anchor": b,
        "blend": collage([a, Image.blend(a, b, 0.31), Image.blend(a, b, 0.64), b]),
        "negative": collage(
            [
                Image.fromarray(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8))
                for _ in range(4)
            ]
        ),
        "flat": collage([a, a, a, a]),
    }
    result = {}
    for name, im in fixtures.items():
        original = folder / (name + ".png")
        im.save(original)
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        out = folder / (name + "-derivatives")
        value = run(original, "image/png", digest, out)
        assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
        result[name] = {
            "features": value["metadata"]["visual_features"],
            "output": out,
            "sha256": digest,
        }
    return result


def test_unseen_controlled_blend_is_detected_and_reconstructed(images):
    """Known unseen mixing weights must be recovered; all six endpoint pairs remain recorded."""
    a = images["blend"]["features"]["panel_analysis"]
    assert a["status"] == "MIXTURE_SEQUENCE_DETECTED"
    assert a["pairs_attempted"] == 6 and len(a["endpoint_pair_trials"]) == 6
    assert a["best"]["endpoints"] == [0, 3]
    weights = [p["endpoint_b_weight"] for p in a["best"]["panels"]]
    assert weights == pytest.approx([0, 0.31, 0.64, 1], abs=0.06)
    for i in range(4):
        assert (images["blend"]["output"] / f"visual-panel-{i}.png").is_file()
        assert (images["blend"]["output"] / f"visual-fit-{i}.png").is_file()
        assert (images["blend"]["output"] / f"visual-residual-{i}.png").is_file()


def test_unrelated_and_repeated_images_do_not_become_overlay_findings(images):
    """Negative controls cannot be converted into a hidden-image or person identification."""
    assert (
        images["negative"]["features"]["panel_analysis"]["status"]
        == "NO_MIXTURE_DETECTED"
    )
    assert (
        images["flat"]["features"]["panel_analysis"]["status"] == "NO_MIXTURE_DETECTED"
    )


def test_identity_requires_linked_acquired_publisher_description(images):
    """The endpoint is matched geometrically; its name is separately attributed to an exact source."""
    anchor = {
        "id": "OWNED-ART",
        "title": "Test Artwork · owned fixture",
        "url": "https://example.org/art.png",
        "sha256": images["anchor"]["sha256"],
    }
    composite = {
        "id": "OWNED-MIX",
        "title": "Owned collage",
        "url": "https://example.org/composite.png",
        "sha256": images["blend"]["sha256"],
    }
    text = "The digital image is titled Test Artwork. President Sample Person is described in the source photograph. These are synthetic fixture names."
    digest = hashlib.sha256(text.encode()).hexdigest()
    page = {
        "id": "OWNED-CONTEXT",
        "title": "Owned caption fixture",
        "url": "https://example.org/report",
        "sha256": digest,
        "text": text,
    }
    core = SimpleNamespace(
        rows=lambda *args: [{"id": page["id"]}],
        forensics={
            "source": lambda eid: (
                page,
                {"media": [{"href": "/composite.png"}]},
                digest,
            )
        },
    )
    f = explain(
        core,
        anchor,
        images["anchor"]["features"],
        composite,
        images["blend"]["features"],
    )
    assert f is not None and f["subject_name_reported"] == "Sample Person"
    assert f["matched_artwork_panel"] == 3 and f["photo_candidate_panel"] == 0
    citation = f["subject_attribution"]
    assert text[citation["text_start"] : citation["text_end"]] == citation["quote"]
    assert "not independent biometric" in citation["attribution"]
    core.forensics = {
        "source": lambda eid: (page, {"media": [{"href": "/unrelated.png"}]}, digest)
    }
    general = explain(
        core,
        anchor,
        images["anchor"]["features"],
        composite,
        images["blend"]["features"],
    )
    assert general is not None and general["subject_name_reported"] is None
    assert not general["reference_is_artwork"] and general["sources"] == []
    # Uncaptioned geometric matches remain generic: no artwork or person inferred.
    assert general["reference_label"] == "Matched reference"


def test_visual_review_starts_without_browser_post_or_tool_click(engine):
    """The server startup worker alone discovers and reviews an acquired-image fixture."""
    core, _, _ = engine
    core.execute(
        "CREATE TABLE evidence(id TEXT,path TEXT,mime TEXT,created TEXT,sha256 TEXT)"
    )
    core.execute(
        "INSERT INTO evidence VALUES(?,?,?,?,?)",
        (
            "OWNED-IMAGE",
            "owned-fixture",
            "image/png",
            core.now(),
            "owned-fixture-digest",
        ),
    )
    core.autopilot = {"settings": lambda: {"enabled": True}}
    calls = []
    processed = []

    def old_source(eid):
        """Simulate a pre-upgrade image that needs automatic isolated reprocessing."""
        if not processed:
            raise ValueError("Image requires reprocessing")
        return {}, {
            "version": "0.12.0",
            "panel_analysis": {"status": "NO_MIXTURE_DETECTED"},
        }

    core.process = lambda eid: processed.append(eid)
    core.visual = {
        "source": old_source,
        "search": lambda eid, limit: (
            calls.append(eid) or {"id": "OWNED-VISUAL", "explanation_ids": []}
        ),
    }
    install_watch(core)
    try:
        with TestClient(core.app):
            deadline = time.time() + 9
            while not calls and time.time() < deadline:
                time.sleep(0.1)
            assert calls == ["OWNED-IMAGE"]
            assert processed == ["OWNED-IMAGE"]
            rows = core.rows("SELECT * FROM visual_review_state")
            assert rows[0]["status"] == "COMPLETE" and rows[0]["attempts"] == 1
    finally:
        core.stopping.set()


def test_case_overview_is_read_only_and_does_not_launch_analysis(engine):
    """Opening or refreshing the home page must not enqueue work or require a manual action."""
    core, _, _ = engine
    core.execute("CREATE TABLE evidence(id TEXT,title TEXT,path TEXT,size INTEGER)")
    core.execute(
        "INSERT INTO evidence VALUES(?,?,?,?)",
        ("OWNED", "Owned original", "owned-fixture", 120),
    )
    core.execute(
        "CREATE TABLE autopilot_dispatch(evidence_id TEXT,created TEXT,run_id TEXT)"
    )
    core.execute(
        "CREATE TABLE research_campaigns(id TEXT,name TEXT,settings TEXT,created TEXT,enabled INTEGER,next_run REAL)"
    )
    core.execute(
        "INSERT INTO research_campaigns(enabled,next_run,settings) VALUES(1,123,'{}')"
    )
    core.execute("CREATE TABLE jobs(status TEXT)")
    core.execute("CREATE TABLE visual_review_state(status TEXT)")
    core.autopilot = {"settings": lambda: {"enabled": True}}
    core.visual = {"explanations": lambda: []}
    install_overview(core)
    c = TestClient(core.app)
    for _ in range(2):
        r = c.get("/api/case/overview")
        assert r.status_code == 200
        assert (
            r.json()["mode"] == "AUTOMATIC"
            and r.json()["originals"] == 1
            and r.json()["watches"] == 1
        )
    assert not core.rows("SELECT * FROM automation_runs")


def test_photo_endpoint_matches_acquired_publisher_image_and_exact_caption(images):
    """Recover a published identity through actual pixel correspondence plus a literal caption."""
    from backend.visual_explanation import match_published_photo

    text = "President Sample Person raises a hand in this synthetic photograph."
    digest = hashlib.sha256(text.encode()).hexdigest()
    page = {
        "id": "OWNED-PUBLISHER",
        "title": "Owned photo publisher",
        "url": "https://example.org/gallery",
        "text": text,
        "sha256": digest,
    }
    photo = {
        "id": "OWNED-PHOTO",
        "title": "Owned photograph",
        "url": "https://example.org/photo.png",
        "sha256": images["photo"]["sha256"],
    }
    core = SimpleNamespace(
        rows=lambda *args: [{"id": "OWNED-PHOTO"}],
        visual={"source": lambda eid: (photo, images["photo"]["features"])},
    )
    panels = images["blend"]["features"]["panel_analysis"]["panels"]
    p = next(x for x in panels if x["panel"] == 0)
    result = match_published_photo(
        core,
        {"id": "OWNED-COMPOSITE"},
        images["blend"]["features"],
        p,
        [(page, {"media": [{"href": "/photo.png", "caption": text}]}, digest)],
        set(),
    )
    assert result is not None and result["geometry"]["ransac_inliers"] >= 12
    assert result["citation"]["subject_name_reported"] == "Sample Person"
    assert (
        result["citation"]["quote"] == text
        and result["original_sha256"] == photo["sha256"]
    )
    assert (
        match_published_photo(
            core,
            {"id": "OWNED-COMPOSITE"},
            images["blend"]["features"],
            p,
            [
                (
                    page,
                    {"media": [{"href": "/other-photo.png", "caption": text}]},
                    digest,
                )
            ],
            set(),
        )
        is None
    )

    # Generic publisher captions work without any named person or artwork.
    caption = "An owned geometric reference photographed for this test."
    generic_page = {**page, "text": caption}
    generic_digest = hashlib.sha256(caption.encode()).hexdigest()
    generic_page["sha256"] = generic_digest
    generic = match_published_photo(
        core,
        {"id": "OWNED-COMPOSITE"},
        images["blend"]["features"],
        p,
        [
            (
                generic_page,
                {"media": [{"href": "/photo.png", "caption": caption}]},
                generic_digest,
            )
        ],
        set(),
    )
    assert generic is not None and generic["caption"] == caption
    assert generic["citation"]["subject_name_reported"] is None


def test_processor_admission_is_shared_across_independent_processes(tmp_path):
    """Three real processes may overlap only two parser reservations, independent of thread limits."""
    import subprocess
    import sys
    from pathlib import Path

    directory = tmp_path / "shared-admission"
    program = """import sys,time,json
from types import SimpleNamespace
from backend import sandbox
sandbox.shutil.disk_usage=lambda p:SimpleNamespace(free=40*1024**3)
with sandbox.processing_admission(timeout=8,directory=sys.argv[1]):
 print(json.dumps({'phase':'enter','time':time.time()}),flush=True)
 time.sleep(.7)
 print(json.dumps({'phase':'exit','time':time.time()}),flush=True)
"""
    ps = [
        subprocess.Popen(
            [sys.executable, "-c", program, str(directory)],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(3)
    ]
    import json

    events = []
    for p in ps:
        stdout, stderr = p.communicate(timeout=12)
        assert p.returncode == 0, stderr
        events.extend(json.loads(x) for x in stdout.splitlines())
    events.sort(key=lambda e: e["time"])
    count = peak = 0
    for e in events:
        count += 1 if e["phase"] == "enter" else -1
        peak = max(peak, count)
        assert count <= 2
    assert peak == 2 and count == 0


def test_processor_storage_guard_creates_no_container_when_disk_is_low(
    tmp_path, monkeypatch
):
    """A low-space reservation fails before Docker creation and releases every kernel lock."""
    from backend import sandbox

    monkeypatch.setattr(sandbox.shutil, "disk_usage", lambda p: SimpleNamespace(free=0))
    with pytest.raises(sandbox.SandboxError, match="safe disk headroom"):
        with sandbox.processing_admission(timeout=0.01, directory=tmp_path / "slots"):
            pytest.fail("Low disk must never admit a processor")
    monkeypatch.setattr(
        sandbox.shutil, "disk_usage", lambda p: SimpleNamespace(free=40 * 1024**3)
    )
    with sandbox.processing_admission(timeout=1, directory=tmp_path / "slots"):
        pass


def test_supervisor_retains_control_when_status_writes_fail(tmp_path):
    """A disk-full status write and a truncated PID file cannot crash the service supervisor."""
    from scripts.run_platform import persist, read_pid

    class FullDisk:
        """Reproduce an ENOSPC filesystem write without filling any real volume."""

        def write_text(self, content):
            """Fail exactly as the resource incident did."""
            raise OSError(28, "No space left on device")

    assert persist(FullDisk(), "owned status") is False
    pid = tmp_path / "pid"
    pid.write_text("")
    assert read_pid(pid) == 0
    pid.write_text("123")
    assert read_pid(pid) == 123


def test_timed_out_container_creation_still_attempts_owned_cleanup(
    tmp_path, monkeypatch
):
    """The resource failure must not leave a created container outside the cleanup path."""
    from backend import sandbox

    original = tmp_path / "owned.txt"
    original.write_text("owned static fixture")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    calls = []

    def command(args, timeout=15):
        """Simulate a CLI timeout after Docker has accepted the creation request."""
        calls.append((args, timeout))
        if args[0] == "create":
            raise sandbox.SandboxError("Synthetic create timeout")
        return ""

    monkeypatch.setattr(sandbox, "command", command)
    with pytest.raises(sandbox.SandboxError, match="Synthetic create timeout"):
        sandbox._run(original, "text/plain", digest, tmp_path / "derivative")
    assert calls[0][0][0] == "create" and calls[0][1] == 45
    assert calls[-1][0][:2] == ["rm", "--force"]
    assert calls[-1][0][-1] == calls[0][0][calls[0][0].index("--name") + 1]
