import time
import uuid
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import Settings

ALGORITHM = "HS256"
ISSUER = "researchops"

_hasher = PasswordHasher()
# Verified when an email is unknown, so response time does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash("researchops-timing-placeholder")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        matched = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return matched and password_hash is not None


def create_access_token(settings: Settings, user_id: str) -> str:
    now = int(time.time())
    return _encode(
        settings,
        {"sub": user_id, "type": "access", "iat": now, "exp": now + settings.access_token_minutes * 60},
    )


def create_refresh_token(settings: Settings, user_id: str, family_id: str) -> tuple[str, str, int]:
    """Return the signed token, its id, and its expiry."""
    now = int(time.time())
    jti = uuid.uuid4().hex
    expires_at = now + settings.refresh_token_days * 86_400
    token = _encode(
        settings,
        {"sub": user_id, "type": "refresh", "jti": jti, "fam": family_id, "iat": now, "exp": expires_at},
    )
    return token, jti, expires_at


def decode_token(settings: Settings, token: str, expected_type: Literal["access", "refresh"]) -> dict[str, Any] | None:
    """Return validated claims, or None for any invalid, expired, or wrong-type token."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    return claims if claims.get("type") == expected_type else None


def _encode(settings: Settings, claims: dict[str, Any]) -> str:
    return jwt.encode({**claims, "iss": ISSUER}, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)
