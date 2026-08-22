"""Leave domain business logic."""
import calendar
import logging
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from mongoengine.errors import NotUniqueError
from mongoengine.queryset.visitor import Q

from apps.leaves.models import Holiday, LeaveAdjustment, LeaveAllocation, LeaveAllocationRule, LeaveRequest, LeaveType
from core.constants import LeaveAllocationFrequency, Role
from core.exceptions import Conflict, NotFound, ValidationError
from core.utils import round_leave
from core.validators import parse_bool, parse_date, require_fields, validate_choice, validate_object_id

logger = logging.getLogger(__name__)


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

    if manager:
        from apps.teams.services import get_subordinate_ids
        sub_ids = get_subordinate_ids(organization, manager)
        if not sub_ids:
            return queryset.none()
        queryset = queryset.filter(employee__in=sub_ids)

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
    """Validate and create a new leave request in PENDING status.

    Balance is enforced against the leave type the employee picks (section:
    admin leave module) rather than the flat `monthly_leave_entitlement`
    setting - `get_balance` below is the same function the admin dashboard
    and approval flow use, so what an employee sees while applying, what
    blocks the submission, and what the dashboard reports are always the
    same number.
    """
    require_fields(data, ["start_date", "end_date", "reason", "leave_type_id"])

    leave_type = get_leave_type(organization, data["leave_type_id"])
    if not leave_type.is_active:
        raise ValidationError(
            "This leave type is not active.", details={"leave_type_id": "Choose an active leave type."}
        )

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

    # 3. Per-request cap, if the leave type sets one.
    requested_days = (end_d - start_d).days + 1
    if leave_type.max_days_per_request and requested_days > leave_type.max_days_per_request:
        raise ValidationError(
            "This request exceeds the maximum allowed for {}.".format(leave_type.name),
            details={"end_date": "Maximum {} day(s) per request for {}.".format(
                leave_type.max_days_per_request, leave_type.name
            )},
        )

    # 4. Leave Balance Validation - against this specific leave type's
    #    configured allocation, not a flat organization-wide number.  Unpaid
    #    leave types are exempt: there is nothing to run out of.
    if leave_type.is_paid:
        balance = get_balance(organization, employee, leave_type, start_d.year)
        remaining = balance["remaining"]
        if requested_days > remaining + 1e-9:
            raise ValidationError(
                "Requested leave ({} day(s)) exceeds your remaining {} balance ({} day(s)).".format(
                    requested_days, leave_type.name, remaining
                ),
                details={"end_date": "Only {} day(s) of {} remaining.".format(remaining, leave_type.name)},
            )

    # Create leave request with initial status PENDING
    leave_req = LeaveRequest(
        organization=organization,
        employee=employee,
        start_date=start_dt,
        end_date=end_dt,
        reason=reason,
        status=LeaveRequest.STATUS_PENDING,
        leave_type=leave_type,
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


# =============================================================================
# Admin leave module - additive.  Nothing above this line is modified from the
# original employee-facing leave service; the employee calendar keeps calling
# `list_holidays` / `list_leave_requests` / `get_leave_balance` /
# `create_leave_request` / `get_employee_calendar` / `cancel_leave_request`
# exactly as before.
# =============================================================================
def _to_dt(day) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _year_bounds(year: int) -> tuple:
    return datetime(year, 1, 1, tzinfo=timezone.utc), datetime(year + 1, 1, 1, tzinfo=timezone.utc)


def get_leave_request_in_org(organization, request_id: str) -> LeaveRequest:
    req_id = validate_object_id(request_id, "request_id")
    request = LeaveRequest.objects.filter(id=req_id, organization=organization, is_deleted=False).first()
    if not request:
        raise NotFound("Leave request not found.")
    return request


# ---------------------------------------------------------------------------
# Admin: leave requests (list all / approve / reject)
# ---------------------------------------------------------------------------
def admin_list_leave_requests(organization, *, manager=None, status=None, leave_type_id=None, department_id=None,
                              search=None, date_from=None, date_to=None):
    queryset = LeaveRequest.objects.filter(organization=organization, is_deleted=False)

    if manager:
        from apps.teams.services import get_subordinate_ids
        sub_ids = get_subordinate_ids(organization, manager)
        if not sub_ids:
            return queryset.none()
        queryset = queryset.filter(employee__in=sub_ids)

    if status:
        queryset = queryset.filter(status=validate_choice(status, LeaveRequest.STATUS_CHOICES, "status"))
    if leave_type_id:
        queryset = queryset.filter(leave_type=leave_type_id)
    if date_from:
        queryset = queryset.filter(end_date__gte=_to_dt(parse_date(date_from, "date_from")))
    if date_to:
        queryset = queryset.filter(start_date__lte=_to_dt(parse_date(date_to, "date_to")))

    if department_id or search:
        from apps.users.models import User

        users_qs = User.objects.filter(organization=organization, is_deleted=False)
        if department_id:
            users_qs = users_qs.filter(department=department_id)
        if search:
            pattern = re.escape(search)
            users_qs = users_qs.filter(
                __raw__={
                    "$or": [
                        {"first_name": {"$regex": pattern, "$options": "i"}},
                        {"last_name": {"$regex": pattern, "$options": "i"}},
                        {"employee_id": {"$regex": pattern, "$options": "i"}},
                    ]
                }
            )
        queryset = queryset.filter(employee__in=[u.id for u in users_qs])

    return queryset.order_by("-created_at")


def approve_leave_request(organization, request_id: str, reviewer, leave_type_id: str = None) -> LeaveRequest:
    """Admin approval.  `leave_type_id` is optional: the employee submission
    flow never sets a leave type, so an admin may tag one here (for dashboard
    attribution) without ever having to change how leave is requested."""
    request = get_leave_request_in_org(organization, request_id)
    from core.constants import Permissions
    from core.exceptions import PermissionDenied
    if not reviewer.has_permission(Permissions.ORG_MANAGE):
        from apps.teams.services import get_subordinate_ids
        if str(request.employee.id) not in get_subordinate_ids(organization, reviewer):
            raise PermissionDenied("You can only approve requests for your team members.")

    from core.constants import Permissions
    from core.exceptions import PermissionDenied
    if not reviewer.has_permission(Permissions.ORG_MANAGE):
        from apps.teams.services import get_subordinate_ids
        if str(request.employee.id) not in get_subordinate_ids(organization, reviewer):
            raise PermissionDenied("You can only reject requests for your team members.")

    if request.status != LeaveRequest.STATUS_PENDING:
        raise Conflict("Only pending requests can be approved.", code="invalid_status")

    if leave_type_id:
        request.leave_type = get_leave_type(organization, leave_type_id)

    request.status = LeaveRequest.STATUS_APPROVED
    request.reviewed_by = reviewer
    request.reviewed_at = datetime.now(timezone.utc)
    request.save()
    return request


def reject_leave_request(organization, request_id: str, reviewer, comment: str = None) -> LeaveRequest:
    request = get_leave_request_in_org(organization, request_id)
    from core.constants import Permissions
    from core.exceptions import PermissionDenied
    if not reviewer.has_permission(Permissions.ORG_MANAGE):
        from apps.teams.services import get_subordinate_ids
        if str(request.employee.id) not in get_subordinate_ids(organization, reviewer):
            raise PermissionDenied("You can only approve requests for your team members.")

    from core.constants import Permissions
    from core.exceptions import PermissionDenied
    if not reviewer.has_permission(Permissions.ORG_MANAGE):
        from apps.teams.services import get_subordinate_ids
        if str(request.employee.id) not in get_subordinate_ids(organization, reviewer):
            raise PermissionDenied("You can only reject requests for your team members.")

    if request.status != LeaveRequest.STATUS_PENDING:
        raise Conflict("Only pending requests can be rejected.", code="invalid_status")

    request.status = LeaveRequest.STATUS_REJECTED
    request.reviewed_by = reviewer
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_comment = (comment or "").strip()
    request.save()
    return request


# ---------------------------------------------------------------------------
# Leave types
# ---------------------------------------------------------------------------
def list_leave_types(organization, *, active_only: bool = False):
    queryset = LeaveType.objects.filter(organization=organization, is_deleted=False)
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


def get_leave_type(organization, leave_type_id: str) -> LeaveType:
    lt_id = validate_object_id(leave_type_id, "leave_type_id")
    leave_type = LeaveType.objects.filter(id=lt_id, organization=organization, is_deleted=False).first()
    if not leave_type:
        raise NotFound("Leave type not found.")
    return leave_type


def _validate_min_unit(value) -> float:
    unit = float(value)
    if unit not in (0.5, 1.0):
        raise ValidationError("Minimum unit must be 0.5 or 1.", details={"min_unit": "Must be 0.5 or 1."})
    return unit


def _validate_carry_forward_percentage(value) -> float:
    pct = float(value)
    if not (0 <= pct <= 100):
        raise ValidationError(
            "Carry-forward percentage must be between 0 and 100.",
            details={"carry_forward_percentage": "Must be between 0 and 100."},
        )
    return pct


def create_leave_type(organization, data: dict) -> LeaveType:
    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip().upper()
    if not name or not code:
        raise ValidationError(
            "Name and code are required.",
            details={"name": "This field is required.", "code": "This field is required."},
        )
    if LeaveType.objects.filter(organization=organization, code=code, is_deleted=False).first():
        raise Conflict("A leave type with this code already exists.", code="leave_type_exists")

    max_days = data.get("max_days_per_request")
    leave_type = LeaveType(
        organization=organization,
        name=name,
        code=code,
        description=data.get("description", ""),
        is_paid=parse_bool(data.get("is_paid", True), True),
        is_active=parse_bool(data.get("is_active", True), True),
        allow_fractional=parse_bool(data.get("allow_fractional", True), True),
        min_unit=_validate_min_unit(data.get("min_unit", 0.5)),
        max_days_per_request=float(max_days) if max_days not in (None, "") else None,
        requires_approval=parse_bool(data.get("requires_approval", True), True),
        color=data.get("color", ""),
        allow_carry_forward=parse_bool(data.get("allow_carry_forward", False), False),
        carry_forward_percentage=_validate_carry_forward_percentage(data.get("carry_forward_percentage", 0)),
        carry_forward_frequency=validate_choice(
            data.get("carry_forward_frequency", LeaveAllocationFrequency.YEARLY),
            LeaveAllocationFrequency.ALL, "carry_forward_frequency",
        ),
    ).save()
    return leave_type


def update_leave_type(leave_type: LeaveType, data: dict) -> LeaveType:
    if "code" in data:
        code = (data["code"] or "").strip().upper()
        if not code:
            raise ValidationError("Code is required.", details={"code": "This field is required."})
        duplicate = LeaveType.objects.filter(
            organization=leave_type.organization, code=code, is_deleted=False, id__ne=leave_type.id
        ).first()
        if duplicate:
            raise Conflict("A leave type with this code already exists.", code="leave_type_exists")
        leave_type.code = code

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise ValidationError("Name is required.", details={"name": "This field is required."})
        leave_type.name = name
    if "description" in data:
        leave_type.description = data["description"]
    if "is_paid" in data:
        leave_type.is_paid = parse_bool(data["is_paid"])
    if "allow_fractional" in data:
        leave_type.allow_fractional = parse_bool(data["allow_fractional"])
    if "min_unit" in data:
        leave_type.min_unit = _validate_min_unit(data["min_unit"])
    if "max_days_per_request" in data:
        max_days = data["max_days_per_request"]
        leave_type.max_days_per_request = float(max_days) if max_days not in (None, "") else None
    if "requires_approval" in data:
        leave_type.requires_approval = parse_bool(data["requires_approval"])
    if "is_active" in data:
        leave_type.is_active = parse_bool(data["is_active"])
    if "color" in data:
        leave_type.color = data["color"]
    if "allow_carry_forward" in data:
        leave_type.allow_carry_forward = parse_bool(data["allow_carry_forward"])
    if "carry_forward_percentage" in data:
        leave_type.carry_forward_percentage = _validate_carry_forward_percentage(data["carry_forward_percentage"])
    if "carry_forward_frequency" in data:
        leave_type.carry_forward_frequency = validate_choice(
            data["carry_forward_frequency"], LeaveAllocationFrequency.ALL, "carry_forward_frequency"
        )

    leave_type.save()
    return leave_type


# ---------------------------------------------------------------------------
# Holidays - admin create/update.  `list_holidays` above (unmodified) already
# serves both the employee calendar and the admin table.
# ---------------------------------------------------------------------------
def create_holiday_admin(organization, data: dict, *, created_by) -> Holiday:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("Holiday name is required.", details={"name": "This field is required."})

    holiday_date = parse_date(data.get("date"), "date")
    if not holiday_date:
        raise ValidationError("Holiday date is required.", details={"date": "This field is required."})

    try:
        holiday = Holiday(
            organization=organization,
            name=name,
            date=_to_dt(holiday_date),
            type=validate_choice(data.get("type", Holiday.TYPE_GOVERNMENT), Holiday.TYPE_CHOICES, "type"),
            description=data.get("description", ""),
            is_active=parse_bool(data.get("is_active", True), True),
            applicable_roles=data.get("applicable_roles") or [],
            created_by=created_by,
            updated_by=created_by,
        ).save()
    except NotUniqueError:
        raise Conflict("A holiday already exists on this date.", code="holiday_date_taken")
    return holiday


def update_holiday_admin(organization, holiday_id: str, data: dict, *, updated_by) -> Holiday:
    """Future holidays are freely editable; a past holiday is protected so
    history is never silently rewritten."""
    hol_id = validate_object_id(holiday_id, "holiday_id")
    holiday = Holiday.objects.filter(id=hol_id, organization=organization, is_deleted=False).first()
    if not holiday:
        raise NotFound("Holiday not found.")

    today = date.today()
    if holiday.date.date() < today:
        raise Conflict("This holiday has already passed and cannot be edited.", code="holiday_locked")

    if "date" in data:
        new_date = parse_date(data["date"], "date")
        if not new_date:
            raise ValidationError("Invalid date.", details={"date": "Use the format YYYY-MM-DD."})
        if new_date < today:
            raise ValidationError(
                "A holiday cannot be moved into the past.", details={"date": "Must be today or later."}
            )
        holiday.date = _to_dt(new_date)

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise ValidationError("Holiday name is required.", details={"name": "This field is required."})
        holiday.name = name
    if "description" in data:
        holiday.description = data["description"]
    if "type" in data:
        holiday.type = validate_choice(data["type"], Holiday.TYPE_CHOICES, "type")
    if "is_active" in data:
        holiday.is_active = parse_bool(data["is_active"])
    if "applicable_roles" in data:
        holiday.applicable_roles = data["applicable_roles"] or []

    holiday.updated_by = updated_by
    try:
        holiday.save()
    except NotUniqueError:
        raise Conflict("A holiday already exists on this date.", code="holiday_date_taken")
    return holiday


# ---------------------------------------------------------------------------
# Allocation rules (role-based, effective-dated) + idempotent accrual
# ---------------------------------------------------------------------------
def list_allocation_rules(organization, *, leave_type_id: str = None, role: str = None):
    queryset = LeaveAllocationRule.objects.filter(organization=organization, is_deleted=False)
    if leave_type_id:
        queryset = queryset.filter(leave_type=leave_type_id)
    if role:
        queryset = queryset.filter(role=validate_choice(role, Role.ALL, "role"))
    return queryset.order_by("role", "-effective_from")


def get_allocation_rule(organization, rule_id: str) -> LeaveAllocationRule:
    rule_id = validate_object_id(rule_id, "rule_id")
    rule = LeaveAllocationRule.objects.filter(id=rule_id, organization=organization, is_deleted=False).first()
    if not rule:
        raise NotFound("Allocation rule not found.")
    return rule


def get_applicable_rule(organization, leave_type: LeaveType, role: str, on_date: date):
    """The rule in force for `role` on `on_date`."""
    on_dt = _to_dt(on_date)
    return (
        LeaveAllocationRule.objects.filter(
            organization=organization, leave_type=leave_type, role=role, is_active=True,
            is_deleted=False, effective_from__lte=on_dt,
        )
        .filter(Q(effective_to=None) | Q(effective_to__gte=on_dt))
        .order_by("-effective_from")
        .first()
    )


def create_allocation_rule(organization, data: dict, *, created_by) -> LeaveAllocationRule:
    leave_type = get_leave_type(organization, data.get("leave_type_id"))
    role = validate_choice(data.get("role"), Role.ALL, "role")
    frequency = validate_choice(
        data.get("frequency", LeaveAllocationFrequency.MONTHLY), LeaveAllocationFrequency.ALL, "frequency"
    )

    amount = data.get("amount")
    if amount is None:
        raise ValidationError("Allocation amount is required.", details={"amount": "This field is required."})
    amount = round_leave(amount)
    if amount <= 0:
        raise ValidationError("Allocation amount must be greater than zero.", details={"amount": "Must be positive."})

    effective_from = parse_date(data.get("effective_from")) or date.today()
    effective_from_dt = _to_dt(effective_from)

    # Supersede the current rule for this (org, leave_type, role), if any - the
    # old rule keeps every month already generated under it.
    previous = LeaveAllocationRule.objects.filter(
        organization=organization, leave_type=leave_type, role=role,
        is_active=True, is_deleted=False, effective_to=None,
    ).first()
    if previous:
        if effective_from_dt <= previous.effective_from:
            raise ValidationError(
                "The new rule must take effect after the current rule's start date.",
                details={"effective_from": "Must be later than {}.".format(previous.effective_from.date())},
            )
        previous.effective_to = effective_from_dt - timedelta(days=1)
        previous.save()

    return LeaveAllocationRule(
        organization=organization,
        leave_type=leave_type,
        role=role,
        frequency=frequency,
        amount=amount,
        effective_from=effective_from_dt,
        created_by=created_by,
    ).save()


def update_allocation_rule(rule: LeaveAllocationRule, data: dict) -> LeaveAllocationRule:
    """Deactivation is always allowed.  Amount/date edits are blocked once the
    rule has produced allocations, so history can never be rewritten - create a
    new rule (which supersedes this one) instead."""
    if "is_active" in data:
        rule.is_active = parse_bool(data["is_active"])

    if "amount" in data or "effective_from" in data or "frequency" in data:
        if LeaveAllocation.objects.filter(rule=rule).first():
            raise Conflict(
                "This rule has already generated allocations and cannot be edited. "
                "Create a new rule to change the amount going forward.",
                code="rule_in_use",
            )
        if "amount" in data:
            amount = round_leave(data["amount"])
            if amount <= 0:
                raise ValidationError("Allocation amount must be greater than zero.", details={"amount": "Must be positive."})
            rule.amount = amount
        if "frequency" in data:
            rule.frequency = validate_choice(data["frequency"], LeaveAllocationFrequency.ALL, "frequency")
        if "effective_from" in data:
            effective_from = parse_date(data["effective_from"])
            if not effective_from:
                raise ValidationError("Invalid date.", details={"effective_from": "Use the format YYYY-MM-DD."})
            rule.effective_from = _to_dt(effective_from)

    rule.save()
    return rule


def generate_allocations(organization, year: int, month: int = None) -> dict:
    """Credit every active employee the allocation their role's rule promises
    for this period.  Idempotent: a (user, leave_type, period_key) row is
    created once and never again, so running the same month twice never
    double-credits."""
    from apps.users.models import User

    frequency = LeaveAllocationFrequency.MONTHLY if month else LeaveAllocationFrequency.YEARLY
    period_key = "{:04d}-{:02d}".format(year, month) if month else "{:04d}".format(year)
    reference_date = date(year, month or 1, 1)

    users = User.objects.filter(organization=organization, is_deleted=False, status="active")
    leave_types = LeaveType.objects.filter(organization=organization, is_deleted=False, is_active=True)

    created, skipped = 0, 0
    for user in users:
        for leave_type in leave_types:
            rule = get_applicable_rule(organization, leave_type, user.role, reference_date)
            if not rule or rule.frequency != frequency:
                continue

            if LeaveAllocation.objects.filter(user=user, leave_type=leave_type, period_key=period_key).first():
                skipped += 1
                continue

            LeaveAllocation(
                organization=organization, user=user, leave_type=leave_type, rule=rule,
                year=year, month=month, frequency=frequency, amount=rule.amount, period_key=period_key,
            ).save()
            created += 1

    logger.info(
        "Leave accrual for %s (%s): %d created, %d already present",
        period_key, organization.slug, created, skipped,
    )
    return {"period": period_key, "frequency": frequency, "created": created, "skipped": skipped}


def carry_forward(organization, leave_type: LeaveType, *, from_year: int, from_month: int = None,
                  created_by=None) -> dict:
    """Credit `leave_type.carry_forward_percentage`% of one period's unused
    balance into the next period, as an audited `LeaveAdjustment`.

    Idempotent per (user, leave_type, source period): a run is recognisable by
    its `reason` text, so re-running the same period is a no-op rather than a
    double credit - the same guarantee `generate_allocations` gives for
    accrual.

    `from_month` given  -> monthly: unused = that month's accrual minus
                            approved usage inside that month.
    `from_month` absent -> yearly: unused = the whole year's remaining balance.
    """
    if not leave_type.allow_carry_forward or leave_type.carry_forward_percentage <= 0:
        raise ValidationError(
            "Carry-forward is not enabled for this leave type.",
            details={"leave_type_id": "Turn on carry-forward and set a percentage first."},
        )

    from apps.users.models import User

    if from_month:
        period_key = "{:04d}-{:02d}".format(from_year, from_month)
        marker = "Carry-forward from {}".format(period_key)
        to_year = from_year + 1 if from_month == 12 else from_year
        month_start = _to_dt(date(from_year, from_month, 1))
        _, last_day = calendar.monthrange(from_year, from_month)
        month_end = _to_dt(date(from_year, from_month, last_day)) + timedelta(hours=23, minutes=59, seconds=59)
    else:
        period_key = "{:04d}".format(from_year)
        marker = "Carry-forward from {}".format(period_key)
        to_year = from_year + 1

    users = User.objects.filter(organization=organization, is_deleted=False, status="active")
    created, skipped = 0, 0

    for user in users:
        already = LeaveAdjustment.objects.filter(
            organization=organization, user=user, leave_type=leave_type, reason=marker
        ).first()
        if already:
            skipped += 1
            continue

        if from_month:
            allocation = LeaveAllocation.objects.filter(
                user=user, leave_type=leave_type, period_key=period_key
            ).first()
            allocated = allocation.amount if allocation else 0.0
            used = round_leave(sum(
                r.total_days for r in LeaveRequest.objects.filter(
                    organization=organization, employee=user, leave_type=leave_type, is_deleted=False,
                    status=LeaveRequest.STATUS_APPROVED, start_date__gte=month_start, start_date__lte=month_end,
                )
            ))
            unused = max(0.0, round_leave(allocated - used))
        else:
            unused = max(0.0, get_balance(organization, user, leave_type, from_year)["remaining"])

        carried = round_leave(unused * leave_type.carry_forward_percentage / 100.0)
        if carried <= 0:
            skipped += 1
            continue

        LeaveAdjustment(
            organization=organization, user=user, leave_type=leave_type, amount=carried,
            reason=marker, created_by=created_by, year=to_year,
        ).save()
        created += 1

    logger.info(
        "Carry-forward for %s (%s, %s): %d credited, %d skipped",
        period_key, organization.slug, leave_type.code, created, skipped,
    )
    return {"period": period_key, "target_year": to_year, "created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# Adjustments
# ---------------------------------------------------------------------------
def create_adjustment(organization, user, leave_type: LeaveType, data: dict, *, created_by) -> LeaveAdjustment:
    amount = data.get("amount")
    if amount in (None, ""):
        raise ValidationError("Adjustment amount is required.", details={"amount": "This field is required."})
    amount = round_leave(amount)
    if amount == 0:
        raise ValidationError("Adjustment amount cannot be zero.", details={"amount": "Must be non-zero."})

    reason = (data.get("reason") or "").strip()
    if not reason:
        raise ValidationError("A reason is required.", details={"reason": "This field is required."})

    year = data.get("year")
    year = int(year) if year not in (None, "") else date.today().year

    return LeaveAdjustment(
        organization=organization, user=user, leave_type=leave_type,
        amount=amount, reason=reason, created_by=created_by, year=year,
    ).save()


def list_adjustments(organization, *, user=None, leave_type=None):
    queryset = LeaveAdjustment.objects.filter(organization=organization, is_deleted=False)
    if user:
        queryset = queryset.filter(user=user)
    if leave_type:
        queryset = queryset.filter(leave_type=leave_type)
    return queryset.order_by("-created_at")


# ---------------------------------------------------------------------------
# Balances / dashboard
#
# `used` / `pending` at the row (employee) level are computed from every leave
# request regardless of whether an admin has tagged it with a leave type, so
# the dashboard always reflects real usage; the per-type breakdown only shows
# what has been tagged (via `approve_leave_request(..., leave_type_id=...)`)
# and never hides the rest.
# ---------------------------------------------------------------------------
def _adjustment_year(adjustment) -> int:
    """The balance-year an adjustment counts toward.  Explicit `year` wins;
    older-style rows fall back to when they were recorded."""
    if adjustment.year is not None:
        return adjustment.year
    return adjustment.created_at.year if adjustment.created_at else None


def _row_totals(organization, user, year: int) -> tuple:
    year_start, year_end = _year_bounds(year)
    requests = LeaveRequest.objects.filter(
        organization=organization, employee=user, is_deleted=False,
        start_date__gte=year_start, start_date__lt=year_end,
    )
    used = round_leave(sum(r.total_days for r in requests if r.status == LeaveRequest.STATUS_APPROVED))
    pending = round_leave(sum(r.total_days for r in requests if r.status == LeaveRequest.STATUS_PENDING))
    return used, pending


def get_balance(organization, user, leave_type: LeaveType, year: int) -> dict:
    allocated = sum(
        a.amount for a in LeaveAllocation.objects.filter(
            organization=organization, user=user, leave_type=leave_type, year=year
        )
    )
    adjustments = LeaveAdjustment.objects.filter(
        organization=organization, user=user, leave_type=leave_type, is_deleted=False
    )
    allocated += sum(a.amount for a in adjustments if _adjustment_year(a) == year)
    allocated = round_leave(allocated)

    year_start, year_end = _year_bounds(year)
    typed_requests = LeaveRequest.objects.filter(
        organization=organization, employee=user, leave_type=leave_type, is_deleted=False,
        start_date__gte=year_start, start_date__lt=year_end,
    )
    used = round_leave(sum(r.total_days for r in typed_requests if r.status == LeaveRequest.STATUS_APPROVED))
    pending = round_leave(sum(r.total_days for r in typed_requests if r.status == LeaveRequest.STATUS_PENDING))
    remaining = round_leave(allocated - used)
    utilization = round(used / allocated * 100, 1) if allocated > 0 else 0.0

    return {
        "leave_type_id": str(leave_type.id),
        "leave_type_name": leave_type.name,
        "leave_type_code": leave_type.code,
        "is_paid": leave_type.is_paid,
        "year": year,
        "allocated": allocated,
        "used": used,
        "pending": pending,
        "remaining": remaining,
        "utilization_percentage": utilization,
    }


def list_user_balances(organization, user, year: int) -> list:
    return [
        get_balance(organization, user, leave_type, year)
        for leave_type in LeaveType.objects.filter(organization=organization, is_deleted=False).order_by("name")
    ]


def list_org_balances(organization, year: int, *, leave_type_id: str = None, department_id: str = None,
                      role: str = None, user_id: str = None, search: str = None) -> list:
    """Employee-wise utilization for the admin dashboard.

    Three scoped queries (allocations, adjustments, requests) are pulled once
    and aggregated in memory rather than re-querying per employee per leave
    type.
    """
    from apps.users.models import User

    users_qs = User.objects.filter(organization=organization, is_deleted=False)
    if department_id:
        users_qs = users_qs.filter(department=department_id)
    if role:
        users_qs = users_qs.filter(role=validate_choice(role, Role.ALL, "role"))
    if user_id:
        users_qs = users_qs.filter(id=user_id)
    if search:
        pattern = re.escape(search)
        users_qs = users_qs.filter(
            __raw__={
                "$or": [
                    {"first_name": {"$regex": pattern, "$options": "i"}},
                    {"last_name": {"$regex": pattern, "$options": "i"}},
                    {"employee_id": {"$regex": pattern, "$options": "i"}},
                ]
            }
        )
    users = list(users_qs.order_by("first_name"))

    leave_types_qs = LeaveType.objects.filter(organization=organization, is_deleted=False)
    if leave_type_id:
        leave_types_qs = leave_types_qs.filter(id=leave_type_id)
    leave_types = list(leave_types_qs.order_by("name"))

    if not users or not leave_types:
        return []

    user_ids = [u.id for u in users]
    lt_ids = [lt.id for lt in leave_types]

    alloc_map = defaultdict(float)
    for allocation in LeaveAllocation.objects.filter(
        organization=organization, user__in=user_ids, leave_type__in=lt_ids, year=year
    ):
        alloc_map[(str(allocation.user.id), str(allocation.leave_type.id))] += allocation.amount

    for adjustment in LeaveAdjustment.objects.filter(
        organization=organization, user__in=user_ids, leave_type__in=lt_ids, is_deleted=False
    ):
        if _adjustment_year(adjustment) == year:
            alloc_map[(str(adjustment.user.id), str(adjustment.leave_type.id))] += adjustment.amount

    year_start, year_end = _year_bounds(year)
    used_map, pending_map = defaultdict(float), defaultdict(float)
    for request in LeaveRequest.objects.filter(
        organization=organization, employee__in=user_ids, leave_type__in=lt_ids, is_deleted=False,
        start_date__gte=year_start, start_date__lt=year_end,
    ):
        key = (str(request.employee.id), str(request.leave_type.id))
        if request.status == LeaveRequest.STATUS_APPROVED:
            used_map[key] += request.total_days
        elif request.status == LeaveRequest.STATUS_PENDING:
            pending_map[key] += request.total_days

    rows = []
    for user in users:
        by_type = []
        for leave_type in leave_types:
            key = (str(user.id), str(leave_type.id))
            allocated = round_leave(alloc_map.get(key, 0.0))
            used = round_leave(used_map.get(key, 0.0))
            pending = round_leave(pending_map.get(key, 0.0))
            remaining = round_leave(allocated - used)
            by_type.append({
                "leave_type_id": str(leave_type.id),
                "leave_type_name": leave_type.name,
                "leave_type_code": leave_type.code,
                "allocated": allocated,
                "used": used,
                "pending": pending,
                "remaining": remaining,
                "utilization_percentage": round(used / allocated * 100, 1) if allocated > 0 else 0.0,
            })

        total_allocated = round_leave(sum(t["allocated"] for t in by_type))
        total_used, total_pending = _row_totals(organization, user, year)

        rows.append({
            "user_id": str(user.id),
            "employee_name": user.full_name,
            "employee_id": user.employee_id,
            "department_id": str(user.department.id) if user.department else None,
            "role": getattr(user.role, "slug", str(user.role or "")),
            "allocated": total_allocated,
            "used": total_used,
            "pending": total_pending,
            "remaining": round_leave(total_allocated - total_used),
            "utilization_percentage": round(total_used / total_allocated * 100, 1) if total_allocated > 0 else 0.0,
            "by_type": by_type,
        })
    return rows


def dashboard_summary(organization, year: int, **filters) -> dict:
    rows = list_org_balances(organization, year, **filters)
    pending_requests = LeaveRequest.objects.filter(
        organization=organization, is_deleted=False, status=LeaveRequest.STATUS_PENDING
    ).count()
    return {
        "year": year,
        "total_employees": len(rows),
        "total_allocated": round_leave(sum(r["allocated"] for r in rows)),
        "total_used": round_leave(sum(r["used"] for r in rows)),
        "total_pending_days": round_leave(sum(r["pending"] for r in rows)),
        "total_remaining": round_leave(sum(r["remaining"] for r in rows)),
        "total_pending_requests": pending_requests,
        "rows": rows,
    }


def employee_summary(organization, user, year: int) -> dict:
    history = LeaveRequest.objects.filter(
        organization=organization, employee=user, is_deleted=False
    ).order_by("-created_at").limit(200)
    return {
        "user": {"id": str(user.id), "full_name": user.full_name},
        "year": year,
        "balances": list_user_balances(organization, user, year),
        "history": [request.to_dict() for request in history],
    }

