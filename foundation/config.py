"""Private environment configuration, never exported in API responses."""

import os
from pathlib import Path

KEYS = {
    "DATABASE_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "JWT_SECRET",
    "TOTP_KEY",
    "CORE_URL",
    "CORE_TOKEN",
    "GATEWAY_SECURE_COOKIES",
}
CONFIG_FILE = Path(
    os.environ.get(
        "SHERLOCK_FOUNDATION_ENV",
        Path(__file__).resolve().parents[1] / "data/foundation.env",
    )
)
if CONFIG_FILE.exists():
    if CONFIG_FILE.is_symlink() or CONFIG_FILE.stat().st_mode & 0o077:
        raise RuntimeError("Foundation secrets file must be regular and mode 0600")
    for line in CONFIG_FILE.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key in KEYS:
            os.environ.setdefault(key, value)
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("Configure DATABASE_URL before starting the foundation")
BROKER = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", BROKER)
CORE_URL = os.environ.get("CORE_URL", "http://127.0.0.1:8000").rstrip("/")
SECRET = os.environ.get("JWT_SECRET", "")
TOTP_KEY = os.environ.get("TOTP_KEY", "")
SECURE_COOKIES = os.environ.get("GATEWAY_SECURE_COOKIES", "false").lower() == "true"

CORE_TOKEN = os.environ.get("CORE_TOKEN", "")
CORE_HEADERS = {"X-Sherlock-Core-Token": CORE_TOKEN} if CORE_TOKEN else {}
CORE_PROXY_TIMEOUT = max(120, min(600, int(os.environ.get("SHERLOCK_CORE_PROXY_TIMEOUT", "300"))))
