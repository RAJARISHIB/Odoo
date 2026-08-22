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

class Permissions:
    # Users & Directory
    USERS_VIEW = 'users.view'
    USERS_CREATE = 'users.create'
    USERS_EDIT = 'users.edit'
    USERS_DELETE = 'users.delete'
    USERS_RESET_PASSWORD = 'users.reset_password'

    # Attendance
    ATTENDANCE_PUNCH = 'attendance.punch'
    ATTENDANCE_VIEW_OWN = 'attendance.view_own'
    ATTENDANCE_VIEW_TEAM = 'attendance.view_team'
    ATTENDANCE_VIEW_ALL = 'attendance.view_all'
    ATTENDANCE_MANAGE = 'attendance.manage'

    # Leaves
    LEAVES_APPLY = 'leaves.apply'
    LEAVES_VIEW_OWN = 'leaves.view_own'
    LEAVES_VIEW_TEAM = 'leaves.view_team'
    LEAVES_VIEW_ALL = 'leaves.view_all'
    LEAVES_APPROVE = 'leaves.approve'
    LEAVES_MANAGE_TYPES = 'leaves.manage_types'

    # Organization
    ORG_VIEW = 'org.view'
    ORG_MANAGE = 'org.manage'
    DEPARTMENTS_MANAGE = 'departments.manage'

    # Roles
    ROLES_VIEW = 'roles.view'
    ROLES_MANAGE = 'roles.manage'
    ROLES_ASSIGN = 'roles.assign'

    # Security & audit
    AUDIT_VIEW = 'audit.view'
    SECURITY_MANAGE = 'security.manage'

    # Payroll
    PAYROLL_VIEW_ALL = 'payroll.view_all'
    PAYROLL_MANAGE = 'payroll.manage'

    # Claims, fines & employee requests
    CLAIMS_VIEW_ALL = 'claims.view_all'
    CLAIMS_MANAGE = 'claims.manage'

    ALL = (
        USERS_VIEW, USERS_CREATE, USERS_EDIT, USERS_DELETE, USERS_RESET_PASSWORD,
        ATTENDANCE_PUNCH, ATTENDANCE_VIEW_OWN, ATTENDANCE_VIEW_TEAM, ATTENDANCE_VIEW_ALL, ATTENDANCE_MANAGE,
        LEAVES_APPLY, LEAVES_VIEW_OWN, LEAVES_VIEW_TEAM, LEAVES_VIEW_ALL, LEAVES_APPROVE, LEAVES_MANAGE_TYPES,
        ORG_VIEW, ORG_MANAGE, DEPARTMENTS_MANAGE,
        ROLES_VIEW, ROLES_MANAGE, ROLES_ASSIGN,
        AUDIT_VIEW, SECURITY_MANAGE,
        PAYROLL_VIEW_ALL, PAYROLL_MANAGE,
        CLAIMS_VIEW_ALL, CLAIMS_MANAGE,
    )

    CATALOG = [
        {
            'module': 'users',
            'label': 'Users & Directory',
            'permissions': [
                {'key': USERS_VIEW, 'label': 'View Users', 'description': 'Browse employee directory and view profiles.'},
                {'key': USERS_CREATE, 'label': 'Create Users', 'description': 'Add or invite new employees.'},
                {'key': USERS_EDIT, 'label': 'Edit Users', 'description': 'Modify employee profiles and assignments.'},
                {'key': USERS_DELETE, 'label': 'Delete Users', 'description': 'Deactivate or archive employee accounts.'},
                {'key': USERS_RESET_PASSWORD, 'label': 'Reset Passwords', 'description': 'Trigger manual password resets for employees.'}
            ]
        },
        {
            'module': 'attendance',
            'label': 'Attendance',
            'permissions': [
                {'key': ATTENDANCE_PUNCH, 'label': 'Check In/Out', 'description': 'Allow user to punch in and out.'},
                {'key': ATTENDANCE_VIEW_OWN, 'label': 'View Own Attendance', 'description': 'View personal punch logs.'},
                {'key': ATTENDANCE_VIEW_TEAM, 'label': 'View Team Attendance', 'description': 'View attendance for direct reports.'},
                {'key': ATTENDANCE_VIEW_ALL, 'label': 'View All Attendance', 'description': 'View organization-wide attendance records.'},
                {'key': ATTENDANCE_MANAGE, 'label': 'Manage Attendance', 'description': 'Manually correct or approve punch times.'}
            ]
        },
        {
            'module': 'leaves',
            'label': 'Leaves & Time Off',
            'permissions': [
                {'key': LEAVES_APPLY, 'label': 'Apply for Leave', 'description': 'Submit leave requests for oneself.'},
                {'key': LEAVES_VIEW_OWN, 'label': 'View Own Leaves', 'description': 'View own leave history and balances.'},
                {'key': LEAVES_VIEW_TEAM, 'label': 'View Team Leaves', 'description': 'View team leave calendar.'},
                {'key': LEAVES_VIEW_ALL, 'label': 'View All Leaves', 'description': 'View organization-wide leave calendar.'},
                {'key': LEAVES_APPROVE, 'label': 'Approve Leaves', 'description': 'Approve or reject leave applications.'},
                {'key': LEAVES_MANAGE_TYPES, 'label': 'Manage Leave Types', 'description': 'Configure leave categories and quotas.'}
            ]
        },
        {
            'module': 'organization',
            'label': 'Organization & Departments',
            'permissions': [
                {'key': ORG_VIEW, 'label': 'View Organization', 'description': 'View organization details and departments.'},
                {'key': ORG_MANAGE, 'label': 'Manage Organization', 'description': 'Update company profile and settings.'},
                {'key': DEPARTMENTS_MANAGE, 'label': 'Manage Departments', 'description': 'Create, edit, and delete departments.'}
            ]
        },
        {
            'module': 'roles',
            'label': 'Roles & Access Control',
            'permissions': [
                {'key': ROLES_VIEW, 'label': 'View Roles', 'description': 'View roles and assigned permissions.'},
                {'key': ROLES_MANAGE, 'label': 'Manage Roles', 'description': 'Create, edit, and delete custom roles.'},
                {'key': ROLES_ASSIGN, 'label': 'Assign Roles', 'description': 'Assign roles to employees.'}
            ]
        },
        {
            'module': 'security',
            'label': 'Security & Audit',
            'permissions': [
                {'key': AUDIT_VIEW, 'label': 'View Audit Log', 'description': 'Read the security audit trail.'},
                {'key': SECURITY_MANAGE, 'label': 'Manage Security Settings', 'description': 'Manage organization-wide security settings.'}
            ]
        },
        {
            'module': 'payroll',
            'label': 'Payroll',
            'permissions': [
                {'key': PAYROLL_VIEW_ALL, 'label': 'View All Payroll', 'description': 'View salary templates, assignments and documents for any employee.'},
                {'key': PAYROLL_MANAGE, 'label': 'Manage Payroll', 'description': 'Configure salary templates, assign employee payroll, and manage payroll documents.'}
            ]
        },
        {
            'module': 'claims',
            'label': 'Claims, Fines & Requests',
            'permissions': [
                {'key': CLAIMS_VIEW_ALL, 'label': 'View All Claims', 'description': 'View expense claims, fines and requests for any employee.'},
                {'key': CLAIMS_MANAGE, 'label': 'Manage Claims', 'description': 'Approve or reject expense claims, fines and employee requests.'}
            ]
        }
    ]

