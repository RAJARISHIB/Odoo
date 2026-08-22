"""Leave domain business logic."""
import calendar
from datetime import date, datetime, time, timedelta, timezone

from apps.leaves.models import Holiday, LeaveRequest
from core.exceptions import ValidationError
from core.validators import parse_date, require_fields


def list_holidays(organization, start_date=None, end_date=None, holiday_type=None):
    """Fetch active holidays for an organization within optional date range."""
    queryset = Holiday.objects.filter(organization=organization, is_active=True, is_deleted=False)

    if start_date:
        start_d = parse_date(start_date, "start_date")
        start_dt = datetime.combine(start_d, time.min, tzinfo=timezone.utc)
        queryset = queryset.filter(date__gte=start_dt)

    if end_date:
        end_d = parse_date(end_date, "end_date")
        end_dt = datetime.combine(end_d, time.max, tzinfo=timezone.utc)
        queryset = queryset.filter(date__lte=end_dt)

    if holiday_type:
        queryset = queryset.filter(type=holiday_type)

    return queryset.order_by("date")


def list_leave_requests(organization, employee=None, start_date=None, end_date=None, status=None):
    """Fetch leave requests for an employee/organization."""
    queryset = LeaveRequest.objects.filter(organization=organization, is_deleted=False)

    if employee:
        queryset = queryset.filter(employee=employee)

    if status:
        queryset = queryset.filter(status=status)

    if start_date:
        start_d = parse_date(start_date, "start_date")
        start_dt = datetime.combine(start_d, time.min, tzinfo=timezone.utc)
        queryset = queryset.filter(end_date__gte=start_dt)

    if end_date:
        end_d = parse_date(end_date, "end_date")
        end_dt = datetime.combine(end_d, time.max, tzinfo=timezone.utc)
        queryset = queryset.filter(start_date__lte=end_dt)

    return queryset.order_by("-created_at")


def get_leave_balance(organization, employee, target_date=None):
    """Calculate monthly leave balance for an employee based on organization settings."""
    if not target_date:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = parse_date(target_date, "target_date") or date.today()

    year = target_date.year
    month = target_date.month

    # Read entitlement from existing organization configuration (default to 2 days/month)
    monthly_entitlement = organization.settings.get("monthly_leave_entitlement", 2)
    try:
        monthly_entitlement = int(monthly_entitlement)
    except (ValueError, TypeError):
        monthly_entitlement = 2

    # Start and end of month in UTC
    _, last_day = calendar.monthrange(year, month)
    month_start = datetime.combine(date(year, month, 1), time.min, tzinfo=timezone.utc)
    month_end = datetime.combine(date(year, month, last_day), time.max, tzinfo=timezone.utc)

    # Get employee leave requests overlapping with this month
    user_requests = LeaveRequest.objects.filter(
        organization=organization,
        employee=employee,
        is_deleted=False,
        status__in=[LeaveRequest.STATUS_APPROVED, LeaveRequest.STATUS_PENDING],
        start_date__lte=month_end,
        end_date__gte=month_start,
    )

    used_days = 0
    pending_days = 0

    for req in user_requests:
        # Calculate overlap days in this month
        req_start_d = max(req.start_date.date(), date(year, month, 1))
        req_end_d = min(req.end_date.date(), date(year, month, last_day))
        days = (req_end_d - req_start_d).days + 1

        if req.status == LeaveRequest.STATUS_APPROVED:
            used_days += max(0, days)
        elif req.status == LeaveRequest.STATUS_PENDING:
            pending_days += max(0, days)

    remaining_days = max(0, monthly_entitlement - used_days - pending_days)

    return {
        "year": year,
        "month": month,
        "monthly_entitlement": monthly_entitlement,
        "used_leave": used_days,
        "pending_leave": pending_days,
        "remaining_leave": remaining_days,
    }


