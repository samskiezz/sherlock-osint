"""Private access must authenticate and verify real routes before advertising a URL."""

import asyncio
import json
import os
import selectors
import subprocess
import sys
import uuid

import httpx
import pytest

from scripts import private_site_access as access


def configuration():
    return {
        "url": access.PRIVATE_ORIGIN,
        "service_token": "owned-fixture-service-token",
        "relay_secret": "owned-fixture-relay-secret",
    }


def test_missing_bindings_fail_without_prompting_or_disclosing_values():
    env = {key: value for key, value in os.environ.items() if key not in access.ENVIRONMENT_NAMES}
    env["SHERLOCK_SITE_SERVICE_TOKEN"] = configuration()["service_token"]
    result = subprocess.run(
        [sys.executable, "scripts/private_site_access.py", "--from-env", "--check-only"],
        cwd=access.ROOT, env=env, input="", capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 2
    assert "SHERLOCK_RELAY_SECRET" in result.stderr
    assert "SHERLOCK_PRIVATE_ACCESS_URL" in result.stderr
    assert configuration()["service_token"] not in result.stdout + result.stderr
    assert "hidden stdin" not in result.stdout


@pytest.mark.parametrize("origin", [
    "http://sherlock-looking-glass-access.sam-kazangas-5963.chatgpt.site",
    "https://another-owner.chatgpt.site",
    access.PRIVATE_ORIGIN + "/other",
    access.PRIVATE_ORIGIN + "?token=private",
    access.PRIVATE_ORIGIN.replace("https://", "https://user:secret@"),
    access.PRIVATE_ORIGIN + ":8443",
])
def test_credentials_are_sent_only_to_the_reviewed_origin(origin):
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(410, json={"detail": "Ticket expired"})
    with pytest.raises(access.AccessError, match="reviewed credential destination"):
        access.preflight(dict(configuration(), url=origin), transport=httpx.MockTransport(transport))
    assert calls == []


def test_preflight_authenticates_without_consuming_or_writing_mailbox_work():
    calls = []
    def transport(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == "/__sherlock_relay/input"
        assert uuid.UUID(request.url.params["id"]).version == 4
        assert request.headers["OAI-Sites-Authorization"] == "Bearer " + configuration()["service_token"]
        assert request.headers["X-Sherlock-Relay-Key"] == configuration()["relay_secret"]
        assert not request.content
        return httpx.Response(410, json={"detail": "Ticket expired"})
    access.preflight(configuration(), transport=httpx.MockTransport(transport))
    assert len(calls) == 1


@pytest.mark.parametrize("status,body", [
    (401, {"detail": "Sign in"}),
    (403, {"detail": "Unauthorised relay request"}),
    (302, {}),
    (200, {"detail": "Ticket expired"}),
    (410, {"detail": "different application"}),
    (410, []),
])
def test_preflight_rejects_auth_failure_redirects_and_wrong_protocol(status, body):
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(status, json=body, headers={"Location": "https://untrusted.example"})
    with pytest.raises(access.AccessError) as caught:
        access.preflight(configuration(), transport=httpx.MockTransport(transport))
    assert len(calls) == 1
    assert all(secret not in str(caught.value) for secret in list(configuration().values())[1:])


def response_for(path):
    if path == "/?view=entities":
        return httpx.Response(200, text='<html><script src="/assets/index.js"></script></html>',
                              headers={"content-type": "text/html; charset=utf-8"})
    if path == "/api/erps/health":
        return httpx.Response(200, json={"status": "ok"})
    if path == "/api/erps/entities?limit=1":
        return httpx.Response(200, json={"entities": []})
    raise AssertionError("Unexpected probe route")


def test_verified_url_requires_built_frontend_erps_and_authenticated_entity_query():
    paths = []
    def transport(request):
        if request.url.path == "/":
            assert "OAI-Sites-Authorization" not in request.headers
            assert "X-Sherlock-Relay-Key" not in request.headers
            return httpx.Response(401)
        assert request.method == "GET" and request.url.path == "/__sherlock_relay/check"
        paths.append(request.url.params["path"])
        return response_for(paths[-1])
    result = access.verify_access(configuration(), transport=httpx.MockTransport(transport))
    assert paths == ["/?view=entities", "/api/erps/health", "/api/erps/entities?limit=1"]
    assert result == {"status": "verified", "url": access.PRIVATE_ORIGIN + "/?view=entities", "private_signin_required": True}


def test_verification_rejects_public_hosting_even_with_working_application():
    def transport(request):
        return (httpx.Response(200, text="public") if request.url.path == "/"
                else response_for(request.url.params["path"]))
    with pytest.raises(access.AccessError, match="sign-in boundary"):
        access.verify_access(configuration(), transport=httpx.MockTransport(transport))


@pytest.mark.parametrize("bad_path,status,body,content_type", [
    ("/?view=entities", 503, "disconnected", "text/plain"),
    ("/?view=entities", 200, "<html>Sign in</html>", "text/html"),
    ("/api/erps/health", 200, '{"status":"degraded"}', "application/json"),
    ("/api/erps/entities?limit=1", 401, "unauthorised", "text/plain"),
    ("/api/erps/entities?limit=1", 200, "not JSON", "text/plain"),
    ("/api/erps/entities?limit=1", 200, "[]", "application/json"),
])
def test_verification_never_claims_disconnected_or_incomplete_app_is_working(bad_path, status, body, content_type):
    def transport(request):
        path = request.url.params["path"]
        return (httpx.Response(status, text=body, headers={"content-type": content_type})
                if path == bad_path else response_for(path))
    with pytest.raises(access.AccessError):
        access.verify_access(configuration(), transport=httpx.MockTransport(transport))


def test_transport_errors_do_not_echo_credential_values():
    def transport(request):
        raise httpx.ConnectError(configuration()["service_token"], request=request)
    for operation in (access.preflight, access.verify_access):
        with pytest.raises(access.AccessError, match="ConnectError") as caught:
            operation(configuration(), transport=httpx.MockTransport(transport))
        assert configuration()["service_token"] not in str(caught.value)


def test_relay_shutdown_removes_its_pid_and_releases_singleton_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(access, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["private_site_access.py", "--from-env"])
    for name, value in zip(access.ENVIRONMENT_NAMES,
                           (configuration()["service_token"], configuration()["relay_secret"], access.PRIVATE_ORIGIN)):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(access, "preflight", lambda _: None)
    monkeypatch.setattr(access.signal, "signal", lambda *_: None)
    calls = []
    async def relay(_):
        assert (tmp_path / "data/private-site-access.pid").read_text() == str(os.getpid())
        calls.append(True)
        raise KeyboardInterrupt
    monkeypatch.setattr(access, "relay", relay)
    for _ in range(2):
        access.main()
        assert not (tmp_path / "data/private-site-access.pid").exists()
    assert len(calls) == 2


def test_python_companion_and_real_worker_complete_remote_checks(monkeypatch, tmp_path):
    """Real HTTP/Worker round trip with fixture-only credentials and local data.

    The transports map the reviewed hostname to the loopback fixture. This
    does not access or certify the actual private Sites deployment.
    """
    server = None
    with (tmp_path / "worker.log").open("w") as log:
        try:
            server = subprocess.Popen(
                ["node", "hosting/private-access/scripts/fixtures/worker-server.mjs"],
                cwd=access.ROOT, stdout=subprocess.PIPE, stderr=log, text=True,
            )
            with selectors.DefaultSelector() as selector:
                selector.register(server.stdout, selectors.EVENT_READ)
                assert selector.select(timeout=10), "Owned Worker fixture did not start"
            worker_url = "http://127.0.0.1:" + str(json.loads(server.stdout.readline())["port"])
            real_async_client = httpx.AsyncClient
            calls = []
            credentials = tmp_path / "data/foundation-secrets/admin-login.json"
            credentials.parent.mkdir(parents=True)
            credentials.write_text(json.dumps({"username": "owned-fixture", "password": "owned-fixture-password"}))
            credentials.chmod(0o600)
            monkeypatch.setattr(access, "ROOT", tmp_path)

            class WorkerTransport(httpx.BaseTransport):
                def __init__(self):
                    self.client = httpx.Client(base_url=worker_url, trust_env=False, timeout=5)
                def handle_request(self, request):
                    response = self.client.request(request.method, request.url.raw_path.decode(),
                                                   headers={key: value for key, value in request.headers.items()
                                                            if key not in ("content-length", "transfer-encoding")},
                                                   content=request.read())
                    return httpx.Response(response.status_code, headers=response.headers, content=response.content)
                def close(self):
                    self.client.close()

            class AsyncWorkerTransport(httpx.AsyncBaseTransport):
                def __init__(self):
                    self.client = real_async_client(base_url=worker_url, trust_env=False, timeout=5)
                async def handle_async_request(self, request):
                    response = await self.client.request(request.method, request.url.raw_path.decode(),
                                                         headers={key: value for key, value in request.headers.items()
                                                                  if key not in ("content-length", "transfer-encoding")},
                                                         content=await request.aread())
                    return httpx.Response(response.status_code, headers=response.headers, content=response.content)
                async def aclose(self):
                    await self.client.aclose()

            def gateway(request):
                calls.append(request.url.path)
                assert "OAI-Sites-Authorization" not in request.headers
                assert "X-Sherlock-Relay-Key" not in request.headers
                if request.url.path == "/api/v1/auth/login":
                    assert json.loads(request.content) == {"username": "owned-fixture", "password": "owned-fixture-password"}
                    return httpx.Response(200, json={"access_token": "owned-fixture-local-token"})
                assert request.headers["Authorization"] == "Bearer owned-fixture-local-token"
                response = response_for(request.url.raw_path.decode())
                return httpx.Response(response.status_code, headers=response.headers,
                                      stream=httpx.ByteStream(response.content))

            def clients(**kwargs):
                if kwargs["base_url"] == access.PRIVATE_ORIGIN:
                    kwargs["transport"] = AsyncWorkerTransport()
                else:
                    assert kwargs["base_url"] == access.LOCAL
                    kwargs["transport"] = httpx.MockTransport(gateway)
                return real_async_client(**kwargs)
            monkeypatch.setattr(access.httpx, "AsyncClient", clients)

            async def scenario():
                task = asyncio.create_task(access.relay(configuration()))
                try:
                    async with real_async_client(base_url=worker_url, trust_env=False) as control:
                        for _ in range(100):
                            if (await control.get("/__fixture/ready")).status_code == 200:
                                break
                            await asyncio.sleep(0.03)
                        else:
                            raise AssertionError("Companion never sent a heartbeat")
                    await asyncio.to_thread(access.preflight, configuration(), transport=WorkerTransport())
                    return await asyncio.to_thread(access.verify_access, configuration(), transport=WorkerTransport())
                finally:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            result = asyncio.run(scenario())
            assert result["status"] == "verified"
            assert result["private_signin_required"] is True
            assert calls == ["/api/v1/auth/login", "/", "/api/erps/health", "/api/erps/entities"]
        finally:
            if server is not None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill(); server.wait(timeout=5)
                if server.stdout:
                    server.stdout.close()
