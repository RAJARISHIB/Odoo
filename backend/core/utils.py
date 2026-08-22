"""Assorted helpers that are not specific to any one domain app."""
import json
import re
import secrets
import string
import uuid
from datetime import datetime, time, timezone

from core.exceptions import ValidationError


def new_request_id() -> str:
    return uuid.uuid4().hex


def parse_json_body(request) -> dict:
    """Decode a JSON request body into a dict.

    An empty body is an empty dict (handy for POST endpoints with no payload,
    such as check-in). Malformed JSON is a 422 rather than a 500.
    """
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("Request body must be valid JSON.", code="invalid_json")
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.", code="invalid_json")
    return data


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def user_agent(request) -> str:
    return request.META.get("HTTP_USER_AGENT", "")[:255]


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower())
    return value.strip("-")


def random_password(length: int = 12) -> str:
    """Temporary password for invited employees."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length)) + "1a"


def day_bounds(day) -> tuple:
    """UTC `(start, end)` datetimes covering a calendar date - for day queries."""
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end


def seconds_to_hours(seconds) -> float:
    return round((seconds or 0) / 3600.0, 2)


def round_leave(value) -> float:
    """Consistent 2dp rounding for leave-day quantities.

    Leave days are plain floats (0.5, 1.5, ...); every arithmetic result is
    passed through this before being stored or returned so accumulated
    additions never drift (`1.5 + 1.5` must stay `3.0`, not `3.0000000000000004`).
    """
    return round(float(value or 0), 2)


def deep_merge(base: dict, override: dict) -> dict:
    """Recursive dict merge - used for partial settings updates."""
    result = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
