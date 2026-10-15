"""Outbound-only private Sites relay; credentials stay in process memory.

Only the fixed authenticated local gateway is reachable. This process does not
accept arbitrary upstream hosts, run shell commands, or expose the Docker API.
"""

import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import termios
import time
from urllib.parse import quote, urlsplit
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT = 32 * 1024 * 1024
MAX_OUTPUT = 256 * 1024 * 1024
LOCAL = "http://127.0.0.1:8010"
PRIVATE_ORIGIN = "https://sherlock-looking-glass-access.sam-kazangas-5963.chatgpt.site"
ENVIRONMENT_NAMES = (
    "SHERLOCK_SITE_SERVICE_TOKEN",
    "SHERLOCK_RELAY_SECRET",
    "SHERLOCK_PRIVATE_ACCESS_URL",
)
ALLOWED_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
RESPONSE_HEADERS = {
    "content-type",
    "content-disposition",
    "content-range",
    "accept-ranges",
    "etag",
    "last-modified",
    "cache-control",
}


class AccessError(RuntimeError):
    """A safe access diagnostic which never includes credential values."""


def missing_environment(environ=None):
    environ = os.environ if environ is None else environ
    return [name for name in ENVIRONMENT_NAMES if not environ.get(name)]


def validate_config(config):
    if not isinstance(config, dict) or any(
        not isinstance(config.get(key), str) or not config[key]
        for key in ("url", "service_token", "relay_secret")
    ):
        raise AccessError("Private access requires an origin, service token and relay secret")
    if config["url"].rstrip("/") != PRIVATE_ORIGIN:
        raise AccessError("Private origin differs from the reviewed credential destination")
    return {"url": PRIVATE_ORIGIN, "service_token": config["service_token"], "relay_secret": config["relay_secret"]}


def environment_config(environ=None):
    environ = os.environ if environ is None else environ
    missing = missing_environment(environ)
    if missing:
        raise AccessError("Missing secure environment configuration: " + ", ".join(missing))
    return validate_config({
        "url": environ["SHERLOCK_PRIVATE_ACCESS_URL"].rstrip("/"),
        "service_token": environ["SHERLOCK_SITE_SERVICE_TOKEN"],
        "relay_secret": environ["SHERLOCK_RELAY_SECRET"],
    })


def remote_client(config, transport=None):
    config = validate_config(config)
    return httpx.Client(
        base_url=config["url"],
        headers={
            "OAI-Sites-Authorization": "Bearer " + config["service_token"],
            "X-Sherlock-Relay-Key": config["relay_secret"],
        },
        timeout=100,
        follow_redirects=False,
        transport=transport,
    )


def preflight(config, *, transport=None):
    """Authenticate without consuming queued work or modifying the mailbox.

    A random, absent input ticket returns 410 only after both authentication
    layers. Unknown operations are unsuitable: this Worker validates a ticket
    before it returns its unknown-operation response.
    """
    try:
        with remote_client(config, transport) as remote:
            response = remote.get(
                "/__sherlock_relay/input", params={"id": str(uuid.uuid4())}, timeout=20
            )
        if response.status_code != 410:
            raise AccessError(f"Private authentication preflight failed (HTTP {response.status_code})")
        if response.json().get("detail") != "Ticket expired":
            raise AccessError("Private authentication preflight returned an unexpected response")
    except httpx.HTTPError as error:
        raise AccessError("Private preflight transport failed: " + type(error).__name__) from None
    except (ValueError, AttributeError):
        raise AccessError("Private authentication preflight returned an unexpected response") from None


