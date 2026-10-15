"""Load optional user-owned provider configuration without persisting secrets in the case."""

import json
import os
from pathlib import Path

ALLOWED = {"BRAVE_SEARCH_API_KEY", "ANTHROPIC_API_KEY", "X_BEARER_TOKEN"}


def load(path=None):
    path = path or Path.home() / ".config/sherlock-osint/service-env.json"
    if not path.exists():
        return
    info = path.stat()
    if path.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError(
            "Provider configuration must be a user-owned regular file with mode 0600"
        )
    if not path.is_file() or info.st_size > 32000:
        raise RuntimeError("Invalid provider configuration file")
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        raise RuntimeError("Provider configuration JSON could not be read") from None
    if not isinstance(data, dict) or any(
        k not in ALLOWED or not isinstance(v, str) or len(v) > 8000
        for k, v in data.items()
    ):
        raise RuntimeError(
            "Provider configuration accepts only documented provider-key string fields"
        )
    for name, value in data.items():
        if value:
            os.environ.setdefault(name, value)
