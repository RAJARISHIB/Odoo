import logging

logger = logging.getLogger(__name__)


"""Leave controllers."""
from datetime import date

from apps.leaves import services
from core.base_controller import BaseController
from core.constants import RealtimeEvent


class LeaveController(BaseController):
    """Employee-facing calendar and leave application controller: /api/v1/leaves/*"""

    def calendar(self):
        """Merged calendar payload containing holidays, user leaves, and leave balance."""
        user = self.require_user()
        data = services.get_employee_calendar(
            user.organization,
            user,
            start_date=self.param("start_date"),
            end_date=self.param("end_date"),
        )
        return self.ok(data)

    def holidays(self):
        """List active holidays for the organization."""
        user = self.require_user()
        queryset = services.list_holidays(
            user.organization,
            start_date=self.param("start_date"),
            end_date=self.param("end_date"),
            holiday_type=self.param("type"),
        )
        return self.ok([h.to_dict() for h in queryset])

    def balance(self):
        """Get employee leave balance."""
        user = self.require_user()
        data = services.get_leave_balance(
            user.organization,
            user,
            target_date=self.param("date"),
        )
        return self.ok(data)

    def type_balances(self):
        """Per-leave-type balance for the signed-in employee - what the apply
        form shows/checks against, and the same numbers the admin dashboard
        and approval flow use."""
        user = self.require_user()
        year = int(self.param("year") or date.today().year)
        return self.ok(services.list_user_balances(user.organization, user, year))

    def my_requests(self):
        """Get signed-in user's leave requests."""
        user = self.require_user()
        queryset = services.list_leave_requests(
            user.organization,
            employee=user,
            start_date=self.param("start_date"),
            end_date=self.param("end_date"),
            status=self.param("status"),
        )
        return self.paginated(queryset)

    def create_request(self):
        """Submit a new leave request (initially PENDING)."""
        user = self.require_user()
        record = services.create_leave_request(
            user.organization,
            user,
            self.data,
        )

        payload = {
            "leave_request": record.to_dict(),
            "user": {"id": str(user.id), "name": user.full_name, "email": user.email},
        }
        self.emit_to_user(user.id, RealtimeEvent.LEAVE_REQUEST_CREATED, payload)
        self.emit_to_admins(RealtimeEvent.LEAVE_REQUEST_CREATED, payload)

        return self.created(record.to_dict(), "Leave request submitted successfully.")

    def cancel_request(self, request_id):
        """Cancel a leave request."""
        user = self.require_user()
        record = services.cancel_leave_request(user.organization, user, request_id)
        return self.ok(record.to_dict(), "Leave request cancelled.")


# =============================================================================
# Admin leave module - additive.  `LeaveController` above is unchanged; these
# controllers add the admin side: approving requests, configuring leave types
# and role-based allocation, managing the holiday calendar, manual balance
# adjustments and the utilization dashboard.  Every write re-checks the role
# here - the Angular guards are a UX convenience only.
# =============================================================================
from apps.users.services import get_user_in_org
from core.constants import Role, Permissions, Permissions
from core.validators import parse_int