def create_leave_request(organization, employee, data: dict) -> LeaveRequest:
    """Validate and create a new leave request in PENDING status."""
    require_fields(data, ["start_date", "end_date", "reason"])

    start_d = parse_date(data["start_date"], "start_date")
    end_d = parse_date(data["end_date"], "end_date")
    reason = str(data["reason"]).strip()

    if not reason:
        raise ValidationError("Reason is required.", details={"reason": "Please enter a reason for leave."})

    if start_d > end_d:
        raise ValidationError(
            "Start date cannot be after end date.",
            details={"end_date": "End date must be on or after start date."},
        )

    today = date.today()
    if start_d < today:
        raise ValidationError(
            "Leave cannot be requested for past dates.",
            details={"start_date": "Start date cannot be in the past."},
        )

    start_dt = datetime.combine(start_d, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_d, time.max, tzinfo=timezone.utc)

    # 1. Holiday Validation: Cannot apply on Government or Organization holidays
    holidays = Holiday.objects.filter(
        organization=organization,
        is_active=True,
        is_deleted=False,
        date__gte=start_dt,
        date__lte=end_dt,
    )
    if holidays.count() > 0:
        holiday_names = ", ".join([h.name for h in holidays])
        raise ValidationError(
            "Selected date range includes holiday(s): {}".format(holiday_names),
            details={"start_date": "Selected dates overlap with holiday: {}".format(holiday_names)},
        )

    # 2. Overlapping Leave Validation: Cannot overlap with PENDING or APPROVED leave
    overlapping = LeaveRequest.objects.filter(
        organization=organization,
        employee=employee,
        is_deleted=False,
        status__in=[LeaveRequest.STATUS_PENDING, LeaveRequest.STATUS_APPROVED],
        start_date__lte=end_dt,
        end_date__gte=start_dt,
    ).first()
    if overlapping:
        raise ValidationError(
            "Selected date range overlaps with an existing leave request.",
            details={"start_date": "Overlaps with leave from {} to {}.".format(
                overlapping.start_date.strftime("%Y-%m-%d"),
                overlapping.end_date.strftime("%Y-%m-%d")
            )},
        )

    # 3. Leave Balance Validation
    requested_days = (end_d - start_d).days + 1
    balance = get_leave_balance(organization, employee, target_date=start_d)
    remaining = balance["remaining_leave"]

    if requested_days > remaining:
        raise ValidationError(
            "Requested leave ({} days) exceeds your available remaining leave balance ({} days).".format(
                requested_days, remaining
            ),
            details={"end_date": "Insufficient leave balance available."},
        )

    # Create leave request with initial status PENDING
    leave_req = LeaveRequest(
        organization=organization,
        employee=employee,
        start_date=start_dt,
        end_date=end_dt,
        reason=reason,
        status=LeaveRequest.STATUS_PENDING,
    )
    return leave_req.save()


def get_employee_calendar(organization, employee, start_date=None, end_date=None):
    """Aggregate holidays and employee leave into a calendar view payload."""
    if not start_date or not end_date:
        today = date.today()
        # Default to current month view
        _, last_day = calendar.monthrange(today.year, today.month)
        start_date = date(today.year, today.month, 1).strftime("%Y-%m-%d")
        end_date = date(today.year, today.month, last_day).strftime("%Y-%m-%d")

    holidays = list_holidays(organization, start_date=start_date, end_date=end_date)
    leave_requests = list_leave_requests(
        organization, employee=employee, start_date=start_date, end_date=end_date
    )

    holidays_data = [h.to_dict() for h in holidays]
    leaves_data = [req.to_dict() for req in leave_requests]
    balance = get_leave_balance(organization, employee, target_date=start_date)

    return {
        "holidays": holidays_data,
        "leaves": leaves_data,
        "balance": balance,
    }


def cancel_leave_request(organization, employee, request_id: str) -> LeaveRequest:
    """Cancel an employee's leave request (regardless of PENDING or APPROVED status)."""
    from core.exceptions import NotFound, ValidationError
    from core.validators import validate_object_id

    req_id = validate_object_id(request_id, "request_id")
    leave_req = LeaveRequest.objects.filter(
        id=req_id,
        organization=organization,
        employee=employee,
        is_deleted=False,
    ).first()

    if not leave_req:
        raise NotFound("Leave request not found.")

    if leave_req.status == LeaveRequest.STATUS_CANCELLED:
        raise ValidationError("This leave request is already cancelled.")

    leave_req.status = LeaveRequest.STATUS_CANCELLED
    leave_req.save()
    return leave_req

