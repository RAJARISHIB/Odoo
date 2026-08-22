"""Leaves domain - mongoengine documents mapped to Mongo collections.

Collections
    holidays                : government and organization holidays
    leave_requests           : employee leave applications
    leave_types              : admin-configurable kinds of leave (added for the
                                admin leave module - section below)
    leave_allocation_rules   : how much leave a role accrues, versioned by date
    leave_allocations        : the ledger of grants actually credited
    leave_adjustments        : manual, audited balance corrections

The employee-facing pieces above (`Holiday`, `LeaveRequest`, and every function
in `services.py`/`controllers.py` that already existed) are unchanged in
behaviour - the fields added to them are optional and admin-only, so a caller
that never sends them (the employee calendar) sees identical behaviour to
before.  Everything below the admin-module marker is new.
"""
from datetime import datetime, timezone

from mongoengine import (
    BooleanField,
    DateTimeField,
    FloatField,
    IntField,
    ListField,
    ReferenceField,
    StringField,
)

from core.base_model import BaseDocument
from core.constants import LeaveAllocationFrequency


class Holiday(BaseDocument):
    """A government or organization holiday."""

    TYPE_GOVERNMENT = "government"
    TYPE_ORGANIZATION = "organization"
    #: Added for the admin leave module - both "organization" and "company" ==
    #: an org-declared holiday; "organization" is kept as the stored value so
    #: existing rows and the employee calendar (which checks for it by name)
    #: are unaffected.
    TYPE_FESTIVAL = "festival"
    TYPE_OPTIONAL = "optional"
    TYPE_CHOICES = (TYPE_GOVERNMENT, TYPE_ORGANIZATION, TYPE_FESTIVAL, TYPE_OPTIONAL)

    organization = ReferenceField("Organization", required=True)
    name = StringField(required=True, max_length=150)
    date = DateTimeField(required=True)
    type = StringField(required=True, choices=TYPE_CHOICES, default=TYPE_GOVERNMENT)
    description = StringField(max_length=500, default="")
    is_active = BooleanField(default=True)

    # -- admin leave module additions (optional, default-safe) --------------
    #: Empty = applies to every role. Populated only by the admin holiday form.
    applicable_roles = ListField(StringField(), default=list)
    created_by = ReferenceField("User", null=True)
    updated_by = ReferenceField("User", null=True)

    meta = {
        "collection": "holidays",
        "indexes": [
            "organization",
            "date",
            "type",
            "is_active",
            {"fields": ("organization", "date"), "unique": True},
        ],
        "ordering": ["date"],
    }

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)
        if self.date:
            data["date"] = self.date.strftime("%Y-%m-%d")
        return data

    def __repr__(self):
        return "<Holiday {} ({}) {}>".format(self.name, self.type, self.date)


class LeaveRequest(BaseDocument):
    """An employee's leave request."""

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_CANCELLED)

    organization = ReferenceField("Organization", required=True)
    employee = ReferenceField("User", required=True)

    start_date = DateTimeField(required=True)
    end_date = DateTimeField(required=True)
    reason = StringField(required=True, max_length=1000)
    status = StringField(required=True, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # -- admin leave module additions (optional, default-safe) --------------
    #: Set only when an admin-configured leave type applies - the employee
    #: submission flow does not send this, so it stays null for those requests.
    leave_type = ReferenceField("LeaveType", null=True)
    reviewed_by = ReferenceField("User", null=True)
    reviewed_at = DateTimeField(null=True)
    review_comment = StringField(max_length=1000)

    meta = {
        "collection": "leave_requests",
        "indexes": [
            "organization",
            "employee",
            "start_date",
            "end_date",
            "status",
            ("organization", "employee", "start_date"),
        ],
        "ordering": ["-created_at"],
    }

    @property
    def total_days(self) -> int:
        """Inclusive count of calendar days in the request."""
        if not self.start_date or not self.end_date:
            return 0
        delta = (self.end_date.date() - self.start_date.date()).days
        return max(1, delta + 1)

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)
        if self.start_date:
            data["start_date"] = self.start_date.strftime("%Y-%m-%d")
        if self.end_date:
            data["end_date"] = self.end_date.strftime("%Y-%m-%d")
        data["total_days"] = self.total_days
        if self.leave_type:
            data["leave_type_name"] = self.leave_type.name
            data["leave_type_code"] = self.leave_type.code
        return data

    def __repr__(self):
        return "<LeaveRequest {} {} to {} ({})>".format(
            self.employee_id, self.start_date, self.end_date, self.status
        )