def verify_access(config, *, transport=None):
    """Verify the real HTML and ERPS request path before returning a remote URL."""
    try:
        with remote_client(config, transport) as remote, httpx.Client(
            base_url=PRIVATE_ORIGIN, timeout=20, follow_redirects=False, transport=transport
        ) as anonymous:
            def check(path):
                response = remote.get("/__sherlock_relay/check", params={"path": path})
                if response.status_code != 200:
                    raise AccessError(f"External application check failed (HTTP {response.status_code})")
                return response

            html = check("/?view=entities")
            if "text/html" not in html.headers.get("content-type", "") or "/assets/" not in html.text:
                raise AccessError("External application did not return the built frontend")
            health = check("/api/erps/health").json()
            if not isinstance(health, dict) or health.get("status") != "ok":
                raise AccessError("External ERPS health check failed")
            entities = check("/api/erps/entities?limit=1").json()
            if not isinstance(entities, dict) or not isinstance(entities.get("entities"), list):
                raise AccessError("External authenticated entity query failed")
            boundary = anonymous.get("/")
        if boundary.status_code not in (301, 302, 303, 307, 308, 401, 403):
            raise AccessError("Private hosting sign-in boundary was not verified")
        return {"status": "verified", "url": PRIVATE_ORIGIN + "/?view=entities", "private_signin_required": True}
    except httpx.HTTPError as error:
        raise AccessError("External verification transport failed: " + type(error).__name__) from None
    except ValueError:
        raise AccessError("External application returned an invalid response") from None


def valid_job(job):
    """Reject nonlocal targets, stale tickets, control characters and unsupported routes."""
    path = job.get("path", "")
    parsed = urlsplit(path)
    route = parsed.path
    return (
        job.get("method") in ALLOWED_METHODS
        and not parsed.scheme
        and not parsed.netloc
        and path.startswith("/")
        and not path.startswith("//")
        and "\\" not in path
        and not any(ord(c) < 32 for c in path)
        and (
            route == "/"
            or route.startswith(("/api/", "/assets/", "/pdfjs/"))
            or route == "/favicon.ico"
        )
        and 0 <= time.time() * 1000 - job.get("created", 0) < 85000
    )


async def relay(config):
    """Poll the private mailbox and stream only owner-authorised requests to the existing app."""
    config = validate_config(config)
    remote_headers = {
        "OAI-Sites-Authorization": "Bearer " + config["service_token"],
        "X-Sherlock-Relay-Key": config["relay_secret"],
    }
    gate = asyncio.Semaphore(8)
    login_lock = asyncio.Lock()
    access = {"token": None, "expires": 0}
    tasks = set()
    async with (
        httpx.AsyncClient(
            base_url=config["url"],
            headers=remote_headers,
            timeout=httpx.Timeout(100, connect=15),
            follow_redirects=False,
        ) as remote,
        httpx.AsyncClient(
            base_url=LOCAL, trust_env=False, timeout=80, follow_redirects=False
        ) as local,
    ):

        async def token():
            """Authenticate locally without sending the account password to the hosted mailbox."""
            async with login_lock:
                if access["token"] and access["expires"] > time.time():
                    return access["token"]
                credentials = json.loads(
                    (ROOT / "data/foundation-secrets/admin-login.json").read_text()
                )
                response = await local.post("/api/v1/auth/login", json=credentials)
                response.raise_for_status()
                access.update(
                    token=response.json()["access_token"], expires=time.time() + 1200
                )
                return access["token"]

        async def execute(job):
            """Stream one bounded request/response, preserving MIME and range semantics."""
            async with gate:
                if not valid_job(job):
                    return
                body = None
                if job.get("has_body"):
                    result = await remote.get(
                        "/__sherlock_relay/input", params={"id": job["id"]}
                    )
                    result.raise_for_status()
                    body = result.content
                    if len(body) > MAX_INPUT:
                        return
                headers = {
                    k: v
                    for k, v in job.get("headers", {}).items()
                    if k.lower() in {"content-type", "range", "if-none-match"}
                }
                headers.update(
                    {
                        "Authorization": "Bearer " + await token(),
                        "Accept-Encoding": "identity",
                    }
                )
                async with local.stream(
                    job["method"], job["path"], headers=headers, content=body
                ) as response:
                    if response.status_code == 401:
                        access["expires"] = 0
                    response_headers = {
                        k: v
                        for k, v in response.headers.items()
                        if k in RESPONSE_HEADERS
                    }

                    async def chunks():
                        """Bound transfer bytes without decoding images or buffering original files."""
                        size = 0
                        async for chunk in response.aiter_raw():
                            size += len(chunk)
                            if size > MAX_OUTPUT:
                                raise ValueError(
                                    "Remote response exceeds transfer budget"
                                )
                            yield chunk

                    result = await remote.post(
                        "/__sherlock_relay/respond",
                        params={"id": job["id"]},
                        headers={
                            "X-Sherlock-Status": str(response.status_code),
                            "X-Sherlock-Headers": quote(
                                json.dumps(response_headers), safe=""
                            ),
                        },
                        content=chunks(),
                    )
                    if result.status_code != 410:
                        result.raise_for_status()

        async def safe_execute(job):
            """Log only error classes; never credential headers, bodies or source content."""
            try:
                await execute(job)
            except Exception as error:
                print("Relay request failed: " + type(error).__name__ + (f" HTTP {error.response.status_code} {error.request.url.path}" if isinstance(error,httpx.HTTPStatusError) else ""), flush=True)

        backoff = 1
        last_heartbeat = 0
        while True:
            try:
                if time.monotonic() - last_heartbeat > 5:
                    result = await remote.post("/__sherlock_relay/heartbeat")
                    result.raise_for_status()
                    last_heartbeat = time.monotonic()
                tasks = {t for t in tasks if not t.done()}
                if len(tasks) < 8:
                    result = await remote.post("/__sherlock_relay/pull")
                    result.raise_for_status()
                    for job in result.json().get("jobs", [])[:8]:
                        tasks.add(asyncio.create_task(safe_execute(job)))
                backoff = 1
                await asyncio.sleep(0.35)
            except Exception as error:
                print(
                    "Private access reconnecting: " + type(error).__name__, flush=True
                )
                await asyncio.sleep(backoff)
                backoff = min(15, backoff * 2)


