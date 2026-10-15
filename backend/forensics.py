"""Durable bounded screening of attested extracts; no shell/model tool access."""

import hashlib
import json
import threading
from pathlib import Path
from fastapi import HTTPException
from pydantic import BaseModel, Field
from .cryptanalysis import METHODS, VERSION, screen


def install(core):
    core.execute(
        "CREATE TABLE IF NOT EXISTS forensic_runs(id TEXT PRIMARY KEY,evidence_id TEXT, fingerprint TEXT UNIQUE,status TEXT,created TEXT,data TEXT)"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS forensic_settings(id TEXT PRIMARY KEY,data TEXT)"
    )
    core.execute(
        "INSERT OR IGNORE INTO forensic_settings VALUES(?,?)",
        ("default", json.dumps({"enabled": True, "max_characters": 4000, "seed": 0})),
    )
    guard = {}

    def settings():
        return json.loads(
            core.rows("SELECT data FROM forensic_settings WHERE id=?", ("default",))[0][
                "data"
            ]
        )

    def source(eid):
        records = core.rows("SELECT * FROM evidence WHERE id=?", (eid,))
        if not records:
            raise ValueError("Evidence not found")
        e = records[0]
        meta = json.loads(e["metadata"])
        path = Path(e["path"] or "")
        if (
            not e["path"]
            or not path.is_file()
            or path.is_symlink()
            or path.resolve().parent != (core.ROOT / "originals").resolve()
        ):
            raise ValueError("Acquired original is required")
        if hashlib.sha256(path.read_bytes()).hexdigest() != e["sha256"]:
            raise ValueError("Original integrity failed")
        text_path = core.ROOT / "derivatives" / eid / "text.txt"
        expected = meta.get("derivative_hashes", {}).get("text.txt")
        if (
            not meta.get("sandbox")
            or not expected
            or text_path.is_symlink()
            or not text_path.is_file()
            or hashlib.sha256(text_path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("Attested text derivative is required")
        if hashlib.sha256(e["text"].encode()).hexdigest() != expected:
            raise ValueError("Indexed text differs from derivative")
        return e, meta, expected

    def analyse(eid):
        with core.lock:
            gate = guard.setdefault(eid, threading.RLock())
        with gate:
            e, meta, digest = source(eid)
            config = settings()
            fingerprint = hashlib.sha256(
                json.dumps(
                    [
                        eid,
                        e["sha256"],
                        digest,
                        VERSION,
                        config["max_characters"],
                        config["seed"],
                        meta.get("image_forensics"),
                    ],
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            old = core.rows(
                "SELECT * FROM forensic_runs WHERE fingerprint=?", (fingerprint,)
            )
            if old and old[0]["status"] != "INTERRUPTED":
                return {**old[0], "data": json.loads(old[0]["data"])}
            rid = old[0]["id"] if old else core.uid("FORENSIC")
            if old:
                core.execute(
                    "UPDATE forensic_runs SET status='RUNNING' WHERE id=?", (rid,)
                )
                core.log("forensic_screen_resumed", {"id": rid, "evidence_id": eid})
            else:
                core.execute(
                    "INSERT INTO forensic_runs VALUES(?,?,?,?,?,?)",
                    (rid, eid, fingerprint, "RUNNING", core.now(), "{}"),
                )
            try:
                text = e["text"][: config["max_characters"]]
                data = (
                    screen(text, config["seed"])
                    if text.strip()
                    else {
                        "attempt_count": 0,
                        "attempts": [],
                        "validation": "UNVALIDATED",
                        "warning": "No OCR or text available; no text transformations attempted.",
                    }
                )
                data.update(
                    {
                        "evidence_sha256": e["sha256"],
                        "text_derivative_sha256": digest,
                        "input_offset": 0,
                        "input_truncated": len(e["text"]) > len(text),
                        "image_forensics": meta.get("image_forensics"),
                        "original_unchanged": True,
                    }
                )
                core.execute(
                    "UPDATE forensic_runs SET status=?,data=? WHERE id=?",
                    ("COMPLETE", json.dumps(data), rid),
                )
                core.log(
                    "forensic_screen_complete",
                    {"id": rid, "evidence_id": eid, "attempts": data["attempt_count"]},
                )
                return {
                    "id": rid,
                    "evidence_id": eid,
                    "status": "COMPLETE",
                    "data": data,
                }
            except Exception as ex:
                core.execute(
                    "UPDATE forensic_runs SET status=?,data=? WHERE id=?",
                    ("FAILED", json.dumps({"failure": str(ex)[:500]}), rid),
                )
                raise

    class Configuration(BaseModel):
        enabled: bool = True
        max_characters: int = Field(default=4000, ge=100, le=4000)
        seed: int = Field(default=0, ge=0, le=2**32 - 1)

    @core.app.get("/api/cipher/methods")
    def methods():
        return {
            "methods": METHODS,
            "engine_version": VERSION,
            "dictionary": "Original curated demonstration lexicon; supply a custom whitespace-separated dictionary for wider word coverage.",
        }

    @core.app.get("/api/forensics")
    def overview(include_results: bool = False):
        runs = [
            {**r, "data": json.loads(r["data"])}
            for r in core.rows(
                "SELECT * FROM forensic_runs ORDER BY created DESC LIMIT 100"
            )
        ]
        if not include_results:
            for r in runs:
                r["data"] = {
                    k: v
                    for k, v in r["data"].items()
                    if k
                    in (
                        "attempt_count",
                        "rule_count",
                        "parameter_trials",
                        "validation",
                        "warning",
                        "original_unchanged",
                        "failure",
                    )
                }
        return {
            "settings": settings(),
            "runs": runs,
            "attempts_total": sum(r["data"].get("attempt_count", 0) for r in runs),
            "automated": True,
            "poll_seconds": 30,
        }

    @core.app.get("/api/forensics/runs/{rid}")
    def detail(rid: str):
        records = core.rows("SELECT * FROM forensic_runs WHERE id=?", (rid,))
        if not records:
            raise HTTPException(404, "Screening run missing")
        return {**records[0], "data": json.loads(records[0]["data"])}

    @core.app.put("/api/forensics/settings")
    def configure(c: Configuration):
        core.execute(
            "UPDATE forensic_settings SET data=? WHERE id=?",
            (json.dumps(c.model_dump()), "default"),
        )
        return settings()

    @core.app.post("/api/forensics/{eid}/screen")
    def start(eid: str):
        try:
            return analyse(eid)
        except ValueError as ex:
            raise HTTPException(422, str(ex))

    @core.app.get("/api/evidence/{eid}/diagnostic/{kind}")
    def diagnostic(eid: str, kind: str):
        if kind not in (
            "red",
            "green",
            "blue",
            "lsb",
            "ela",
            "visual-blur-0",
            "visual-blur-2",
            "visual-blur-8",
            "visual-blur-24",
            "visual-panel-0",
            "visual-panel-1",
            "visual-panel-2",
            "visual-panel-3",
            "visual-fit-0",
            "visual-fit-1",
            "visual-fit-2",
            "visual-fit-3",
            "visual-residual-0",
            "visual-residual-1",
            "visual-residual-2",
            "visual-residual-3",
        ):
            raise HTTPException(404, "Unknown diagnostic")
        if not core.rows("SELECT id FROM evidence WHERE id=?", (eid,)):
            raise HTTPException(404, "Unknown evidence")
        path = core.ROOT / "derivatives" / eid / (kind + ".png")
        meta = json.loads(
            core.rows("SELECT metadata FROM evidence WHERE id=?", (eid,))[0]["metadata"]
        )
        expected = meta.get("derivative_hashes", {}).get(kind + ".png")
        if not expected or path.is_symlink() or not path.is_file():
            raise HTTPException(404, "Diagnostic not generated")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise HTTPException(409, "Diagnostic integrity failed")
        return core.FileResponse(
            path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"}
        )

    @core.app.get("/api/forensics/compare")
    def compare(left: str, right: str):
        try:
            a, am, _ = source(left)
            b, bm, _ = source(right)
        except ValueError as ex:
            raise HTTPException(422, str(ex))
        ah = am.get("average_hash")
        bh = bm.get("average_hash")
        return {
            "left": left,
            "right": right,
            "byte_identical": a["sha256"] == b["sha256"],
            "average_hash_hamming": (int(ah, 16) ^ int(bh, 16)).bit_count()
            if ah and bh
            else None,
            "dimensions": [am.get("dimensions"), bm.get("dimensions")],
            "warning": "Average hash compares coarse visual structure. A small distance does not establish identity, authorship, manipulation or a shared origin.",
        }

    def worker():
        core.execute(
            "UPDATE forensic_runs SET status='INTERRUPTED' WHERE status='RUNNING'"
        )
        # Interrupted runs retry with the same ID; completed results are never removed.
        while not core.stopping.is_set():
            core.heartbeat("forensic-screen", {"enabled": settings()["enabled"]})
            if settings()["enabled"]:
                for row in core.rows(
                    "SELECT id FROM evidence WHERE status='ORIGINAL VERIFIED' ORDER BY created DESC"
                ):
                    if core.stopping.is_set() or not settings()["enabled"]:
                        break
                    try:
                        record = core.rows(
                            "SELECT mime,metadata FROM evidence WHERE id=?",
                            (row["id"],),
                        )[0]
                        if record["mime"].startswith("image/") and not json.loads(
                            record["metadata"]
                        ).get("image_forensics"):
                            core.process(row["id"])
                        analyse(row["id"])
                    except Exception as ex:
                        core.log(
                            "forensic_screen_failure",
                            {"evidence_id": row["id"], "reason": str(ex)[:300]},
                        )
            core.stopping.wait(30)

    @core.app.on_event("startup")
    def startup():
        threading.Thread(target=worker, daemon=True, name="forensic-screen").start()

    return {"analyse": analyse, "source": source}
