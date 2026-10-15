"""Explicit SOCKS5h acquisition for public v3 onion documents. No clearnet fallback."""

import base64
import hashlib
import json
import re
import socket
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from fastapi import HTTPException
from pydantic import BaseModel


def validate_onion_url(url):
    p = urlparse(url)
    if (
        p.scheme not in ("http", "https")
        or p.username
        or p.password
        or p.port not in (None, 80, 443)
    ):
        raise ValueError(
            "Onion documents require HTTP(S), standard ports and no embedded credentials"
        )
    host = (p.hostname or "").lower()
    labels = host.split(".")
    if (
        len(labels) < 2
        or labels[-1] != "onion"
        or not re.fullmatch(r"[a-z2-7]{56}", labels[-2])
    ):
        raise ValueError("A valid v3 onion address is required")
    if any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels[:-2]
    ):
        raise ValueError("Invalid onion subdomain")
    raw = base64.b32decode(labels[-2].upper())
    key, checksum, version = raw[:32], raw[32:34], raw[34:]
    if (
        version != b"\x03"
        or checksum != hashlib.sha3_256(b".onion checksum" + key + version).digest()[:2]
    ):
        raise ValueError("Invalid v3 onion address checksum")
    return p


def validate_proxy(url):
    p = urlparse(url)
    if (
        p.scheme != "socks5h"
        or p.hostname not in ("127.0.0.1", "::1", "localhost")
        or not p.port
        or p.username
        or p.password
        or p.path not in ("", "/")
        or p.query
        or p.fragment
    ):
        raise ValueError(
            "Use a loopback SOCKS5h endpoint, e.g. socks5h://127.0.0.1:9050; remote DNS is mandatory"
        )
    return p


def runtime_blocker():
    path = Path("/etc/codex/network-policy.json")
    if not path.is_file():
        return None
    try:
        policy = json.loads(path.read_text())
        if policy.get("version") != 1:
            return "Managed network policy cannot be verified for Tor"
        grants = policy.get("tcp_network_access", {})
        if not grants.get("domains") and not grants.get("ip_ranges"):
            return "Managed environment has no TCP grants for Tor relays. Live onion acquisition is blocked here; configure native Tor on a permitted local machine."
        # Partial grants cannot authorize an arbitrary Tor relay circuit.
        if "0.0.0.0/0" not in grants.get("ip_ranges", []):
            return (
                "Managed TCP grants do not establish permission for a Tor relay network"
            )
    except (OSError, ValueError):
        return "Managed network policy could not be verified for Tor"
    return None


class TorConfig(BaseModel):
    enabled: bool = True
    proxy: str = "socks5h://127.0.0.1:9050"


def install(core):
    core.execute(
        "CREATE TABLE IF NOT EXISTS tor_config(id INTEGER PRIMARY KEY,enabled INTEGER,proxy TEXT)"
    )
    core.execute(
        "INSERT OR IGNORE INTO tor_config VALUES(1,0,'socks5h://127.0.0.1:9050')"
    )

    def settings():
        return core.rows("SELECT * FROM tor_config WHERE id=1")[0]

    def status():
        config = settings()
        blocker = runtime_blocker()
        result = {
            "proxy": config["proxy"],
            "enabled": bool(config["enabled"]),
            "ready": False,
            "remote_dns": True,
            "fallback": "NEVER",
            "browser": "Preserved document reader; no downloaded JavaScript execution",
            "privacy": "Tor transport does not provide the full fingerprinting protections of Tor Browser",
        }
        if blocker:
            return {**result, "state": "BLOCKED_NETWORK_POLICY", "reason": blocker}
        if not config["enabled"]:
            return {
                **result,
                "state": "NOT CONFIGURED",
                "reason": "Enable a native Tor or Tor Browser loopback SOCKS endpoint",
            }
        try:
            p = validate_proxy(config["proxy"])
            with socket.create_connection(
                (p.hostname, p.port), timeout=2
            ) as connection:
                connection.sendall(b"\x05\x01\x00")
                if connection.recv(2) != b"\x05\x00":
                    raise ValueError("Endpoint is not an unauthenticated SOCKS5 proxy")
            return {
                **result,
                "state": "SOCKS READY",
                "ready": True,
                "reason": "Local SOCKS5 handshake succeeded; individual onion reachability is checked during acquisition",
            }
        except (OSError, ValueError) as e:
            return {**result, "state": "UNAVAILABLE", "reason": str(e)}

    def require():
        blocker = runtime_blocker()
        if blocker:
            raise ValueError(blocker)
        config = settings()
        if not config["enabled"]:
            raise ValueError("Tor is not enabled; no onion request was sent")
        validate_proxy(config["proxy"])
        return config

    def fetch(url):
        validate_onion_url(url)
        config = require()
        # Explicit proxy overrides environment HTTP proxies. Hostnames remain
        # domain names in the SOCKS request, including redirects and robots.txt.
        with httpx.Client(
            proxy=config["proxy"],
            trust_env=False,
            timeout=60,
            follow_redirects=False,
            headers=core.CLIENT_HEADERS,
        ) as client:
            for _ in range(6):
                validate_onion_url(url)
                with client.stream("GET", url) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        url = str(response.url.join(response.headers["location"]))
                        validate_onion_url(
                            url
                        )  # clearnet/private redirect is rejected before any connection
                        continue
                    response.raise_for_status()
                    if (
                        int(response.headers.get("content-length", "0"))
                        > core.MAX_BYTES
                    ):
                        raise ValueError("Onion document exceeds the file-size limit")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > core.MAX_BYTES:
                            raise ValueError(
                                "Onion document exceeds the file-size limit"
                            )
                        chunks.append(chunk)
                    core.log(
                        "tor_fetch",
                        {
                            "url": url,
                            "status": response.status_code,
                            "bytes": size,
                            "remote_dns": True,
                        },
                    )
                    return (
                        b"".join(chunks),
                        url,
                        dict(response.headers),
                        response.status_code,
                    )
            raise ValueError("Too many onion redirects")

    def robots(url):
        p = validate_onion_url(url)
        try:
            data, _, _, _ = fetch(f"{p.scheme}://{p.netloc}/robots.txt")
            parser = RobotFileParser()
            parser.parse(data.decode("utf-8", "replace").splitlines())
            if not parser.can_fetch("SherlockOSINT", url):
                raise ValueError("Onion site's robots.txt disallows acquisition")
        except httpx.HTTPStatusError as e:
            if not 400 <= e.response.status_code < 500:
                raise ValueError(
                    "Onion access policy is unavailable; acquisition stopped"
                ) from e

    @core.app.get("/api/onion/status")
    def tor_status():
        return status()

    @core.app.post("/api/onion/config")
    def configure(value: TorConfig):
        try:
            validate_proxy(value.proxy)
        except ValueError as e:
            raise HTTPException(422, str(e))
        core.execute(
            "UPDATE tor_config SET enabled=?,proxy=? WHERE id=1",
            (int(value.enabled), value.proxy),
        )
        core.log("tor_configured", {"enabled": value.enabled, "proxy": value.proxy})
        return status()

    return {"fetch": fetch, "robots": robots, "status": status, "require": require}
