"""Prepare private ERPS credentials and a dedicated database; never print values."""
import json
import os
from pathlib import Path
import secrets
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def ensure_database(admin_url, target_url):
    """Resume provisioning from saved credentials without rotating existing roles."""
    import psycopg
    from psycopg import sql
    from urllib.parse import urlsplit, unquote

    admin, target = urlsplit(admin_url), urlsplit(target_url)
    if (admin.hostname, admin.port or 5432) == (target.hostname, target.port or 5432):
        username = unquote(target.username or "")
        password = unquote(target.password or "")
        database = unquote(target.path.lstrip("/"))
        if not username or not password or not database:
            raise RuntimeError("Database credentials and database name are required")
        with psycopg.connect(admin_url, autocommit=True) as c:
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (username,)).fetchone():
                c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(username), sql.Literal(password)))
            if not c.execute("SELECT 1 FROM pg_database WHERE datname=%s", (database,)).fetchone():
                c.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(username)))
    with psycopg.connect(target_url) as c:
        c.execute("SELECT 1")


def main():
    import psycopg
    from foundation import config

    admin_url = config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    path = ROOT / "data/erps.json"
    if path.exists():
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise RuntimeError("ERPS config must be a regular private file (0600)")
        data = json.loads(path.read_text())
    else:
        password = secrets.token_hex(32)
        from urllib.parse import urlsplit, urlunsplit

        parsed = urlsplit(admin_url)
        with psycopg.connect(admin_url, autocommit=True) as c:
            if c.execute("SELECT 1 FROM pg_roles WHERE rolname='erps_app'").fetchone():
                raise RuntimeError("Existing erps_app role has no matching private config; refusing to rotate it")
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
    ensure_database(admin_url, data["ERPS_DATABASE_URL"])
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
