"""Password hashing and JWT issuing/verification.

Passwords are stored as PBKDF2-HMAC-SHA256 hashes with a per-user random salt,
using only the Python standard library (no native build step required).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt

from .config import settings
from .utils import utcnow

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS
    ).hex()
    return f"{_ALGORITHM}${_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = (stored or "").split("$")
        if algorithm != _ALGORITHM:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, AttributeError):
        return False


def create_access_token(subject: str, role: str, name: str) -> tuple[str, int]:
    """Return ``(token, expires_in_seconds)``."""
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    expires_at = utcnow() + expires_delta
    payload = {
        "sub": subject,
        "role": role,
        "name": name,
        "iat": int(utcnow().timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(
        payload, settings.effective_jwt_secret, algorithm=settings.jwt_algorithm
    )
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            settings.effective_jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError:
        return None


def create_reset_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "scope": "password_reset",
        "exp": int((utcnow() + timedelta(minutes=15)).timestamp()),
    }
    return jwt.encode(
        payload, settings.effective_jwt_secret, algorithm=settings.jwt_algorithm
    )


def decode_reset_token(token: str) -> str | None:
    payload = decode_access_token(token)
    if not payload or payload.get("scope") != "password_reset":
        return None
    return payload.get("sub")
