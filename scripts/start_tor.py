"""Manually start an already installed native Tor client; never invoked by agents."""

import shutil
import subprocess
from pathlib import Path
from backend.onion import runtime_blocker


def main():
    blocker = runtime_blocker()
    if blocker:
        raise SystemExit(blocker)
    executable = shutil.which("tor")
    if not executable:
        raise SystemExit(
            "Native Tor is not installed. On macOS install the official Homebrew tor formula, or run Tor Browser and use its SOCKS port 9150."
        )
    root = Path(__file__).resolve().parents[1]
    profile = root / "data" / "tor-client"
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    profile.chmod(0o700)
    print(
        "Starting native Tor on 127.0.0.1:9050. Keep this process running for onion research."
    )
    return subprocess.call(
        [
            executable,
            "-f",
            "/dev/null",
            "--ClientOnly",
            "1",
            "--SocksPort",
            "127.0.0.1:9050",
            "--DataDirectory",
            str(profile),
            "--SafeLogging",
            "1",
            "--AvoidDiskWrites",
            "1",
            "--Log",
            "notice stdout",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
