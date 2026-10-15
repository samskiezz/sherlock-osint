"""Install a reviewed native user service; generate-only works on other platforms."""

import argparse, os, plistlib, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mac_plist(root=ROOT, full_platform=False):
    return {
        "Label": "local.sherlock-osint",
        "ProgramArguments": [
            str(root / ".venv/bin/python"),
            str(root / "scripts/run_platform.py"),
            "--services",
        ]
        if full_platform
        else [str(root / "start.sh")],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "SHERLOCK_DATA": str(root / "data"),
        },
        "StandardOutPath": str(root / "data/service.log"),
        "StandardErrorPath": str(root / "data/service-error.log"),
        "ProcessType": "Background",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate-only", type=Path)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument(
        "--full-platform",
        action="store_true",
        help="Supervise the core, bridge and configured Compose services",
    )
    args = parser.parse_args()
    if args.generate_only:
        args.generate_only.write_bytes(
            plistlib.dumps(mac_plist(full_platform=args.full_platform))
        )
        print("Generated launchd plist; not installed.")
        return
    if sys.platform != "darwin":
        raise SystemExit(
            "Native launchd installation requires macOS. Use --generate-only to inspect the configuration."
        )
    if (
        not (ROOT / ".venv/bin/python").is_file()
        or not (ROOT / "frontend/dist/index.html").is_file()
    ):
        raise SystemExit("Run ./setup.sh first.")
    dest = Path.home() / "Library/LaunchAgents/local.sherlock-osint.plist"
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = f"gui/{os.getuid()}/local.sherlock-osint"
    if args.uninstall:
        subprocess.run(["launchctl", "bootout", target], check=False)
        dest.unlink(missing_ok=True)
        print("Uninstalled SHERLOCK service; evidence retained.")
        return
    (ROOT / "data").mkdir(exist_ok=True)
    dest.write_bytes(plistlib.dumps(mac_plist(full_platform=args.full_platform)))
    dest.chmod(0o600)
    subprocess.run(["launchctl", "bootout", target], check=False)
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(dest)], check=True
    )
    subprocess.run(["launchctl", "enable", target], check=True)
    print(
        "Installed user launchd service. Collection runs while the Mac is awake and Docker is available. http://127.0.0.1:8010 for the full platform; :8000 for core-only mode"
    )


if __name__ == "__main__":
    main()
