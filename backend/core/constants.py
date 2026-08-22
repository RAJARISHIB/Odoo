"""Enumerations shared across apps, the websocket layer and the UI contract."""


class Role:
    """A user's capability level.  Anything at or above HR reaches the admin panel."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    HR = "hr"
    MANAGER = "manager"
    EMPLOYEE = "employee"

    ALL = (SUPER_ADMIN, ADMIN, HR, MANAGER, EMPLOYEE)
    ADMIN_PANEL = (SUPER_ADMIN, ADMIN, HR, MANAGER)
    CHOICES = ALL


class UserStatus:
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"

    ALL = (ACTIVE, INVITED, SUSPENDED, ARCHIVED)


class AttendanceStatus:
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    HALF_DAY = "half_day"
    ON_LEAVE = "on_leave"
    HOLIDAY = "holiday"

    ALL = (PRESENT, ABSENT, LATE, HALF_DAY, ON_LEAVE, HOLIDAY)


class AttendanceSource:
    WEB = "web"
    MOBILE = "mobile"
    BIOMETRIC = "biometric"
    MANUAL = "manual"

    ALL = (WEB, MOBILE, BIOMETRIC, MANUAL)


class Panel:
    ADMIN = "admin"
    USER = "user"

    ALL = (ADMIN, USER)


class LeaveAllocationFrequency:
    """How often a `LeaveAllocationRule` credits leave. Used by the admin leave
    module only - see apps/leaves/models.py."""

    MONTHLY = "monthly"
    YEARLY = "yearly"

    ALL = (MONTHLY, YEARLY)


class RealtimeEvent:
    """Event names published to the websocket hub.  Keep in sync with the
    Angular `RealtimeService` and `realtime/src/lib/events.js`."""

    ATTENDANCE_CHECKED_IN = "attendance.checked_in"
    ATTENDANCE_CHECKED_OUT = "attendance.checked_out"
    ATTENDANCE_UPDATED = "attendance.updated"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_STATUS_CHANGED = "user.status_changed"
    LEAVE_REQUEST_CREATED = "leave.request_created"
    LEAVE_REQUEST_UPDATED = "leave.request_updated"
    LEAVE_TYPE_UPDATED = "leave.type_updated"
    LEAVE_ALLOCATION_UPDATED = "leave.allocation_updated"
    LEAVE_BALANCE_UPDATED = "leave.balance_updated"
    HOLIDAY_UPDATED = "holiday.updated"
    ORG_UPDATED = "organization.updated"
    NOTIFICATION = "notification"
    SYSTEM_ANNOUNCEMENT = "system.announcement"
