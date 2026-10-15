import base64
import hashlib
import os
import socket
import struct
import threading

import pytest
from fastapi.testclient import TestClient

from backend import onion as tor_module
from backend import research as research_module


def onion_address():
    key = b"K" * 32
    version = b"\x03"
    checksum = hashlib.sha3_256(b".onion checksum" + key + version).digest()[:2]
    return base64.b32encode(key + checksum + version).decode().lower() + ".onion"


@pytest.fixture(scope="module")
def case(tmp_path_factory):
    os.environ["SHERLOCK_DATA"] = str(tmp_path_factory.mktemp("research"))
    from backend import app as core

    client = TestClient(core.app)
    r = client.post(
        "/api/upload",
        files={
            "file": (
                "public-research-fixture.txt",
                b"The research report documents an ordinary propulsion experiment in 2016.",
                "text/plain",
            )
        },
    )
    assert r.status_code == 200, r.text
    return core, client, r.json()


def campaign(client, **extra):
    value = {
        "name": "Public research integration fixture",
        "question": "What does the research report actually document? Quote the original passage.",
        "queries": ["research"],
        "providers": ["nasa"],
        "max_downloads": 2,
        "cron_expression": "0 */6 * * *",
        **extra,
    }
    r = client.post("/api/research", json=value)
    assert r.status_code == 200, r.text
    return r.json()


def finish_run(core, rid, source):
    for _ in range(8):
        core.research["advance"](rid)
        r = core.research["value"](rid)
        for item in r["data"].get("jobs", []):
            core.execute(
                "UPDATE jobs SET status='COMPLETE',progress=100,evidence_id=? WHERE id=?",
                (source["id"], item["job_id"]),
            )
        iid = r["data"].get("investigation_id")
        if iid and core.investigator["value"](iid)["status"] == "QUEUED":
            core.investigator["run"](iid)
        if r["status"] in ("COMPLETE", "PARTIAL", "FAILED"):
            return r
    raise AssertionError("Research pipeline did not terminate")


def test_campaign_acquires_audits_publishes_and_keeps_source_failure(case, monkeypatch):
    core, client, source = case

    def search(_, provider, *args):
        if provider == "gdelt":
            raise ValueError("Test source unavailable")
        return {
            "catalogues": [],
            "hits": [
                {
                    "url": "https://example.com/research.txt",
                    "title": "Public research fixture",
                    "kind": "document",
                    "provider": provider,
                }
            ],
        }

    monkeypatch.setattr(research_module, "search", search)
    c = campaign(client, providers=["nasa", "gdelt"])
    r = core.research["launch"](c["id"])
    completed = finish_run(core, r["id"], source)
    assert completed["status"] == "PARTIAL"
    assert completed["data"]["result"]["acquired"][0]["sha256"] == source["sha256"]
    assert (
        completed["data"]["result"]["new_originals"] == 0
    )  # fixture already existed; a new job is not a new vault file
    board = client.get("/api/boards/" + c["board_id"]).json()
    assert len(board["nodes"]) == 1 and board["edges"] == []
    assert completed["data"]["result"]["analysis_state"] == "COMPLETE"
    assert any(t["status"] == "FAILED" for t in completed["tasks"])


def test_second_cron_run_reuses_source_and_does_not_generate_duplicate_plan(
    case, monkeypatch
):
    core, client, source = case
    monkeypatch.setattr(
        research_module,
        "search",
        lambda *args: {
            "catalogues": [],
            "hits": [
                {
                    "url": "https://example.com/stable.txt",
                    "title": "Stable public source",
                    "kind": "document",
                }
            ],
        },
    )
    c = campaign(client)
    first = finish_run(core, core.research["launch"](c["id"])["id"], source)
    second = finish_run(core, core.research["launch"](c["id"])["id"], source)
    assert first["data"]["result"]["investigation_id"]
    assert second["data"]["result"]["investigation_id"] is None
    assert second["data"]["result"]["new_to_campaign"] == 0
    assert first["data"]["jobs"][0]["job_id"] == second["data"]["jobs"][0]["job_id"]