def main():
    """Use secure environment bindings or retain the legacy hidden-stdin mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-env", action="store_true", help="Use secure runtime bindings; never prompt")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--check-only", action="store_true", help="Check credentials without taking queued work")
    operation.add_argument("--verify", action="store_true", help="Check the live remote frontend and ERPS API")
    args = parser.parse_args()
    try:
        if args.from_env:
            config = environment_config()
        else:
            original = termios.tcgetattr(sys.stdin) if sys.stdin.isatty() else None
            try:
                if original is not None:
                    hidden = list(original)
                    hidden[3] &= ~termios.ECHO
                    termios.tcsetattr(sys.stdin, termios.TCSANOW, hidden)
                print("Ready for private access configuration on hidden stdin", flush=True)
                config = validate_config(json.loads(sys.stdin.readline(16384)))
            except ValueError:
                raise AccessError("Invalid private access configuration") from None
            finally:
                if original is not None:
                    termios.tcsetattr(sys.stdin, termios.TCSANOW, original)
        if args.verify:
            print(json.dumps(verify_access(config)), flush=True)
            return
        preflight(config)
        if args.check_only:
            print(json.dumps({"status": "authenticated", "mailbox_changed": False}), flush=True)
            return
        (ROOT / "data").mkdir(exist_ok=True)
        with (ROOT / "data/private-site-access.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AccessError("An owned private relay is already running") from None
            pid = ROOT / "data/private-site-access.pid"
            pid.write_text(str(os.getpid()))
            def stop(*_):
                raise KeyboardInterrupt
            signal.signal(signal.SIGTERM, stop)
            print("Starting private workspace access; external verification is still required", flush=True)
            try:
                asyncio.run(relay(config))
            except KeyboardInterrupt:
                pass
            finally:
                pid.unlink(missing_ok=True)
    except AccessError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
