"""Password hashing (Argon2id), JWT access tokens, opaque refresh tokens."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import Unauthorized

_hasher = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)  # OWASP-ish, fast enough for API use


def hash_password(plain: str) -> str:
    _validate_password_strength(plain)
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:  # malformed hash must never 500 the login endpoint
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except Exception:
        return False


def _validate_password_strength(pw: str) -> None:
    from app.core.errors import ValidationFailed

    if len(pw) < settings.PASSWORD_MIN_LENGTH:
        raise ValidationFailed(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters")
    classes = sum(bool(x) for x in (
        any(c.islower() for c in pw), any(c.isupper() for c in pw),
        any(c.isdigit() for c in pw), any(not c.isalnum() for c in pw)))
    if classes < 3:
        raise ValidationFailed("Password must mix lower case, upper case, digits or symbols (3 of 4)")


def create_access_token(*, user_id: str, org_id: str | None, role: str, sid: str,
                        extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(org_id) if org_id else None,
        "role": role,
        "sid": str(sid),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MIN)).timestamp()),
        "typ": "access",
        "iss": "nextgen-ai",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG],
                             options={"require": ["exp", "sub", "iss"]})
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Session expired", code="token_expired") from None
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid token", code="token_invalid") from None
    if payload.get("typ") != "access":
        raise Unauthorized("Invalid token type", code="token_invalid")
    return payload


# ---- opaque secrets (refresh tokens, link codes, reset tokens) ----------
def new_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_opaque_token(token: str) -> str:
    """Store only the digest; a DB leak must not yield usable tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_link_code() -> str:
    """Human-typable, 8 chars, no ambiguous glyphs (Uzbek/Russian friendly)."""
    alphabet = "ACDEFGHJKLMNPQRTUVWXY34679"
    return "".join(secrets.choice(alphabet) for _ in range(8))
