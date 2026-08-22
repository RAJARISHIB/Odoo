"""Login ID generation.

Every person who can sign in gets a system-generated login ID.  Nobody types it
in, and it is never editable:

    [OI][JODO][2022][0001]
     |    |     |     |
     |    |     |     +-- serial number of joining, within that org and year
     |    |     +-------- year of joining
     |    +-------------- first two letters of first name + of last name
     +------------------- organization code

    OIJODO20220001  ->  Odoo India / John Doe / joined 2022 / 1st joiner of 2022

The same routine serves both paths that create an account: organization signup,
and an HR officer or admin adding an employee.
"""
import re

SERIAL_WIDTH = 4
FILLER = "X"


def organization_code(name: str) -> str:
    """Two-letter code for an organization.

    Multi-word names use the initials of the first two words ("Odoo India" ->
    "OI"); single-word names use their first two letters ("Acme" -> "AC").
    """
    words = [word for word in re.split(r"[^A-Za-z0-9]+", name or "") if word]
    if not words:
        return "XX"
    if len(words) >= 2:
        code = words[0][0] + words[1][0]
    else:
        code = words[0][:2]
    return _pad(code.upper(), 2)


def name_segment(first_name: str, last_name: str = "") -> str:
    """Four letters: two from the first name, two from the last.

    A person with no last name on file still needs four letters, so the first
    name supplies its next two characters, padded with X when it is too short.
    """
    first = _letters(first_name)
    last = _letters(last_name)

    head = _pad(first[:2], 2)
    if last:
        tail = _pad(last[:2], 2)
    else:
        tail = _pad(first[2:4], 2)
    return (head + tail).upper()


def build_login_id(org_code: str, first_name: str, last_name: str, year: int, serial: int) -> str:
    return "{}{}{}{}".format(
        org_code.upper(),
        name_segment(first_name, last_name),
        year,
        str(serial).zfill(SERIAL_WIDTH),
    )


def generate_login_id(organization, first_name: str, last_name: str, joining_date=None) -> str:
    """Allocate the next free login ID for a new member of `organization`.

    The serial is the count of people who joined that organization in that year,
    plus one.  Should that ID already exist - a race, or a restored record - the
    serial walks forward until it is free, so the value is always unique.
    """
    from apps.users.models import User

    year = (joining_date.year if joining_date else _current_year())
    org_code = organization.code or organization_code(organization.name)

    year_start, year_end = _year_bounds(year)
    serial = (
        User.objects.filter(
            organization=organization,
            date_of_joining__gte=year_start,
            date_of_joining__lte=year_end,
        ).count()
        + 1
    )

    candidate = build_login_id(org_code, first_name, last_name, year, serial)
    while User.objects.filter(login_id=candidate).first():
        serial += 1
        candidate = build_login_id(org_code, first_name, last_name, year, serial)
    return candidate


def split_full_name(full_name: str) -> tuple:
    """Split a single "Name" field into (first, last).

    The signup form collects one name, but the login ID needs both halves, so
    the first token is the first name and everything after it is the last name.
    """
    parts = [part for part in (full_name or "").strip().split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _letters(value: str) -> str:
    return re.sub(r"[^A-Za-z]", "", value or "")


def _pad(value: str, width: int) -> str:
    return (value + FILLER * width)[:width]


def _current_year() -> int:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).year


def _year_bounds(year: int) -> tuple:
    from datetime import datetime, timezone

    return (
        datetime(year, 1, 1, tzinfo=timezone.utc),
        datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
    )
