import io
import json
import hashlib
import os
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from backend.cryptanalysis import transform, screen, statistics, METHODS


@pytest.mark.parametrize(
    "method,value,params,expected",
    [
        ("hex", "436f6c6520416c6c656e", {}, "Cole Allen"),
        ("base32", "JBSWY3DP", {}, "Hello"),
        ("base64", "SGVsbG8=", {}, "Hello"),
        ("binary", "01001000 01101001", {}, "Hi"),
        ("octal", "110 151", {}, "Hi"),
        ("decimal", "72 105", {}, "Hi"),
        ("vigenere", "LXFOPVEFRNHR", {"key": "LEMON"}, "ATTACKATDAWN"),
        (
            "beaufort",
            "CKMPVCPVWPIWUJOGIUAPVWRIWUUK",
            {"key": "FORTIFICATION"},
            "DEFENDTHEEASTWALLOFTHECASTLE",
        ),
        ("affine", "IHHWVCSWFRCP", {"a": 5, "b": 8}, "AFFINECIPHER"),
        (
            "rail_fence",
            "WECRLTEERDSOEEFEAOCAIVDEN",
            {"rails": 3},
            "WEAREDISCOVEREDFLEEATONCE",
        ),
        (
            "columnar",
            "EVLNEACDTKESEAQROFOJDEECWIREE",
            {"key": "ZEBRAS"},
            "WEAREDISCOVEREDFLEEATONCEQKJE",
        ),
        ("morse", "... --- ...", {}, "SOS"),
        ("polybius", "23 15 31 31 34", {}, "HELLO"),
        ("bacon", "AABBB AABAA ABABB ABABB ABBBA", {}, "HELLO"),
        ("a1z26", "8 5 12 12 15", {}, "HELLO"),
        ("atbash", "SVOOL", {}, "HELLO"),
        ("xor", "030e070704", {"key": "K"}, "HELLO"),
        ("unicode_escape", r"caf\u00e9", {}, "café"),
        ("nfkc", "ＡＢＣ", {}, "ABC"),
        ("line_initials", "A test\nB test\nC test", {}, "ABC"),
    ],
)
def test_known_vectors(method, value, params, expected):
    assert transform(value, method, params) == expected


def test_scrabble_blanks_exact_rack_and_custom_dictionary():
    hits = json.loads(
        transform(
            "liste?",
            "scrabble",
            {"exact": True, "dictionary": "listen silent enlist cat zzzzz"},
        )
    )
    assert {x["word"] for x in hits} == {"listen", "silent", "enlist"}
    assert all(x["tile_score"] == 5 and x["blank_tiles_used"] == 1 for x in hits)
    assert len(METHODS) == 52


def test_negative_controls_and_failed_attempts_are_preserved():
    result = screen("436f6c6520416c6c656e", 42)
    assert result == screen("436f6c6520416c6c656e", 42)
    assert result["rule_count"] == 51
    assert len(result["attempts"]) == 51
    assert any(a["status"] == "FAILED" for a in result["attempts"])
    assert all(
        a["adjusted_p"] is None or a["adjusted_p"] == 1
        for a in result["attempts"]
        if a["status"] == "OUTPUT"
    )
    assert result["validation"] == "UNVALIDATED"
    assert (
        next(x for x in result["attempts"] if x["method"] == "hex")["output"]
        == "Cole Allen"
    )
    assert statistics("ab\u202ec")["unicode_controls"][0]["codepoint"] == "U+202E"


@pytest.fixture(scope="module")
def core(tmp_path_factory):
    os.environ["SHERLOCK_DATA"] = str(tmp_path_factory.mktemp("forensic-vault"))
    from backend import app

    return app


def test_isolated_image_views_original_integrity_and_persistent_screen(core):
    client = TestClient(core.app)
    im = Image.new("RGB", (96, 64), (31, 90, 130))
    out = io.BytesIO()
    im.save(out, format="PNG")
    original = out.getvalue()
    r = client.post(
        "/api/upload", files={"file": ("diagnostic.png", original, "image/png")}
    )
    assert r.status_code == 200, r.text
    e = r.json()
    meta = e["metadata"]
    eid = e["id"]
    assert meta["image_forensics"]["state"] == "INDICATORS ONLY"
    assert meta["image_forensics"]["lsb"]["channels"]["red"]["one_fraction"] == 1
    assert (
        len(meta["image_forensics"]["jpeg_residual"]["benign_recompression_controls"])
        == 3
    )
    assert meta["sandbox"]["network"] == "none"
    for view in ("red", "green", "blue", "lsb", "ela"):
        response = client.get(f"/api/evidence/{eid}/diagnostic/{view}")
        assert response.status_code == 200, response.text
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert (
            hashlib.sha256(response.content).hexdigest()
            == meta["derivative_hashes"][view + ".png"]
        )
    assert client.get(f"/api/evidence/{eid}/diagnostic/unknown").status_code == 404
    assert client.get(e["fileUrl"]).content == original
    first = client.post(f"/api/forensics/{eid}/screen").json()
    second = client.post(f"/api/forensics/{eid}/screen").json()
    assert first["id"] == second["id"]
    core.execute(
        "UPDATE forensic_runs SET status='INTERRUPTED' WHERE id=?", (first["id"],)
    )
    resumed = client.post(f"/api/forensics/{eid}/screen").json()
    assert resumed["id"] == first["id"] and resumed["status"] == "COMPLETE"
    assert first["data"]["original_unchanged"] is True
    assert (
        client.put("/api/forensics/settings", json={"enabled": False}).json()["enabled"]
        is False
    )
    assert client.get("/api/forensics").json()["settings"]["enabled"] is False
    same = client.get(
        "/api/forensics/compare", params={"left": eid, "right": eid}
    ).json()
    assert same["byte_identical"] is True and same["average_hash_hamming"] == 0
    client.put("/api/forensics/settings", json={"enabled": True})


def test_holdout_does_not_authenticate_and_source_binding_is_enforced(core):
    c = TestClient(core.app)
    r = c.post(
        "/api/cipher",
        json={
            "method": "hex",
            "input": "4849",
            "holdout_input": "425945",
            "holdout_expected": "BYE",
        },
    ).json()
    assert r["holdout"]["status"] == "MATCH" and r["validation"] == "UNVALIDATED"
    assert (
        c.post(
            "/api/cipher",
            json={"method": "hex", "input": "4849", "evidence_id": "invented"},
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/cipher",
            json={"method": "affine", "input": "TEST", "parameters": {"a": 2}},
        ).status_code
        == 422
    )
