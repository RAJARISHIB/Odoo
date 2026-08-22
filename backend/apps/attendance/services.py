"""Attendance business logic: punches, day roll-ups and reporting.

One `Attendance` document per user per calendar day holds a list of
check-in/check-out sessions, so a punch mutates an existing document rather than
appending rows.
"""
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.attendance.models import Attendance, WorkSession
from apps.users.models import User
from core.constants import AttendanceSource, AttendanceStatus
from core.exceptions import Conflict, NotFound, ValidationError
from core.validators import parse_date, parse_datetime, validate_choice

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def org_timezone(organization) -> ZoneInfo:
    try:
        return ZoneInfo(organization.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Unknown timezone %s, falling back to UTC", organization.timezone)
        return ZoneInfo("UTC")


def today_for(organization) -> date:
    """The current calendar date in the organization's own timezone."""
    return datetime.now(org_timezone(organization)).date()


def day_key(day: date) -> datetime:
    """Normalise a date to midnight UTC - the stored `Attendance.date` value."""
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _expected_start(organization, day: date) -> datetime:
    """Shift start for `day`, as a UTC datetime."""
    hour, minute = (organization.work_start_time or "09:30").split(":")
    local = datetime.combine(day, time(int(hour), int(minute)), tzinfo=org_timezone(organization))
    return local.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Punches
# ---------------------------------------------------------------------------
def get_or_create_day(user: User, day: date = None) -> Attendance:
    day = day or today_for(user.organization)
    key = day_key(day)

    record = Attendance.objects.filter(
        organization=user.organization, user=user, date=key, is_deleted=False
    ).first()
    if record:
        return record

    return Attendance(
        organization=user.organization,
        user=user,
        date=key,
        status=AttendanceStatus.PRESENT,
    ).save()


def check_in(user: User, *, source: str = AttendanceSource.WEB, note: str = None,
             location: dict = None, ip_address: str = "", user_agent: str = "") -> Attendance:
    """Open a work session for today.  Rejected if one is already open."""
    validate_choice(source, AttendanceSource.ALL, "source")
    record = get_or_create_day(user)

    if record.is_checked_in:
        raise Conflict("You are already checked in.", code="already_checked_in")

    now = datetime.now(timezone.utc)
    record.sessions.append(
        WorkSession(
            check_in=now,
            source=source,
            note=note,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
        )
    )

    # Lateness is judged on the first punch of the day only.
    if len(record.sessions) == 1:
        expected = _expected_start(user.organization, today_for(user.organization))
        grace = timedelta(minutes=user.organization.late_grace_minutes or 0)
        if now > expected + grace:
            record.late_minutes = int((now - expected).total_seconds() // 60)
            record.status = AttendanceStatus.LATE
        else:
            record.status = AttendanceStatus.PRESENT

    if location:
        record.location = location

    record.recalculate().save()
    return record


def check_out(user: User, *, note: str = None) -> Attendance:
    """Close the open work session and refresh the day's totals."""
    record = Attendance.objects.filter(
        organization=user.organization, user=user,
        date=day_key(today_for(user.organization)), is_deleted=False,
    ).first()

    if not record or not record.is_checked_in:
        raise Conflict("You are not currently checked in.", code="not_checked_in")

    session = record.open_session
    session.check_out = datetime.now(timezone.utc)
    if note:
        session.note = note

    record.recalculate()
    _apply_day_status(record, user.organization)
    record.save()
    return record


def _apply_day_status(record: Attendance, organization):
    """Downgrade to half-day when the worked total falls short of policy."""
    if record.status in (AttendanceStatus.ON_LEAVE, AttendanceStatus.HOLIDAY):
        return record

    worked_hours = record.total_seconds / 3600.0
    full_day = organization.full_day_hours or 8
    half_day = organization.half_day_hours or 4

    if worked_hours >= full_day:
        record.overtime_seconds = int(max(0, record.total_seconds - full_day * 3600))
        if record.status != AttendanceStatus.LATE:
            record.status = AttendanceStatus.PRESENT
    elif worked_hours >= half_day:
        record.status = AttendanceStatus.HALF_DAY
    return record


def current_status(user: User) -> dict:
    """What the user panel's check-in widget renders on load."""
    day = today_for(user.organization)
    record = Attendance.objects.filter(
        organization=user.organization, user=user, date=day_key(day), is_deleted=False
    ).first()

    if not record:
        return {
            "date": day.isoformat(),
            "is_checked_in": False,
            "status": None,
            "total_hours": 0,
            "sessions": [],
            "attendance": None,
        }

    return {
        "date": day.isoformat(),
        "is_checked_in": record.is_checked_in,
        "status": record.status,
        "total_hours": record.total_hours,
        "sessions": [session.to_dict() for session in record.sessions],
        "attendance": record.to_dict(),
    }


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def list_attendance(organization, *, user=None, date_from=None, date_to=None, status=None):
    """Tenant-scoped attendance queryset with the usual admin filters."""
    queryset = Attendance.objects.filter(organization=organization, is_deleted=False)

    if user is not None:
        queryset = queryset.filter(user=user)
    if date_from:
        queryset = queryset.filter(date__gte=day_key(parse_date(date_from, "date_from")))
    if date_to:
        queryset = queryset.filter(date__lte=day_key(parse_date(date_to, "date_to")))
    if status:
        queryset = queryset.filter(status=validate_choice(status, AttendanceStatus.ALL, "status"))

    return queryset.order_by("-date")


def get_record(organization, record_id: str) -> Attendance:
    record = Attendance.objects.filter(
        id=record_id, organization=organization, is_deleted=False
    ).first()
    if not record:
        raise NotFound("Attendance record not found.")
    return record


def upsert_manual_entry(organization, target_user: User, data: dict, *, approved_by: User) -> Attendance:
    """Admin correction: write or overwrite one day for one employee."""
    day = parse_date(data.get("date"), "date")
    if not day:
        raise ValidationError("Date is required.", details={"date": "Use the format YYYY-MM-DD."})

    check_in_at = parse_datetime(data.get("check_in"), "check_in")
    check_out_at = parse_datetime(data.get("check_out"), "check_out")
    if check_in_at and check_out_at and check_out_at <= check_in_at:
        raise ValidationError(
            "Check-out must be after check-in.", details={"check_out": "Must be after check-in."}
        )

    record = Attendance.objects.filter(
        organization=organization, user=target_user, date=day_key(day), is_deleted=False
    ).first()
    if not record:
        record = Attendance(organization=organization, user=target_user, date=day_key(day))

    record.sessions = []
    if check_in_at:
        record.sessions.append(
            WorkSession(
                check_in=check_in_at,
                check_out=check_out_at,
                source=AttendanceSource.MANUAL,
                note=data.get("note"),
            )
        )

    record.status = validate_choice(
        data.get("status", AttendanceStatus.PRESENT), AttendanceStatus.ALL, "status"
    )
    record.is_manual = True
    record.approved_by = approved_by
    record.note = data.get("note")
    record.recalculate().save()
    return record


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def user_summary(organization, user: User, *, date_from=None, date_to=None) -> dict:
    """Per-employee totals over a window (defaults to the last 30 days)."""
    date_to = parse_date(date_to, "date_to") or today_for(organization)
    date_from = parse_date(date_from, "date_from") or (date_to - timedelta(days=30))

    records = list(
        Attendance.objects.filter(
            organization=organization, user=user, is_deleted=False,
            date__gte=day_key(date_from), date__lte=day_key(date_to),
        )
    )

    counts = {status: 0 for status in AttendanceStatus.ALL}
    total_seconds = 0
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
        total_seconds += record.total_seconds or 0

    return {
        "user_id": str(user.id),
        "user_name": user.full_name,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "days_recorded": len(records),
        "total_hours": round(total_seconds / 3600.0, 2),
        "average_hours": round(total_seconds / 3600.0 / len(records), 2) if records else 0,
        "counts": counts,
    }


def daily_overview(organization, day: date = None) -> dict:
    """Who is in today - the admin dashboard's headline panel."""
    day = day or today_for(organization)
    records = list(
        Attendance.objects.filter(organization=organization, date=day_key(day), is_deleted=False)
    )

    headcount = User.objects.filter(
        organization=organization, is_deleted=False, status="active"
    ).count()

    checked_in_now = [record for record in records if record.is_checked_in]
    counts = {status: 0 for status in AttendanceStatus.ALL}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1

    return {
        "date": day.isoformat(),
        "headcount": headcount,
        "marked": len(records),
        "not_marked": max(headcount - len(records), 0),
        "currently_checked_in": len(checked_in_now),
        "counts": counts,
        "total_hours": round(sum(r.total_seconds for r in records) / 3600.0, 2),
    }