def test_pause_during_search_preserves_state_and_reuses_completed_tool(
    case, monkeypatch
):
    core, client, _ = case
    started, release = threading.Event(), threading.Event()
    calls = []

    def search(*args):
        calls.append(1)
        started.set()
        assert release.wait(5)
        return {"catalogues": [], "hits": []}

    monkeypatch.setattr(research_module, "search", search)
    c = campaign(client)
    r = core.research["launch"](c["id"])
    thread = threading.Thread(target=core.research["advance"], args=(r["id"],))
    thread.start()
    assert started.wait(3)
    assert client.post(f"/api/research/{c['id']}/pause").status_code == 200
    release.set()
    thread.join(5)
    paused = core.research["value"](r["id"])
    assert paused["status"] == "PAUSED" and paused["cursor"] == 0
    task_ids = [t["id"] for t in paused["tasks"]]
    client.post(f"/api/research/{c['id']}/resume")
    core.research["advance"](r["id"])
    resumed = core.research["value"](r["id"])
    assert resumed["cursor"] == 1 and len(calls) == 1
    assert [t["id"] for t in resumed["tasks"]] == task_ids


def test_cancel_prevents_late_publish_and_pauses_owned_jobs(case, monkeypatch):
    core, client, _ = case
    monkeypatch.setattr(
        research_module,
        "search",
        lambda *args: {
            "catalogues": [],
            "hits": [
                {
                    "url": "https://example.com/pending.txt",
                    "title": "Pending original",
                    "kind": "document",
                }
            ],
        },
    )
    c = campaign(client)
    r = core.research["launch"](c["id"])
    core.research["advance"](r["id"])
    core.research["advance"](r["id"])
    queued = core.research["value"](r["id"])
    jid = queued["data"]["jobs"][0]["job_id"]
    client.post(f"/api/research/{c['id']}/pause")
    assert (
        core.rows("SELECT status FROM jobs WHERE id=?", (jid,))[0]["status"] == "PAUSED"
    )
    client.post(f"/api/research/{c['id']}/resume")
    assert (
        core.rows("SELECT status FROM jobs WHERE id=?", (jid,))[0]["status"] == "QUEUED"
    )
    client.post(f"/api/research/{c['id']}/cancel")
    core.research["advance"](r["id"])
    assert core.research["value"](r["id"])["status"] == "CANCELLED"
    assert (
        core.rows("SELECT status FROM jobs WHERE id=?", (jid,))[0]["status"]
        == "CANCELLED"
    )
    assert client.get("/api/boards/" + c["board_id"]).json()["nodes"] == []


def test_sandbox_extracts_document_links_and_research_follows_one_hop(
    case, monkeypatch
):
    core, client, _ = case
    html = b'<html><title>Research disclosure</title><body>Public research report <a href="https://example.com/original.pdf">Original research paper</a><script>bad()</script></body></html>'
    page = client.post(
        "/api/upload", files={"file": ("disclosure.html", html, "text/html")}
    ).json()
    assert page["metadata"]["links"][0]["href"] == "https://example.com/original.pdf"
    assert "bad()" not in page["text"]
    monkeypatch.setattr(
        research_module,
        "search",
        lambda *args: {
            "catalogues": [],
            "hits": [
                {
                    "url": "https://example.com/page",
                    "title": "Research page",
                    "kind": "webpage",
                }
            ],
        },
    )
    c = campaign(client)
    r = core.research["launch"](c["id"])
    core.research["advance"](r["id"])
    core.research["advance"](r["id"])
    jid = core.research["value"](r["id"])["data"]["jobs"][0]["job_id"]
    core.execute(
        "UPDATE jobs SET status='COMPLETE',evidence_id=? WHERE id=?", (page["id"], jid)
    )
    core.research["advance"](r["id"])
    jobs = core.research["value"](r["id"])["data"]["jobs"]
    assert (
        len(jobs) == 2 and jobs[1]["hit"]["url"] == "https://example.com/original.pdf"
    )
    assert jobs[1]["hit"]["parent_evidence_id"] == page["id"]


def test_campaign_rejects_private_seeds_and_invalid_schedules(case):
    _, client, _ = case
    base = {
        "name": "Invalid seed",
        "question": "Find public documents relating to this case.",
        "queries": ["research"],
        "providers": ["feeds"],
    }
    assert (
        client.post(
            "/api/research", json={**base, "seeds": ["http://127.0.0.1/secrets"]}
        ).status_code
        == 422
    )
    assert client.post("/api/research", json={**base, "seeds": []}).status_code == 422
    assert (
        client.post(
            "/api/research",
            json={**base, "providers": ["nasa"], "cron_expression": "* * * * *"},
        ).status_code
        == 422
    )


