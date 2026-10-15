"""Create local private service secrets; never print credentials or overwrite existing ones."""

import json
import os
import secrets
from pathlib import Path
from cryptography.fernet import Fernet

root = Path(__file__).resolve().parents[1]
private = root / "data/foundation-secrets"
private.mkdir(mode=0o700, parents=True, exist_ok=True)
env = root / "data/foundation.env"
if not env.exists():
    pg = secrets.token_hex(24)
    redis_password = secrets.token_hex(24)
    values = {
        "DATABASE_URL": f"postgresql+psycopg://sherlock:{pg}@127.0.0.1:55432/sherlock",
        "CELERY_BROKER_URL": f"redis://:{redis_password}@127.0.0.1:56379/0",
        "CELERY_RESULT_BACKEND": f"redis://:{redis_password}@127.0.0.1:56379/1",
        "JWT_SECRET": secrets.token_hex(48),
        "TOTP_KEY": Fernet.generate_key().decode(),
        "CORE_URL": "http://127.0.0.1:8000",
        "GATEWAY_SECURE_COOKIES": "false",
        "CORE_TOKEN": secrets.token_hex(32),
    }
    env.write_text("\n".join(k + "=" + v for k, v in values.items()) + "\n")
    env.chmod(0o600)
    (private / "postgres_password").write_text(pg)
    (private / "postgres_password").chmod(0o600)
    (private / "redis.conf").write_text(
        f"bind 0.0.0.0\nprotected-mode yes\nrequirepass {redis_password}\nappendonly yes\nappendfsync everysec\nmaxmemory 128mb\nmaxmemory-policy noeviction\n"
    )
    (private / "redis.conf").chmod(0o600)
    compose = {
        "POSTGRES_PASSWORD": pg,
        "REDIS_PASSWORD": redis_password,
        "JWT_SECRET": values["JWT_SECRET"],
        "TOTP_KEY": values["TOTP_KEY"],
        "ELASTIC_PASSWORD": secrets.token_hex(24),
        "CORE_TOKEN": values["CORE_TOKEN"],
        "SHERLOCK_UID": str(os.getuid()),
        "SHERLOCK_GID": str(os.getgid()),
    }
    p = root / "data/foundation-compose.env"
    p.write_text("\n".join(k + "=" + v for k, v in compose.items()) + "\n")
    p.chmod(0o600)
(root / "data/foundation-redis").mkdir(mode=0o700, exist_ok=True)
print(
    json.dumps(
        {
            "private_environment_path": str(env),
            "private_secrets_directory": str(private),
            "credentials_printed": False,
        }
    )
)