# =============================================================================
# Admin leave module - new collections.  Nothing above this line changes the
# behaviour of the employee calendar; everything below is additive.
# =============================================================================
class LeaveType(BaseDocument):
    """A kind of leave an org has defined (Casual, Sick, Unpaid, ...).

    Admin-defined rather than hard-coded, so the allocation and dashboard logic
    reads `min_unit` / `allow_fractional` / `max_days_per_request` from here
    instead of assuming any particular set of leave types exists.
    """

    organization = ReferenceField("Organization", required=True)
    name = StringField(required=True, max_length=100)
    code = StringField(required=True, max_length=20)
    description = StringField(max_length=500)

    is_paid = BooleanField(default=True)
    is_active = BooleanField(default=True)

    allow_fractional = BooleanField(default=True)
    #: Smallest allocatable slice - 0.5 or 1.0 day.
    min_unit = FloatField(default=0.5)
    #: Optional cap on a single request; null = no cap.
    max_days_per_request = FloatField(null=True)
    requires_approval = BooleanField(default=True)
    #: UI accent, e.g. "#4f46e5" - purely cosmetic.
    color = StringField(max_length=20, default="")

    meta = {
        "collection": "leave_types",
        "indexes": [
            "organization",
            "is_active",
            {"fields": ("organization", "code"), "unique": True},
        ],
        "ordering": ["name"],
    }

    def __repr__(self):
        return "<LeaveType {} ({})>".format(self.name, self.code)


class LeaveAllocationRule(BaseDocument):
    """How much leave one role accrues for one leave type, from an effective date.

    Superseding a rule sets the old one's `effective_to` instead of deleting
    it, so a month generated under the old rule stays explainable forever - a
    rule change never rewrites allocations already made.
    """

    organization = ReferenceField("Organization", required=True)
    leave_type = ReferenceField(LeaveType, required=True)
    role = StringField(required=True)
    frequency = StringField(
        choices=LeaveAllocationFrequency.ALL, default=LeaveAllocationFrequency.MONTHLY
    )
    amount = FloatField(required=True)
    effective_from = DateTimeField(required=True)
    #: Null while this is the current rule for (org, leave_type, role).
    effective_to = DateTimeField(null=True)
    is_active = BooleanField(default=True)
    created_by = ReferenceField("User", null=True)

    meta = {
        "collection": "leave_allocation_rules",
        "indexes": [
            "organization",
            "leave_type",
            "role",
            "is_active",
            ("organization", "leave_type", "role"),
        ],
        "ordering": ["-effective_from"],
    }

    def __repr__(self):
        return "<LeaveAllocationRule {} {} {}/mo>".format(self.leave_type_id, self.role, self.amount)


class LeaveAllocation(BaseDocument):
    """One ledger entry: this employee was granted this many days for this period.

    `period_key` ("2026-03" for monthly, "2026" for yearly) is unique per
    (user, leave_type), which is what makes accrual generation idempotent -
    running the same month twice is a no-op, never a double credit.
    """

    organization = ReferenceField("Organization", required=True)
    user = ReferenceField("User", required=True)
    leave_type = ReferenceField(LeaveType, required=True)
    rule = ReferenceField(LeaveAllocationRule, null=True)

    year = IntField(required=True)
    #: Null for a yearly-frequency grant.
    month = IntField(null=True, min_value=1, max_value=12)
    frequency = StringField(
        choices=LeaveAllocationFrequency.ALL, default=LeaveAllocationFrequency.MONTHLY
    )
    amount = FloatField(required=True)
    period_key = StringField(required=True, max_length=10)

    meta = {
        "collection": "leave_allocations",
        "indexes": [
            "organization",
            "user",
            "leave_type",
            "year",
            {"fields": ("user", "leave_type", "period_key"), "unique": True},
        ],
        "ordering": ["-year", "-month"],
    }

    def __repr__(self):
        return "<LeaveAllocation {} {} {}>".format(self.user_id, self.leave_type_id, self.period_key)


class LeaveAdjustment(BaseDocument):
    """A manual, audited balance correction (carry-forward, a one-off grant, a
    correction for an earlier mistake). Never applied silently."""

    organization = ReferenceField("Organization", required=True)
    user = ReferenceField("User", required=True)
    leave_type = ReferenceField(LeaveType, required=True)
    #: Positive credits the balance, negative debits it.
    amount = FloatField(required=True)
    reason = StringField(required=True, max_length=500)
    created_by = ReferenceField("User", required=True)

    meta = {
        "collection": "leave_adjustments",
        "indexes": ["organization", "user", "leave_type"],
        "ordering": ["-created_at"],
    }

    def __repr__(self):
        return "<LeaveAdjustment {} {} {:+}>".format(self.user_id, self.leave_type_id, self.amount)