class LeaveTypeController(BaseController):
    """Leave type catalogue: /api/v1/leaves/types"""

    def list(self):
        user = self.require_user()
        active_only = not self.is_admin or self.param("active_only", "true").lower() != "false"
        types = services.list_leave_types(user.organization, active_only=active_only)
        return self.ok([leave_type.to_dict() for leave_type in types])

    def create(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        self.require("name", "code")
        leave_type = services.create_leave_type(self.user.organization, self.data)
        self.emit_to_admins(RealtimeEvent.LEAVE_TYPE_UPDATED, {"leave_type": leave_type.to_dict()})
        return self.created(leave_type.to_dict(), "Leave type created.")

    def update(self, type_id):
        self.require_permissions(Permissions.ORG_MANAGE)
        leave_type = services.get_leave_type(self.user.organization, type_id)
        leave_type = services.update_leave_type(leave_type, self.data)
        self.emit_to_admins(RealtimeEvent.LEAVE_TYPE_UPDATED, {"leave_type": leave_type.to_dict()})
        return self.ok(leave_type.to_dict(), "Leave type updated.")

    def set_active(self, type_id, active: bool):
        self.require_permissions(Permissions.ORG_MANAGE)
        leave_type = services.get_leave_type(self.user.organization, type_id)
        leave_type = services.update_leave_type(leave_type, {"is_active": active})
        self.emit_to_admins(RealtimeEvent.LEAVE_TYPE_UPDATED, {"leave_type": leave_type.to_dict()})
        return self.ok(leave_type.to_dict(), "Leave type {}.".format("activated" if active else "deactivated"))


class HolidayAdminController(BaseController):
    """Holiday create/update: /api/v1/leaves/holidays.  Reads stay on the
    existing `LeaveController.holidays`; this only adds admin-only writes."""

    def create(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        self.require("name", "date")
        holiday = services.create_holiday_admin(self.user.organization, self.data, created_by=self.user)
        self.emit_to_admins(RealtimeEvent.HOLIDAY_UPDATED, {"holiday": holiday.to_dict()})
        return self.created(holiday.to_dict(), "Holiday created.")

    def update(self, holiday_id):
        self.require_permissions(Permissions.ORG_MANAGE)
        holiday = services.update_holiday_admin(self.user.organization, holiday_id, self.data, updated_by=self.user)
        self.emit_to_admins(RealtimeEvent.HOLIDAY_UPDATED, {"holiday": holiday.to_dict()})
        self.emit_to_org(RealtimeEvent.HOLIDAY_UPDATED, {"holiday": holiday.to_dict()})
        return self.ok(holiday.to_dict(), "Holiday updated.")


class LeaveAdminRequestController(BaseController):
    """Organization-wide leave requests: /api/v1/admin/leaves/requests"""

    def list(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        queryset = services.admin_list_leave_requests(
            self.user.organization,
            status=self.param("status"), leave_type_id=self.param("leave_type_id"),
            department_id=self.param("department_id"), search=self.param("search"),
            date_from=self.param("date_from"), date_to=self.param("date_to"),
        )
        return self.paginated(queryset, serializer=self._with_employee)

    def retrieve(self, request_id):
        self.require_permissions(Permissions.ORG_MANAGE)
        request = services.get_leave_request_in_org(self.user.organization, request_id)
        return self.ok(self._with_employee(request))

    def approve(self, request_id):
        self.require_permissions(Permissions.ORG_MANAGE)
        request = services.approve_leave_request(
            self.user.organization, request_id, self.user, leave_type_id=self.field("leave_type_id")
        )
        return self._announce(request, "Leave request approved.")

    def reject(self, request_id):
        self.require_permissions(Permissions.ORG_MANAGE)
        request = services.reject_leave_request(self.user.organization, request_id, self.user, self.field("comment"))
        return self._announce(request, "Leave request rejected.")

    def _announce(self, request, message: str):
        payload = {"request": self._with_employee(request), "user_id": str(request.employee.id)}
        self.emit_to_admins(RealtimeEvent.LEAVE_REQUEST_UPDATED, payload)
        self.emit_to_user(request.employee.id, RealtimeEvent.LEAVE_REQUEST_UPDATED, payload)
        return self.ok(request.to_dict(), message)

    @staticmethod
    def _with_employee(request) -> dict:
        data = request.to_dict()
        employee = request.employee
        if employee:
            data["employee_info"] = {
                "id": str(employee.id),
                "name": employee.full_name,
                "email": employee.email,
                "employee_id": employee.employee_id,
                "department_id": str(employee.department.id) if employee.department else None,
                "role": employee.role,
            }
        return data


class LeaveAllocationController(BaseController):
    """Role-based allocation rules + accrual generation: /api/v1/admin/leaves/allocation-rules"""

    def list(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        rules = services.list_allocation_rules(
            self.user.organization, leave_type_id=self.param("leave_type_id"), role=self.param("role"),
        )
        return self.ok([rule.to_dict() for rule in rules])

    def create(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        self.require("leave_type_id", "role", "amount")
        rule = services.create_allocation_rule(self.user.organization, self.data, created_by=self.user)
        self.emit_to_admins(RealtimeEvent.LEAVE_ALLOCATION_UPDATED, {"rule": rule.to_dict()})
        return self.created(rule.to_dict(), "Allocation rule created.")

    def update(self, rule_id):
        self.require_permissions(Permissions.ORG_MANAGE)
        rule = services.get_allocation_rule(self.user.organization, rule_id)
        rule = services.update_allocation_rule(rule, self.data)
        self.emit_to_admins(RealtimeEvent.LEAVE_ALLOCATION_UPDATED, {"rule": rule.to_dict()})
        return self.ok(rule.to_dict(), "Allocation rule updated.")

    def generate(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        today = date.today()
        year = parse_int(self.field("year"), today.year, "year")
        month = parse_int(self.field("month"), today.month, "month")
        if self.field("frequency") == "yearly":
            month = None

        result = services.generate_allocations(self.user.organization, year, month)
        self.emit_to_admins(RealtimeEvent.LEAVE_ALLOCATION_UPDATED, result)
        return self.ok(result, "Generated allocations for {}.".format(result["period"]))

    def carry_forward(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        self.require("leave_type_id", "year")
        leave_type = services.get_leave_type(self.user.organization, self.field("leave_type_id"))
        year = parse_int(self.field("year"), None, "year")
        month = parse_int(self.field("month"), None, "month")

        result = services.carry_forward(
            self.user.organization, leave_type, from_year=year, from_month=month, created_by=self.user
        )
        self.emit_to_admins(RealtimeEvent.LEAVE_BALANCE_UPDATED, result)
        return self.ok(result, "Carried forward {} adjustment(s) into {}.".format(result["created"], result["target_year"]))


class LeaveAdjustmentController(BaseController):
    """Manual, audited balance corrections: /api/v1/admin/leaves/adjustments"""

    def list(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        target_user = get_user_in_org(self.user.organization, self.param("user_id")) if self.param("user_id") else None
        leave_type = services.get_leave_type(self.user.organization, self.param("leave_type_id")) if self.param("leave_type_id") else None
        adjustments = services.list_adjustments(self.user.organization, user=target_user, leave_type=leave_type)
        return self.ok([self._with_creator(a) for a in adjustments])

    def create(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        self.require("user_id", "leave_type_id", "amount", "reason")
        target_user = get_user_in_org(self.user.organization, self.field("user_id"))
        leave_type = services.get_leave_type(self.user.organization, self.field("leave_type_id"))
        adjustment = services.create_adjustment(
            self.user.organization, target_user, leave_type, self.data, created_by=self.user
        )

        payload = {"adjustment": self._with_creator(adjustment), "user_id": str(target_user.id)}
        self.emit_to_admins(RealtimeEvent.LEAVE_BALANCE_UPDATED, payload)
        self.emit_to_user(target_user.id, RealtimeEvent.LEAVE_BALANCE_UPDATED, payload)
        return self.created(adjustment.to_dict(), "Balance adjustment recorded.")

    @staticmethod
    def _with_creator(adjustment) -> dict:
        data = adjustment.to_dict()
        if adjustment.created_by:
            data["created_by_name"] = adjustment.created_by.full_name
        return data


class LeaveDashboardController(BaseController):
    """Balances + org-wide analytics."""

    def admin_balances(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        year = parse_int(self.param("year"), date.today().year, "year")
        rows = services.list_org_balances(
            self.user.organization, year,
            leave_type_id=self.param("leave_type_id"), department_id=self.param("department_id"),
            role=self.param("role"), user_id=self.param("user_id"), search=self.param("search"),
        )
        return self.ok(rows, meta={"total": len(rows), "year": year})

    def dashboard(self):
        self.require_permissions(Permissions.ORG_MANAGE)
        year = parse_int(self.param("year"), date.today().year, "year")
        summary = services.dashboard_summary(
            self.user.organization, year,
            leave_type_id=self.param("leave_type_id"), department_id=self.param("department_id"),
            role=self.param("role"), search=self.param("search"),
        )
        return self.ok(summary)

    def employee_summary(self, user_id):
        self.require_permissions(Permissions.ORG_MANAGE)
        year = parse_int(self.param("year"), date.today().year, "year")
        target_user = get_user_in_org(self.user.organization, user_id)
        return self.ok(services.employee_summary(self.user.organization, target_user, year))

