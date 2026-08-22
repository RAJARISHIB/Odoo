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


class AuditAction:
    """Security-relevant event names written to `core.audit.AuditLog`.

    Distinct from `RealtimeEvent` below: realtime events are UI push
    notifications, these are the accountability record - see `core.audit`.
    """

    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILED = "login.failed"
    LOGOUT = "logout"
    ACCOUNT_LOCKED = "account.locked"

    PASSWORD_CHANGED = "password.changed"
    PASSWORD_RESET_REQUESTED = "password.reset_requested"
    PASSWORD_RESET_COMPLETED = "password.reset_completed"
    ADMIN_PASSWORD_RESET = "password.admin_reset"

    EMAIL_VERIFIED = "email.verified"

    MFA_CHALLENGE_ISSUED = "mfa.challenge_issued"
    MFA_ENABLED = "mfa.enabled"
    MFA_DISABLED = "mfa.disabled"
    MFA_FAILED = "mfa.failed"
    MFA_RECOVERY_CODES_REGENERATED = "mfa.recovery_codes_regenerated"

    ROLE_CHANGED = "role.changed"
    PERMISSION_CHANGED = "permission.changed"

    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"

    SESSION_REVOKED = "session.revoked"

    LEAVE_APPROVED = "leave.approved"
    LEAVE_REJECTED = "leave.rejected"
    LEAVE_BALANCE_ADJUSTED = "leave.balance_adjusted"
    HOLIDAY_CHANGED = "holiday.changed"

    ACCESS_DENIED = "access.denied"


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
