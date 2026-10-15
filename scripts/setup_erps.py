"""Prepare private ERPS credentials and a dedicated database; never print values."""
import json
import os
from pathlib import Path
import secrets
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import psycopg
    from psycopg import sql
    from foundation import config

    path = ROOT / "data/erps.json"
    if path.exists():
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise RuntimeError("ERPS config must be a regular private file (0600)")
        data = json.loads(path.read_text())
    else:
        password = secrets.token_hex(32)
        from urllib.parse import urlsplit, urlunsplit

        url = config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        parsed = urlsplit(url)
        with psycopg.connect(url, autocommit=True) as c:
            if c.execute("SELECT 1 FROM pg_roles WHERE rolname='erps_app'").fetchone():
                raise RuntimeError("Existing erps_app role has no matching private config; refusing to rotate it")
            c.execute(sql.SQL("CREATE ROLE erps_app LOGIN PASSWORD {}").format(sql.Literal(password)))
            c.execute("CREATE DATABASE erps OWNER erps_app")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5432
        data = {
            "ERPS_DATABASE_URL": urlunsplit(("postgresql", f"erps_app:{password}@{host}:{port}", "/erps", "", "")),
            "ERPS_TOKEN": secrets.token_hex(32),
            "ERPS_READER_TOKEN": secrets.token_hex(32),
            "ERPS_WRITER_TOKEN": secrets.token_hex(32),
            "ERPS_WORKSPACE": str(uuid.uuid4()),
            "ERPS_URL": "http://127.0.0.1:3000",
        }
        path.parent.mkdir(exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
    with psycopg.connect(data["ERPS_DATABASE_URL"]) as c:
        c.execute("SELECT 1")
    from urllib.parse import urlsplit, urlunsplit
    from urllib.parse import unquote
    parts = urlsplit(data["ERPS_DATABASE_URL"])
    compose = dict(data, ERPS_DATABASE_URL=urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@",1)[0]+"@postgres:5432")))
    compose["ERPS_BIND"] = "0.0.0.0:3000"
    generated = {
        ROOT / "data/erps-compose.env": "\n".join(k+"="+v for k,v in compose.items())+"\n",
        ROOT / "data/erps-compose-db-password": unquote(parts.password or ""),
    }
    for target, content in generated.items():
        if not target.exists():
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd,"w") as f:
                f.write(content)
        elif target.is_symlink() or target.stat().st_mode & 0o077:
            raise RuntimeError("Compose secret files must be regular and private")
    print(json.dumps({"database_ready": True, "private_config": str(path), "credentials_printed": False}))


if __name__ == "__main__":
    main()
