"""Leave controllers."""
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
        self.emit_to_user(user.id, getattr(RealtimeEvent, "LEAVE_CREATED", "leave.created"), payload)
        self.emit_to_admins(getattr(RealtimeEvent, "LEAVE_CREATED", "leave.created"), payload)

        return self.created(record.to_dict(), "Leave request submitted successfully.")

    def cancel_request(self, request_id):
        """Cancel a leave request."""
        user = self.require_user()
        record = services.cancel_leave_request(user.organization, user, request_id)
        return self.ok(record.to_dict(), "Leave request cancelled.")

