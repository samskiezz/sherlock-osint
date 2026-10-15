"""Real Rust/Postgres acceptance tests plus deterministic client/extraction checks.

Run after cargo build --locked -p erps-api and scripts/setup_erps.py. Tests
create their own database and never mutate the application case or workspace.
"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import uuid

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def mention(name="John Smith", source=None, **extra):
    return dict(id=str(uuid.uuid4()), evidence_id=source or str(uuid.uuid4()), byte_offset=0,
        surface=name, kind="Person", context="", valid_from=0, valid_to=100, **extra)


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    cfg_path = ROOT / "data/erps.json"
    binary = ROOT / "target/debug/erps-api"
    if not cfg_path.exists() or not binary.exists():
        pytest.skip("ERPS real-service tests require setup_erps.py and cargo build -p erps-api")
    import psycopg
    from psycopg import sql
    from foundation import config
    cfg = json.loads(cfg_path.read_text())
    admin = config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    name = "erps_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {} OWNER erps_app").format(sql.Identifier(name)))
    from urllib.parse import urlsplit, urlunsplit
    parsed = urlsplit(cfg["ERPS_DATABASE_URL"])
    url = urlunsplit(parsed._replace(path="/" + name))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    log = tmp_path_factory.mktemp("erps") / "server.log"
    env = dict(os.environ, ERPS_DATABASE_URL=url, ERPS_TOKEN=secrets.token_hex(32),
        ERPS_WORKSPACE=str(uuid.uuid4()), ERPS_BIND=f"127.0.0.1:{port}", ERPS_BATCH_THRESHOLD="1")
    base = f"http://127.0.0.1:{port}"
    process = None

    def start():
        nonlocal process
        with log.open("a") as output:
            process = subprocess.Popen([str(binary)], env=env, stdout=output, stderr=output)
        for _ in range(200):
            try:
                if httpx.get(base + "/health", trust_env=False, timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            if process.poll() is not None:
                raise AssertionError("ERPS startup failed; inspect private test log")
            time.sleep(0.1)
        raise AssertionError("ERPS readiness timed out")

    def restart(batch="1"):
        process.kill(); process.wait(10)
        env["ERPS_BATCH_THRESHOLD"] = batch
        start()

    try:
        start()
        yield {"base": base, "url": url, "restart": restart}
    finally:
        if process and process.poll() is None:
            process.kill(); process.wait(10)
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def client(server):
    import psycopg
    workspace = str(uuid.uuid4()); token = secrets.token_hex(32)
    with psycopg.connect(server["url"]) as c:
        c.execute("INSERT INTO erps.policies(token_hash,workspace,actor,can_write,can_delete) VALUES(%s,%s,'acceptance',true,true)", (hashlib.sha256(token.encode()).hexdigest(), workspace))
    with httpx.Client(base_url=server["base"], trust_env=False, timeout=60,
        headers={"Authorization": "Bearer " + token, "X-ERPS-Purpose": "investigation"}) as client:
        client.workspace = workspace
        yield client


def resolved(client, mentions, constraints=None):
    r = client.post("/resolve", json={"mentions": mentions, "constraints": constraints or []})
    assert r.status_code == 200, r.text
    return r.json()


def test_same_batch_visibility_idempotency_and_five_views(client):
    a, b = mention(), mention()
    first = resolved(client, [a, b]); second = resolved(client, [b, a])
    assert first["candidate_pairs"] == 1
    assert first["scoring_engine"] == "datafusion"
    assert len(first["entities"]) == 1
    entity = first["entities"][0]
    assert entity == second["entities"][0]
    p = client.get("/lineage/" + entity["id"]).json()
    assert p["count"] == 2 and p["boolean"] is True
    assert set(p["support"]) == {a["evidence_id"], b["evidence_id"]}
    assert {tuple(w) for w in p["why"]} == {(a["evidence_id"],), (b["evidence_id"],)}
    assert len(p["decisions"][0]["provenance"]["monomials"][0]["vars"]) == 2
    assert client.get("/audit/verify").json()["valid"]


def test_atomic_rollback_and_identity_conflict(client):
    a = mention(); resolved(client, [a])
    b = dict(a, surface="Changed name")
    assert client.post("/resolve", json={"mentions": [mention("New Entity"), b]}).status_code == 422
    assert len(client.get("/entities").json()["entities"]) == 1
    invalid = mention(); invalid["valid_to"] = -1
    assert client.post("/resolve", json={"mentions": [invalid]}).status_code == 422
    assert client.post("/resolve", json={"mentions": [], "unexpected": 1}).status_code == 422


def test_large_coefficients_and_counts_remain_exact_in_json(client):
    largest=18446744073709551615
    source=str(uuid.uuid4())
    m=mention(source=source,provenance={"monomials":[{"vars":[source.upper()],"coeff":largest}]})
    entity=resolved(client,[m])["entities"][0]
    assert entity["provenance"]["monomials"][0]["coeff"]==str(largest)
    lineage=client.get("/lineage/"+entity["id"]).json()
    assert lineage["count"]==str(largest)
    assert lineage["why"]==[[source]] and lineage["boolean"] is True
    assert resolved(client,[m])["entities"][0]["id"]==entity["id"]
    retracted=client.post("/deletion",json={"source_var":source})
    assert retracted.status_code==200 and retracted.json()["entities"]==[]


def test_strong_identifiers_temporal_conflicts_and_constraints(client):
    a = mention("Alias One", attributes={"passport": "P1"})
    b = mention("Different Name", attributes={"passport": "P1"})
    result = resolved(client, [a, b]); assert len(result["entities"]) == 1
    c = mention("Alias One", attributes={"passport": "P2"})
    result = resolved(client, [c]); assert len(result["entities"]) == 2
    impossible = {"a": a["id"], "b": c["id"], "must_link": True}
    assert client.post("/resolve", json={"mentions": [], "constraints": [impossible]}).status_code == 422
    separate = {"a": a["id"], "b": b["id"], "must_link": False}
    assert client.post("/resolve", json={"mentions": [], "constraints": [separate]}).status_code == 422


def test_review_is_not_negative_and_neighborhood_is_explicit(client):
    a = mention(); b = mention(); a["context"] = "common alpha"; b["context"] = "common beta"
    result = resolved(client, [a, b]); assert len(result["entities"]) == 2
    eid = result["entities"][0]["id"]
    assert client.get("/lineage/" + eid).json()["decisions"][0]["decision"] == "Review"
    graph = client.get(f"/entities/{eid}/neighbors").json()
    assert len(graph["entities"]) == 2 and len(graph["edges"]) == 1
    assert graph["edges"][0]["kind"] == "candidate_review"


def test_deletion_splits_cluster_and_blocks_source_resurrection(client):
    a, b, c = mention("Alpha Entity"), mention("Bridge Entity"), mention("Zulu Entity")
    cs = [{"a": a["id"], "b": b["id"], "must_link": True}, {"a": b["id"], "b": c["id"], "must_link": True}]
    before = resolved(client, [a,b,c], cs); assert len(before["entities"]) == 1
    r = client.post("/deletion", json={"source_var": b["evidence_id"]}); assert r.status_code == 200, r.text
    after = r.json(); assert len(after["entities"]) == 2 and after["removed_mentions"] == [b["id"]]
    assert before["entities"][0]["id"] in after["deleted_entities"]
    assert client.post("/resolve", json={"mentions": [b]}).status_code == 422
    assert client.get("/entities/" + before["entities"][0]["id"]).status_code == 404


def test_alternate_derivation_survives_and_history_has_transaction_time(client):
    x,y,z = [str(uuid.uuid4()) for _ in range(3)]
    m = mention(source=z, provenance={"monomials": [{"vars": [x,y], "coeff": 2}, {"vars": [z], "coeff": 1}]})
    result = resolved(client,[m]); eid=result["entities"][0]["id"]
    r=client.post("/deletion",json={"source_var":x}); assert r.status_code==200,r.text
    assert r.json()["removed_mentions"]==[] and r.json()["affected_mentions"]==1
    p=client.get("/lineage/"+eid).json(); assert p["support"]==[z] and p["count"]==1
    assert client.get("/entities/"+eid,params={"as_of":"1900-01-01T00:00:00Z"}).status_code==404


def test_concurrent_resolution_has_no_lost_update(client):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        result=list(executor.map(lambda m: resolved(client,[m]),[mention("First Person"),mention("Second Human")]))
    assert len(result)==2
    assert len(client.get("/entities").json()["entities"])==2


def test_policies_no_cross_workspace_or_hidden_source_leak(client,server):
    result=resolved(client,[mention()]); entity=result["entities"][0]; eid=entity["id"]
    assert httpx.get(server["base"]+"/entities",trust_env=False).status_code==401
    assert client.get("/entities",headers={"X-ERPS-Purpose":"marketing"}).status_code==403
    import psycopg
    token=secrets.token_hex(32)
    with psycopg.connect(server["url"]) as c:
        c.execute("INSERT INTO erps.policies(token_hash,workspace,actor,properties,visible_sources) VALUES(%s,%s,'restricted',%s,%s)",(hashlib.sha256(token.encode()).hexdigest(),client.workspace,["canonical_name"],[]))
    headers={"Authorization":"Bearer "+token}
    constant=mention("Independent Axiom",provenance={"monomials":[{"vars":[],"coeff":1}]})
    resolved(client,[constant])
    assert client.get("/entities",headers=headers).json()["entities"]==[]
    assert client.get("/entities/"+eid,headers=headers).status_code==404
    assert client.get("/lineage/"+eid,headers=headers).status_code==404
    assert client.post("/deletion",headers=headers,json={"source_var":str(uuid.uuid4())}).status_code==403
    with psycopg.connect(server["url"]) as c:
        c.execute("UPDATE erps.policies SET visible_sources=NULL WHERE token_hash=%s",(hashlib.sha256(token.encode()).hexdigest(),))
    projected=client.get("/entities/"+eid,headers=headers).json()
    assert set(projected)=={"id","canonical_name","properties_withheld"}
    assert client.get("/lineage/"+eid,headers=headers).status_code==403
    assert client.get("/entities",params={"kind":"Person"},headers=headers).status_code==403
    assert client.get("/entities",params={"valid_at":1},headers=headers).status_code==403
    assert client.get(f"/entities/{eid}/neighbors",headers=headers).status_code==403
    with psycopg.connect(server["url"]) as c:
        c.execute("UPDATE erps.policies SET properties=%s WHERE token_hash=%s",(["kind"],hashlib.sha256(token.encode()).hexdigest()))
    assert client.get("/entities",params={"q":"John"},headers=headers).status_code==403
    other=secrets.token_hex(32)
    with psycopg.connect(server["url"]) as c:
        c.execute("INSERT INTO erps.policies(token_hash,workspace,actor) VALUES(%s,%s,'other')",(hashlib.sha256(other.encode()).hexdigest(),str(uuid.uuid4())))
    assert client.get("/entities/"+eid,headers={"Authorization":"Bearer "+other}).status_code==404


def test_crash_restart_rebuild_and_rayon_batch_equivalence(client,server):
    a,b=mention(),mention(); first=resolved(client,[a,b]); eid=first["entities"][0]["id"]
    score=client.get("/lineage/"+eid).json()["decisions"][0]["score"]
    server["restart"]("10000")
    assert client.get("/entities/"+eid).status_code==200
    result=resolved(client,[a,b]); assert result["scoring_engine"]=="rayon"
    assert client.get("/lineage/"+eid).json()["decisions"][0]["score"]==score
    server["restart"]("1")


def test_audit_is_append_only(client,server):
    resolved(client,[mention()]);assert client.get("/audit/verify").json()["valid"]
    import psycopg
    with psycopg.connect(server["url"]) as c:
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute("DELETE FROM erps.audit WHERE workspace=%s",(client.workspace,))


def test_transaction_history_and_ontology_validation(client,server):
    import psycopg
    a=mention(attributes={"passport":"A"})
    entity=resolved(client,[a])["entities"][0]
    with psycopg.connect(server["url"]) as c:
        stamp=c.execute("SELECT recorded_from FROM erps.entity_versions WHERE workspace=%s AND id=%s",(client.workspace,entity["id"])).fetchone()[0]
    client.post("/deletion",json={"source_var":a["evidence_id"]}).raise_for_status()
    old=client.get("/entities/"+entity["id"],params={"as_of":stamp.isoformat()})
    assert old.status_code==200 and old.json()["attributes"]["passport"][0]["value"]=="A"
    assert client.get("/entities/"+entity["id"]).status_code==404
    invalid=mention(attributes={"registration_id":"ORG-1"})
    assert client.post("/resolve",json={"mentions":[invalid]}).status_code==422
    ontology=client.get("/ontology").json()
    assert len(ontology["types"])==10 and ontology["logical_entailment"] is False


def test_durable_outbox_retries_without_discarding_original(monkeypatch,tmp_path):
    import sqlite3
    import types
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import backend.erps as module
    path=tmp_path/"case.db"
    def execute(query,args=()):
        with sqlite3.connect(path) as c:
            c.execute(query,args)
    def rows(query,args=()):
        with sqlite3.connect(path) as c:
            c.row_factory=sqlite3.Row
            return [dict(r) for r in c.execute(query,args)]
    execute("CREATE TABLE evidence(id TEXT,title TEXT,text TEXT,status TEXT,created TEXT)")
    execute("INSERT INTO evidence VALUES('EV-test','Synthetic fixture','John Smith met Jane Jones','ORIGINAL VERIFIED','now')")
    core=types.SimpleNamespace(app=FastAPI(),execute=execute,rows=rows,now=lambda:"now",log=lambda *a:None)
    state=module.install(core)
    class Client:
        fail=True
        calls=0
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def resolve(self,mentions):
            Client.calls+=1
            if Client.fail:raise httpx.ConnectError("unavailable")
            assert len(mentions)==2
    monkeypatch.setattr(module,"ErpsClient",Client)
    state["enqueue"]("EV-test",True);state["drain_once"]()
    assert rows("SELECT * FROM erps_outbox")[0]["status"]=="retry"
    assert rows("SELECT text FROM evidence")[0]["text"]=="John Smith met Jane Jones"
    for _ in range(9):state["drain_once"]()
    assert rows("SELECT * FROM erps_outbox")[0]["status"]=="failed"
    state["drain_once"]();assert Client.calls==10
    state["enqueue"]("EV-test",True)
    assert rows("SELECT * FROM erps_outbox")[0]["attempts"]==0
    Client.fail=False;state["drain_once"]();state["enqueue"]("EV-test",True);state["drain_once"]()
    assert rows("SELECT * FROM erps_outbox")[0]["status"]=="complete"
    assert Client.calls==11
    execute("DELETE FROM erps_outbox")
    monkeypatch.setenv("ERPS_AUTO_INGEST","1")
    state["reconcile_once"]()
    assert rows("SELECT * FROM erps_outbox")[0]["status"]=="pending"
    state["drain_once"]();assert Client.calls==12
    web=TestClient(core.app)
    assert web.post("/api/erps/index",json={"evidence_id":"EV-test"},headers={"X-Sherlock-Erps-Role":"Viewer"}).status_code==403


def test_extraction_utf8_offsets_and_deterministic_ids():
    from backend.erps import extract
    text="é evidence: John Smith contacted john@example.org"
    mentions=extract("EV-test",text)
    assert mentions==extract("EV-test",text)
    person=next(m for m in mentions if m["kind"]=="Person")
    assert person["byte_offset"]==len(text[:text.index("John")].encode())
    assert person["offset_space"]=="ExtractedTextUtf8"
    assert len({m["id"] for m in mentions})==len(mentions)


def test_client_auth_contract_and_failure_propagation(monkeypatch):
    from backend.erps_client import ErpsClient
    monkeypatch.setenv("ERPS_URL","http://127.0.0.1:3000");monkeypatch.setenv("ERPS_TOKEN","x"*64)
    def respond(request):
        assert request.headers["Authorization"]=="Bearer "+"x"*64
        assert request.headers["X-ERPS-Purpose"]=="investigation"
        return httpx.Response(503,json={"detail":"Unavailable"})
    with ErpsClient(transport=httpx.MockTransport(respond)) as c:
        with pytest.raises(httpx.HTTPStatusError):c.resolve([mention()])