def test_onion_v3_checksum_and_explicit_transport_guard(case):
    core, client, _ = case
    host = onion_address()
    assert tor_module.validate_onion_url("http://" + host + "/doc.pdf").hostname == host
    for value in (
        "http://127.0.0.1/file",
        "https://example.com/file",
        "http://" + host.replace(host[0], "a", 1),
        "http://" + host + ":8080/file",
    ):
        with pytest.raises(ValueError):
            tor_module.validate_onion_url(value)
    with pytest.raises(ValueError):
        core.validate_url("http://" + host)
    assert (
        client.post(
            "/api/jobs",
            json={
                "url": "http://" + host,
                "title": "Onion fixture",
                "transport": "public",
            },
        ).status_code
        == 422
    )
    r = client.post(
        "/api/jobs",
        json={"url": "http://" + host, "title": "Onion fixture", "transport": "tor"},
    )
    assert r.status_code == 200
    assert (
        core.rows("SELECT transport FROM jobs WHERE id=?", (r.json()["id"],))[0][
            "transport"
        ]
        == "tor"
    )
    assert (
        client.post(
            "/api/onion/config", json={"proxy": "socks5://127.0.0.1:9050"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/onion/config", json={"proxy": "socks5h://10.0.0.2:9050"}
        ).status_code
        == 422
    )


def test_blocked_tor_never_sends_request_or_claims_acquisition(case, monkeypatch):
    core, client, _ = case
    monkeypatch.setattr(
        tor_module, "runtime_blocker", lambda: "Fixture: no TCP relay grants"
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Network request must not be made")

    monkeypatch.setattr(tor_module.httpx, "Client", forbidden)
    status = client.get("/api/onion/status").json()
    assert status["state"] == "BLOCKED_NETWORK_POLICY" and not status["ready"]
    with pytest.raises(ValueError, match="no TCP"):
        core.onion["fetch"]("http://" + onion_address())


def socks_server(response):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)
    records = []

    def exact(c, n):
        out = b""
        while len(out) < n:
            part = c.recv(n - len(out))
            assert part
            out += part
        return out

    def serve():
        with listener:
            c, _ = listener.accept()
            with c:
                c.settimeout(5)
                greeting = exact(c, 2)
                exact(c, greeting[1])
                c.sendall(b"\x05\x00")
                head = exact(c, 4)
                assert head[3] == 3  # SOCKS domain name, not a locally resolved IP
                length = exact(c, 1)[0]
                host = exact(c, length).decode()
                port = struct.unpack("!H", exact(c, 2))[0]
                records.append((host, port))
                c.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x50")
                request = b""
                while b"\r\n\r\n" not in request:
                    request += c.recv(4096)
                records.append(request.decode())
                c.sendall(response)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return listener.getsockname()[1], records, thread


def test_socks5h_sends_onion_hostname_to_proxy_without_local_dns(case, monkeypatch):
    core, _, _ = case
    body = b"Public onion protocol fixture"
    port, records, thread = socks_server(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\nConnection: close\r\n\r\n"
        + body
    )
    monkeypatch.setattr(tor_module, "runtime_blocker", lambda: None)
    original_dns = socket.getaddrinfo

    def guarded(host, *args, **kwargs):
        assert not str(host).endswith(".onion"), "Onion DNS leaked locally"
        return original_dns(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded)
    core.execute(
        "UPDATE tor_config SET enabled=1,proxy=? WHERE id=1",
        (f"socks5h://127.0.0.1:{port}",),
    )
    try:
        result = core.onion["fetch"]("http://" + onion_address() + "/document.txt")
        assert result[0] == body and records[0] == (onion_address(), 80)
        thread.join(3)
        assert "GET /document.txt" in records[1]
    finally:
        core.execute(
            "UPDATE tor_config SET enabled=0,proxy='socks5h://127.0.0.1:9050' WHERE id=1"
        )


def test_onion_redirect_to_clearnet_is_rejected_without_fallback(case, monkeypatch):
    core, _, _ = case
    port, records, thread = socks_server(
        b"HTTP/1.1 302 Found\r\nLocation: https://example.com/file.pdf\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    )
    monkeypatch.setattr(tor_module, "runtime_blocker", lambda: None)
    core.execute(
        "UPDATE tor_config SET enabled=1,proxy=? WHERE id=1",
        (f"socks5h://127.0.0.1:{port}",),
    )
    try:
        with pytest.raises(ValueError, match="onion address"):
            core.onion["fetch"]("http://" + onion_address() + "/file")
        thread.join(3)
        assert len(records) == 2
    finally:
        core.execute(
            "UPDATE tor_config SET enabled=0,proxy='socks5h://127.0.0.1:9050' WHERE id=1"
        )
