"""Argon2 passwords, HS256 JWTs, persisted role checks and replay-resistant TOTP."""

import time
import uuid
from pathlib import Path
from typing import Any
import casbin
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from authlib.jose import JsonWebToken
from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
from sqlalchemy import select
from . import config
from .models import Session, User

passwords = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
jwt = JsonWebToken(["HS256"])
policy = casbin.Enforcer(
    str(Path(__file__).with_name("rbac_model.conf")),
    str(Path(__file__).with_name("rbac_policy.csv")),
)
DUMMY_HASH = passwords.hash("timing-control-" + uuid.uuid4().hex)


def issue(user: User) -> str:
    """Issue a short-lived access token, including revocation version and audience."""
    if len(config.SECRET) < 32:
        raise RuntimeError("JWT_SECRET must have at least 32 characters")
    now = int(time.time())
    return jwt.encode(
        {"alg": "HS256"},
        {
            "sub": user.id,
            "ver": user.token_version,
            "iat": now,
            "exp": now + 900,
            "iss": "sherlock-foundation",
            "aud": "sherlock-gateway",
        },
        config.SECRET,
    ).decode()


def authenticate(request: Request) -> User:
    """Validate the access token and reload active role/version from the database."""
    bearer = request.headers.get("authorization", "")
    token = (
        bearer[7:]
        if bearer.startswith("Bearer ")
        else request.cookies.get("sherlock_access")
    )
    if not token:
        raise HTTPException(401, "Authentication required")
    try:
        claims = jwt.decode(
            token,
            config.SECRET,
            claims_options={
                "exp": {"essential": True},
                "sub": {"essential": True},
                "iss": {"essential": True, "value": "sherlock-foundation"},
                "aud": {"essential": True, "value": "sherlock-gateway"},
            },
        )
        claims.validate()
        with Session() as s:
            user = s.get(User, claims["sub"])
            if not user or not user.active or user.token_version != claims.get("ver"):
                raise ValueError("Revoked")
            request.state.actor_id = user.id
            return user
    except Exception as ex:
        raise HTTPException(401, "Invalid or expired access token") from ex


def require(request: Request, resource: str, action: str) -> User:
    """Enforce current Casbin role permissions."""
    user = authenticate(request)
    if not policy.enforce(user.role, resource, action):
        raise HTTPException(403, "Role does not permit this operation")
    return user


def check_password(user: User | None, value: str) -> bool:
    """Verify Argon2 with a dummy hash for nonexistent accounts."""
    try:
        return passwords.verify(
            user.password_hash if user else DUMMY_HASH, value
        ) and bool(user)
    except (VerifyMismatchError, InvalidHashError):
        return False


def check_totp(user: User, code: str) -> bool:
    """Consume a valid TOTP time step once; caller must hold a user row lock."""
    if not user.totp_seed or not code.isdigit() or len(code) != 6:
        return False
    seed = Fernet(config.TOTP_KEY.encode()).decrypt(user.totp_seed.encode()).decode()
    now = int(time.time())
    otp = pyotp.TOTP(seed)
    for counter in (now // 30 - 1, now // 30, now // 30 + 1):
        if counter > user.totp_last_counter and __import__("hmac").compare_digest(
            otp.at(counter * 30), code
        ):
            user.totp_last_counter = counter
            return True
    return False
