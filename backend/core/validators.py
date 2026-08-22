"""Input validation helpers used by `BaseController` and the services layer.

Everything here raises `core.exceptions.ValidationError`, so failures surface as
a 422 with a per-field `details` map the Angular forms can bind to directly.
"""
import re
from datetime import date, datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from core.exceptions import ValidationError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{7,20}$")

MIN_PASSWORD_LENGTH = 8


def require_fields(data: dict, fields) -> dict:
    """Assert every name in `fields` is present and non-empty."""
    missing = {}
    for field in fields:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing[field] = "This field is required."
    if missing:
        raise ValidationError("Missing required fields.", details=missing)
    return data


def validate_email(value: str, field: str = "email") -> str:
    value = (value or "").strip().lower()
    if not EMAIL_RE.match(value):
        raise ValidationError(
            "Invalid email address.", details={field: "Enter a valid email address."}
        )
    return value


def validate_phone(value: str, field: str = "phone") -> str:
    value = (value or "").strip()
    if value and not PHONE_RE.match(value):
        raise ValidationError(
            "Invalid phone number.", details={field: "Enter a valid phone number."}
        )
    return value


def validate_password(value: str, field: str = "password") -> str:
    """Baseline strength: length, at least one letter and one digit."""
    value = value or ""
    problems = []
    if len(value) < MIN_PASSWORD_LENGTH:
        problems.append("Must be at least {} characters.".format(MIN_PASSWORD_LENGTH))
    if not re.search(r"[A-Za-z]", value):
        problems.append("Must contain a letter.")
    if not re.search(r"\d", value):
        problems.append("Must contain a number.")
    if problems:
        raise ValidationError("Password is too weak.", details={field: " ".join(problems)})
    return value


def validate_choice(value, choices, field: str = "value"):
    if value not in choices:
        allowed = ", ".join(str(choice) for choice in choices)
        raise ValidationError(
            "Invalid value for '{}'.".format(field),
            details={field: "Must be one of: {}.".format(allowed)},
        )
    return value


def validate_object_id(value, field: str = "id") -> str:
    try:
        ObjectId(str(value))
    except (InvalidId, TypeError):
        raise ValidationError("Invalid identifier.", details={field: "Not a valid id."})
    return str(value)


def parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_int(value, default=None, field: str = "value"):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError("Expected a number.", details={field: "Must be an integer."})


def parse_date(value, field: str = "date"):
    """Accepts `YYYY-MM-DD` and returns a `date`."""
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("Invalid date.", details={field: "Use the format YYYY-MM-DD."})


def parse_datetime(value, field: str = "timestamp"):
    """Accepts ISO-8601 (with or without a trailing Z), returns tz-aware UTC."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError("Invalid timestamp.", details={field: "Use an ISO-8601 timestamp."})
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def pick(data: dict, fields) -> dict:
    """Subset of `data` limited to `fields`, skipping keys that were not sent.

    Used to build partial-update payloads without clobbering absent fields.
    """
    return {key: data[key] for key in fields if key in data}
