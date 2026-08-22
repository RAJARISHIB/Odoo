"""Password hashing and JWT issue/verify.

The access token is also what the Angular client hands to the Express websocket
server on connect, so the claim set below is the shared contract between all
three services (see `realtime/src/lib/auth.js`).
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password

from core.exceptions import AuthenticationError

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(raw_password: str) -> str:
    return make_password(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    if not raw_password or not hashed_password:
        return False
    return check_password(raw_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def _encode(claims: dict, ttl: timedelta, token_type: str) -> tuple:
    now = datetime.now(timezone.utc)
    expires_at = now + ttl
    jti = uuid.uuid4().hex
    payload = {
        **claims,
        "typ": token_type,
        "jti": jti,
        "iss": settings.JWT["ISSUER"],
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.JWT["SECRET"], algorithm=settings.JWT["ALGORITHM"])
    return token, jti, expires_at


def create_access_token(user) -> tuple:
    """Returns (token, jti, expires_at)."""
    claims = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.slug if getattr(user, "role", None) and not isinstance(user.role, str) else user.role,
        "org_id": str(user.organization.id) if user.organization else None,
        "name": user.full_name,
    }
    return _encode(claims, settings.JWT["ACCESS_TTL"], TOKEN_TYPE_ACCESS)


def create_refresh_token(user) -> tuple:
    return _encode({"sub": str(user.id)}, settings.JWT["REFRESH_TTL"], TOKEN_TYPE_REFRESH)


def decode_token(token: str, expected_type: str = TOKEN_TYPE_ACCESS) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT["SECRET"],
            algorithms=[settings.JWT["ALGORITHM"]],
            issuer=settings.JWT["ISSUER"],
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired.", code="token_expired")
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError(f"Invalid token: {exc}", code="token_invalid")

    if payload.get("typ") != expected_type:
        raise AuthenticationError(
            f"Expected a {expected_type} token.", code="token_wrong_type"
        )
    return payload


def extract_bearer_token(request) -> str:
    """Pull the raw token out of `Authorization: Bearer <token>`."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]
