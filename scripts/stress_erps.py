"""Bounded capacity/recovery check using a temporary, owned Postgres database.

Requires setup_erps.py and a built ERPS executable. No records are written to the
operator's ERPS database. The synthetic singleton workload is not an ER accuracy
benchmark. Credentials stay in memory and private server logs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import random
import secrets
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit
import uuid

import httpx
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def exercise(binary, output, size):
    from foundation import config
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    result_file = output / "capacity.json"
    if result_file.exists():
        raise RuntimeError("Choose a new output directory to preserve earlier results")
    private = ROOT / "data/erps.json"
    if private.is_symlink() or private.stat().st_mode & 0o077:
        raise RuntimeError("ERPS config must be a regular private file")
    saved = json.loads(private.read_text())
    administrator = config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    name = "erps_capacity_" + uuid.uuid4().hex[:12]
    parts = urlsplit(saved["ERPS_DATABASE_URL"])
    database = urlunsplit(parts._replace(path="/" + name))
    token = secrets.token_hex(32)
    workspace = str(uuid.uuid4())
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    for key in config.KEYS | {"ERPS_READER_TOKEN", "ERPS_WRITER_TOKEN"}:
        env.pop(key, None)
    env.update(ERPS_DATABASE_URL=database, ERPS_TOKEN=token,
               ERPS_WORKSPACE=workspace, ERPS_BIND=f"127.0.0.1:{port}")
    process = None
    created = False
    report = {"status": "running", "mentions_requested": size,
              "workload": "seeded random identifiers with distinct overlapping passports; singleton ground truth",
              "batches": [], "temporary_database_removed": False}

    def persist():
        result_file.write_text(json.dumps(report, indent=2) + "\n")
        result_file.chmod(0o600)

    def start():
        nonlocal process
        with (output / "server.log").open("ab") as log:
            (output / "server.log").chmod(0o600)
            process = subprocess.Popen([str(binary)], env=env, cwd=ROOT,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        for _ in range(200):
            if process.poll() is not None:
                raise RuntimeError("Owned ERPS process exited; inspect the private server log")
            try:
                if httpx.get(base + "/health", trust_env=False, timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise RuntimeError("Owned ERPS readiness timed out")

    def stop(hard=False):
        if process is not None and process.poll() is None:
            process.kill() if hard else process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=10)

    def counts():
        with psycopg.connect(database) as db:
            return {table: db.execute(sql.SQL("SELECT count(*) FROM erps.{} WHERE workspace=%s")
                .format(sql.Identifier(table)), (workspace,)).fetchone()[0] for table in ("mentions", "entities")}

    rng = random.Random(42)
    def mention(i):
        return {"id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"owned-capacity-mention:{i}")),
                "evidence_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"owned-capacity-source:{i}")),
                "byte_offset": 0, "surface": "".join(rng.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=16)),
                "kind": "Person", "context": "", "valid_from": 0, "valid_to": 100,
                "attributes": {"passport": f"OWNED-CAPACITY-{i}"}}
    mentions = [mention(i) for i in range(size + 1)]
    persist()
    try:
        with psycopg.connect(administrator, autocommit=True) as db:
            db.execute(sql.SQL("CREATE DATABASE {} OWNER erps_app").format(sql.Identifier(name)))
        created = True
        start()
        with httpx.Client(base_url=base, trust_env=False, timeout=300,
                headers={"Authorization": "Bearer " + token, "X-ERPS-Purpose": "investigation"}) as client:
            first_id = None
            for offset in range(0, size, 1000):
                batch = mentions[offset:min(offset + 1000, size)]
                started = time.perf_counter()
                response = client.post("/resolve", json={"mentions": batch})
                assert response.status_code == 200, f"Owned load batch returned HTTP {response.status_code}"
                data = response.json()
                expected = offset + len(batch)
                assert len(data["entities"]) == expected
                first_id = next(e["id"] for e in data["entities"] if mentions[0]["id"] in e["mention_ids"])
                item = {"mentions": expected, "candidate_pairs": data["candidate_pairs"],
                        "scoring_engine": data["scoring_engine"], "http_round_trip_ms": round((time.perf_counter()-started)*1000,3)}
                report["batches"].append(item); persist()
                print(json.dumps(item), flush=True)
            assert counts() == {"mentions": size, "entities": size}
            report["full_capacity_counts"] = counts()
            lineage = client.get("/lineage/" + first_id).json()
            assert lineage["count"] == 1 and lineage["boolean"] and len(lineage["why"]) == 1
            assert lineage["support"] == [mentions[0]["evidence_id"]]
            page = client.get("/entities", params={"limit": 100}).json()
            assert len(page["entities"]) == min(100, size)
            if size > 100:
                following = client.get("/entities", params={"limit":100,"after":page["next"]}).json()
                assert not ({e["id"] for e in page["entities"]} & {e["id"] for e in following["entities"]})
            retry = client.post("/resolve", json={"mentions":mentions[max(0,size-1000):size]})
            assert retry.status_code == 200 and len(retry.json()["entities"]) == size
            report["idempotent_retry"] = True
            if size == 10_000:
                overflow = client.post("/resolve", json={"mentions":[mentions[-1]]})
                assert overflow.status_code == 422 and counts()["mentions"] == size
                report["capacity_overflow_rolled_back"] = True
            deletion = client.post("/deletion", json={"source_var":mentions[0]["evidence_id"]})
            assert deletion.status_code == 200
            assert len(deletion.json()["entities"]) == size-1
            assert client.get("/entities/" + first_id).status_code == 404
            assert client.post("/resolve", json={"mentions":[mentions[0]]}).status_code == 422
            assert counts() == {"mentions":size-1,"entities":size-1}
            report["deletion_and_resurrection_guard"] = True
            with ThreadPoolExecutor(max_workers=8) as pool:
                statuses = list(pool.map(lambda _: client.get("/entities",params={"limit":10}).status_code,range(8)))
            assert statuses == [200]*8
            report["concurrent_authenticated_reads"] = 8
            report["audit_chain_valid"] = client.get("/audit/verify").json()["valid"]
            assert report["audit_chain_valid"]
            peak = next((line.split()[1] for line in Path(f"/proc/{process.pid}/status").read_text().splitlines() if line.startswith("VmHWM:")),None)
            report["peak_rss_kib"] = int(peak) if peak else None
            stop(hard=True); start()
            assert len(client.get("/entities",params={"limit":10}).json()["entities"]) == min(10,size-1)
            assert counts() == {"mentions":size-1,"entities":size-1}
            report["crash_restart_persistence"] = True
            report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        raise
    finally:
        stop()
        if created:
            with psycopg.connect(administrator,autocommit=True) as db:
                db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            report["temporary_database_removed"] = True
        persist()
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary",type=Path,default=ROOT/"target/debug/erps-api")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--mentions",type=int,default=10_000)
    args=parser.parse_args()
    if not 1 <= args.mentions <= 10_000:
        parser.error("This bounded check supports 1..10000 synthetic mentions")
    result=exercise(args.binary.resolve(),args.output.resolve(),args.mentions)
    print(json.dumps({key:value for key,value in result.items() if key!='batches'}),flush=True)
