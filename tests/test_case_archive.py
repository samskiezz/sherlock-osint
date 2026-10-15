"""Verify archives include real permitted bytes and explicitly omit unavailable sources."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile
import pytest
from fastapi import HTTPException
from backend.case_archive import build


def fixture(tmp_path):
    original = tmp_path / "originals"
    original.mkdir()
    raw = b"Author-created acceptance fixture. No external evidence assertions.\n"
    digest = hashlib.sha256(raw).hexdigest()
    p = original / digest
    p.write_bytes(raw)
    p.chmod(0o400)
    derivative = tmp_path / "derivatives" / "EV-fixture"
    derivative.mkdir(parents=True)
    text = derivative / "text.txt"
    text.write_bytes(raw)
    event = []
    core = SimpleNamespace(
        ROOT=tmp_path, MIN_FREE_BYTES=0, log=lambda *args: event.append(args)
    )
    e = {
        "id": "EV-fixture",
        "sha256": digest,
        "metadata": {
            "licence_review": {
                "redistributable": True,
                "original_sha256": digest,
                "licence": "CC0 test fixture",
                "basis": "Created for this isolated software acceptance test",
            },
            "derivative_hashes": {"text.txt": digest},
        },
    }
    return core, {"evidence": [e], "retrieval_queries": []}, raw, event


def test_archive_contains_original_bytes_derivatives_and_matching_hash_manifest(
    tmp_path,
):
    core, payload, raw, event = fixture(tmp_path)
    response = build(core, payload)
    try:
        with zipfile.ZipFile(response.path) as z:
            record = json.loads(z.read("included-originals.json"))[0]
            assert z.read(record["member"]) == raw
            assert z.read("derivatives/EV-fixture/text.txt") == raw
            assert not json.loads(z.read("original-omissions.json"))
            for line in z.read("SHA256SUMS").decode().splitlines():
                digest, member = line.split("  ", 1)
                assert hashlib.sha256(z.read(member)).hexdigest() == digest
            assert json.loads(z.read("manifest.json"))["retrieval_queries"] == []
        assert event[-1][0] == "case_archive_built"
    finally:
        Path(response.path).unlink(missing_ok=True)


@pytest.mark.parametrize(
    "problem", ["unreviewed", "different_review_hash", "missing", "tampered"]
)
def test_unreviewed_missing_or_damaged_files_are_never_fabricated(tmp_path, problem):
    core, payload, raw, event = fixture(tmp_path)
    e = payload["evidence"][0]
    path = tmp_path / "originals" / e["sha256"]
    if problem == "unreviewed":
        e["metadata"]["licence_review"] = {}
    elif problem == "different_review_hash":
        e["metadata"]["licence_review"]["original_sha256"] = "0" * 64
    elif problem == "missing":
        path.unlink()
    else:
        path.chmod(0o600)
        path.write_bytes(b"tampered bytes")
    response = build(core, payload)
    try:
        with zipfile.ZipFile(response.path) as z:
            assert not json.loads(z.read("included-originals.json"))
            assert json.loads(z.read("original-omissions.json"))
            assert not any(p.startswith("originals/") for p in z.namelist())
    finally:
        Path(response.path).unlink(missing_ok=True)
