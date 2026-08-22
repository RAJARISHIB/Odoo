"""Password hashing and JWT issue/verify.

The access token is also what the Angular client hands to the Express websocket
server on connect, so the claim set below is the shared contract between all
three services (see `realtime/src/lib/auth.js`).
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time as time_module
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password

from core.exceptions import AuthenticationError

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
TOKEN_TYPE_MFA_PENDING = "mfa_pending"


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


def create_access_token(user, *, reauth_at: datetime = None, session_jti: str = None) -> tuple:
    """Returns (token, jti, expires_at).

    `reauth_at` is when the caller last proved their password (+ MFA, if
    enabled) - defaults to "now" for an ordinary login. `step_up_required`
    (see `core.decorators`) reads it back to decide whether a sensitive
    action needs fresh credentials or can ride on the current session.
    `session_jti` is the paired refresh token's `jti`, carried along so the
    "active sessions" list can tell which row is the one the caller is using
    right now - see `apps.users.controllers.AuthController.sessions`.
    """
    claims = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.slug if getattr(user, "role", None) and not isinstance(user.role, str) else user.role,
        "org_id": str(user.organization.id) if user.organization else None,
        "name": user.full_name,
        "reauth_at": int((reauth_at or datetime.now(timezone.utc)).timestamp()),
        "sid": session_jti,
    }
    return _encode(claims, settings.JWT["ACCESS_TTL"], TOKEN_TYPE_ACCESS)


def create_refresh_token(user) -> tuple:
    return _encode({"sub": str(user.id)}, settings.JWT["REFRESH_TTL"], TOKEN_TYPE_REFRESH)


def create_mfa_pending_token(user) -> tuple:
    """A narrow, short-lived token good only for `POST /auth/mfa/verify` -
    minted after a correct password for an MFA-enabled account, instead of a
    full session. No role/org claims: nothing but the MFA-verify endpoint
    should ever accept this token type."""
    return _encode({"sub": str(user.id)}, timedelta(minutes=5), TOKEN_TYPE_MFA_PENDING)


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


# ---------------------------------------------------------------------------
# One-shot tokens (password reset, email verification).  Only the hash is
# ever stored; the raw value exists only in the email and the request that
# redeems it, same principle as `RefreshToken` storing a `jti` rather than a
# raw token.
# ---------------------------------------------------------------------------
def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# MFA - TOTP (RFC 6238) hand-rolled over stdlib hmac/hashlib, no auth library
# needed.  Recovery codes reuse the same password hasher as everything else.
# ---------------------------------------------------------------------------
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I - avoids transcription errors


def generate_totp_secret() -> str:
    """Base32 secret an authenticator app can scan/enter."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    padded = secret_b32.upper() + "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(padded)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return str(code_int).zfill(TOTP_DIGITS)


def verify_totp(secret_b32: str, code: str, *, window: int = 1) -> bool:
    """`window=1` accepts the previous/current/next 30s step, tolerating
    minor clock drift between server and phone."""
    code = (code or "").strip()
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    counter_now = int(time_module.time()) // TOTP_STEP_SECONDS
    return any(
        hmac.compare_digest(_hotp(secret_b32, counter_now + delta), code)
        for delta in range(-window, window + 1)
    )


def totp_uri(secret_b32: str, *, account_name: str, issuer: str = "Dayflow HRMS") -> str:
    """`otpauth://` URI an authenticator app understands, for the enrollment QR."""
    label = urllib.parse.quote("{}:{}".format(issuer, account_name))
    query = urllib.parse.urlencode(
        {"secret": secret_b32, "issuer": issuer, "algorithm": "SHA1",
         "digits": TOTP_DIGITS, "period": TOTP_STEP_SECONDS}
    )
    return "otpauth://totp/{}?{}".format(label, query)


def generate_recovery_codes(count: int = 10) -> list:
    """Raw, one-time MFA recovery codes like `XXXX-XXXX`.  Callers hash each
    with `hash_password` before storing - see `apps.users.models.User.mfa_recovery_codes`."""
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
        codes.append(raw[:4] + "-" + raw[4:])
    return codes


def extract_bearer_token(request) -> str:
    """Pull the raw token out of `Authorization: Bearer <token>`."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]
