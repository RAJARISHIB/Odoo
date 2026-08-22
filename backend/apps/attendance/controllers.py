"""Attendance controllers.

Punch endpoints emit realtime events so the admin panel's live board updates
without polling.
"""
from apps.attendance import services
from apps.users.services import get_user_in_org
from core.base_controller import BaseController
from core.constants import AttendanceSource, RealtimeEvent, Role


class AttendanceController(BaseController):
    """Employee-facing attendance: /api/v1/attendance/*"""

    def status(self):
        """Today's punch state for the signed-in user."""
        user = self.require_user()
        return self.ok(services.current_status(user))

    def check_in(self):
        user = self.require_user()
        record = services.check_in(
            user,
            source=self.field("source", AttendanceSource.WEB),
            note=self.field("note"),
            location=self.field("location") or {},
            **self.client_meta,
        )
        self._announce(RealtimeEvent.ATTENDANCE_CHECKED_IN, user, record)
        return self.created(record.to_dict(), "Checked in.")

    def check_out(self):
        user = self.require_user()
        record = services.check_out(user, note=self.field("note"))
        self._announce(RealtimeEvent.ATTENDANCE_CHECKED_OUT, user, record)
        return self.ok(record.to_dict(), "Checked out.")

    def my_records(self):
        """The signed-in user's own attendance history."""
        user = self.require_user()
        queryset = services.list_attendance(
            user.organization,
            user=user,
            date_from=self.param("date_from"),
            date_to=self.param("date_to"),
            status=self.param("status"),
        )
        return self.paginated(queryset)

    def my_summary(self):
        user = self.require_user()
        summary = services.user_summary(
            user.organization, user,
            date_from=self.param("date_from"), date_to=self.param("date_to"),
        )
        return self.ok(summary)

    def _announce(self, event: str, user, record):
        """Tell the admin board, and echo to the user's other open tabs."""
        payload = {
            "user": {"id": str(user.id), "name": user.full_name, "email": user.email},
            "attendance": record.to_dict(),
        }
        self.emit_to_admins(event, payload)
        self.emit_to_user(user.id, event, payload)


class AttendanceAdminController(BaseController):
    """Admin-facing attendance: /api/v1/admin/attendance/*"""

    def list(self):
        self.require_permissions(Permissions.ATTENDANCE_VIEW_ALL)
        target_user = None
        if self.param("user_id"):
            target_user = get_user_in_org(self.user.organization, self.param("user_id"))

        queryset = services.list_attendance(
            self.user.organization,
            user=target_user,
            date_from=self.param("date_from"),
            date_to=self.param("date_to"),
            status=self.param("status"),
        )
        return self.paginated(queryset, serializer=self._with_user)

    def retrieve(self, record_id):
        self.require_permissions(Permissions.ATTENDANCE_VIEW_ALL)
        record = services.get_record(self.user.organization, record_id)
        return self.ok(self._with_user(record))

    def overview(self):
        """Live 'who is in today' snapshot."""
        self.require_permissions(Permissions.ATTENDANCE_VIEW_ALL)
        from core.validators import parse_date

        day = parse_date(self.param("date"), "date")
        return self.ok(services.daily_overview(self.user.organization, day))

    def user_summary(self, user_id):
        self.require_permissions(Permissions.ATTENDANCE_VIEW_ALL)
        target_user = get_user_in_org(self.user.organization, user_id)
        summary = services.user_summary(
            self.user.organization, target_user,
            date_from=self.param("date_from"), date_to=self.param("date_to"),
        )
        return self.ok(summary)

    def manual_entry(self):
        """Create or correct one employee's day."""
        self.require_permissions(Permissions.ATTENDANCE_VIEW_TEAM)
        self.require("user_id", "date")
        target_user = get_user_in_org(self.user.organization, self.field("user_id"))
        record = services.upsert_manual_entry(
            self.user.organization, target_user, self.data, approved_by=self.user
        )

        payload = {"attendance": record.to_dict(), "user_id": str(target_user.id)}
        self.emit_to_user(target_user.id, RealtimeEvent.ATTENDANCE_UPDATED, payload)
        self.emit_to_admins(RealtimeEvent.ATTENDANCE_UPDATED, payload)
        return self.created(record.to_dict(), "Attendance recorded.")

    def destroy(self, record_id):
        self.require_permissions(Permissions.ATTENDANCE_MANAGE)
        record = services.get_record(self.user.organization, record_id)
        record.soft_delete()
        self.emit_to_admins(RealtimeEvent.ATTENDANCE_UPDATED, {"deleted_id": str(record.id)})
        return self.deleted("Attendance record removed.")

    @staticmethod
    def _with_user(record) -> dict:
        """Inline the employee so the admin table needs no second request."""
        data = record.to_dict()
        user = record.user
        if user:
            data["user"] = {
                "id": str(user.id),
                "name": user.full_name,
                "email": user.email,
                "employee_id": user.employee_id,
            }
        return data
