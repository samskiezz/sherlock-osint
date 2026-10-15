"""Outbound-only private Sites relay; credentials stay in process memory.

Only the fixed authenticated local gateway is reachable. This process does not
accept arbitrary upstream hosts, run shell commands, or expose the Docker API.
"""

import asyncio
import fcntl
import json
import os
from pathlib import Path
import sys
import termios
import time
from urllib.parse import quote, urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT = 32 * 1024 * 1024
MAX_OUTPUT = 256 * 1024 * 1024
LOCAL = "http://127.0.0.1:8010"
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
    parsed = urlsplit(config["url"])
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".chatgpt.site")
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Expected the exact private Sites HTTPS origin")
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
    """Accept runtime credentials on hidden stdin and keep a single owned relay running."""
    if sys.stdin.isatty():
        attributes = termios.tcgetattr(sys.stdin)
        attributes[3] &= ~termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSANOW, attributes)
    print("Ready for private access configuration on hidden stdin", flush=True)
    config = json.loads(sys.stdin.readline())
    lock = (ROOT / "data/private-site-access.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    (ROOT / "data/private-site-access.pid").write_text(str(os.getpid()))
    print("Starting private workspace access", flush=True)
    try:
        asyncio.run(relay(config))
    except KeyboardInterrupt:
        pass
    finally:
        (ROOT / "data/private-site-access.pid").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
