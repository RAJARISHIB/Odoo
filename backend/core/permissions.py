"""Fine-grained permission catalogue and role -> permission resolution.

`core.constants.Role` stays the coarse "which panel/table can this user reach
at all" gate that `roles_required`/`require_roles` already checks at 50+ call
sites - that layer is not being torn out. Permissions are a finer-grained
"which specific actions can this role take" layer on top of it: a role is a
named, per-organization-editable set of permission strings (`RolePermission`
in `apps.users.models`), seeded from `DEFAULT_ROLE_PERMISSIONS` below and
editable via `PUT /api/v1/admin/roles/<role>/permissions` (see
`apps.users.controllers.RoleController`) - this is what makes roles
"configurable" per the spec instead of another hardcoded table.

Object-level checks (a user's own record vs. someone else's) are a separate
concern already covered by `BaseController.assert_self_or_admin` /
`assert_same_organization`; a permission answers "can this role ever do X",
not "can this specific user do X to this specific record".
"""
from core.constants import Role


class Permission:
    """`<resource>.<action>` permission strings."""

    EMPLOYEE_VIEW = "employee.view"
    EMPLOYEE_CREATE = "employee.create"
    EMPLOYEE_UPDATE = "employee.update"
    EMPLOYEE_DELETE = "employee.delete"

    ATTENDANCE_VIEW_OWN = "attendance.view_own"
    ATTENDANCE_VIEW_ALL = "attendance.view_all"
    ATTENDANCE_EDIT = "attendance.edit"
    ATTENDANCE_APPROVE = "attendance.approve"

    LEAVE_VIEW_OWN = "leave.view_own"
    LEAVE_VIEW_ALL = "leave.view_all"
    LEAVE_CREATE = "leave.create"
    LEAVE_APPROVE = "leave.approve"
    LEAVE_REJECT = "leave.reject"
    LEAVE_CONFIGURE = "leave.configure"

    #: No payroll module exists yet (see project decision log) - these are
    #: reserved so one can be bolted on without inventing its authorization
    #: model from scratch.
    PAYROLL_VIEW_OWN = "payroll.view_own"
    PAYROLL_VIEW_ALL = "payroll.view_all"
    PAYROLL_EDIT = "payroll.edit"
    PAYROLL_EXPORT = "payroll.export"

    #: Same - reserved for a future documents module.
    DOCUMENT_VIEW_OWN = "document.view_own"
    DOCUMENT_VIEW_EMPLOYEE = "document.view_employee"
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_DELETE = "document.delete"

    USER_MANAGE = "user.manage"
    ROLE_MANAGE = "role.manage"
    #: Reserved for a future per-user permission override; today permissions
    #: are only editable per-role, which `ROLE_MANAGE` already gates.
    PERMISSION_MANAGE = "permission.manage"

    AUDIT_VIEW = "audit.view"
    SECURITY_MANAGE = "security.manage"

    ALL = (
        EMPLOYEE_VIEW, EMPLOYEE_CREATE, EMPLOYEE_UPDATE, EMPLOYEE_DELETE,
        ATTENDANCE_VIEW_OWN, ATTENDANCE_VIEW_ALL, ATTENDANCE_EDIT, ATTENDANCE_APPROVE,
        LEAVE_VIEW_OWN, LEAVE_VIEW_ALL, LEAVE_CREATE, LEAVE_APPROVE, LEAVE_REJECT, LEAVE_CONFIGURE,
        PAYROLL_VIEW_OWN, PAYROLL_VIEW_ALL, PAYROLL_EDIT, PAYROLL_EXPORT,
        DOCUMENT_VIEW_OWN, DOCUMENT_VIEW_EMPLOYEE, DOCUMENT_UPLOAD, DOCUMENT_DELETE,
        USER_MANAGE, ROLE_MANAGE, PERMISSION_MANAGE,
        AUDIT_VIEW, SECURITY_MANAGE,
    )


#: What each role can do out of the box - least privilege first.  Every
#: role beneath SUPER_ADMIN starts with only the "own data" permissions;
#: everything else must be explicitly granted (here, or later per-org via
#: `RolePermission`).  SUPER_ADMIN is intentionally absent: `has_permission`
#: below always grants it everything, so it is never editable.
DEFAULT_ROLE_PERMISSIONS = {
    Role.ADMIN: {
        Permission.EMPLOYEE_VIEW, Permission.EMPLOYEE_CREATE,
        Permission.EMPLOYEE_UPDATE, Permission.EMPLOYEE_DELETE,
        Permission.ATTENDANCE_VIEW_OWN, Permission.ATTENDANCE_VIEW_ALL,
        Permission.ATTENDANCE_EDIT, Permission.ATTENDANCE_APPROVE,
        Permission.LEAVE_VIEW_OWN, Permission.LEAVE_VIEW_ALL, Permission.LEAVE_CREATE,
        Permission.LEAVE_APPROVE, Permission.LEAVE_REJECT, Permission.LEAVE_CONFIGURE,
        Permission.PAYROLL_VIEW_OWN,
        Permission.DOCUMENT_VIEW_OWN, Permission.DOCUMENT_VIEW_EMPLOYEE, Permission.DOCUMENT_UPLOAD,
        Permission.USER_MANAGE, Permission.ROLE_MANAGE,
        Permission.AUDIT_VIEW, Permission.SECURITY_MANAGE,
        # payroll.view_all / .edit / .export deliberately NOT granted by
        # default, even to Admin - salary access is opt-in, not role-implied.
    },
    Role.HR: {
        Permission.EMPLOYEE_VIEW, Permission.EMPLOYEE_CREATE, Permission.EMPLOYEE_UPDATE,
        Permission.ATTENDANCE_VIEW_OWN, Permission.ATTENDANCE_VIEW_ALL, Permission.ATTENDANCE_APPROVE,
        Permission.LEAVE_VIEW_OWN, Permission.LEAVE_VIEW_ALL, Permission.LEAVE_CREATE,
        Permission.LEAVE_APPROVE, Permission.LEAVE_REJECT, Permission.LEAVE_CONFIGURE,
        Permission.PAYROLL_VIEW_OWN,
        Permission.DOCUMENT_VIEW_OWN, Permission.DOCUMENT_VIEW_EMPLOYEE, Permission.DOCUMENT_UPLOAD,
        # user.manage / audit.view / payroll.* / role.manage: grantable, not default.
    },
    Role.MANAGER: {
        Permission.ATTENDANCE_VIEW_OWN,
        Permission.LEAVE_VIEW_OWN, Permission.LEAVE_CREATE,
        Permission.PAYROLL_VIEW_OWN,
        Permission.DOCUMENT_VIEW_OWN, Permission.DOCUMENT_UPLOAD,
        # No team-scoped visibility by default - "manager = all employee
        # access" is exactly what the spec says not to do.  Grant
        # leave.approve / attendance.view_all explicitly per-org if wanted.
    },
    Role.EMPLOYEE: {
        Permission.ATTENDANCE_VIEW_OWN,
        Permission.LEAVE_VIEW_OWN, Permission.LEAVE_CREATE,
        Permission.PAYROLL_VIEW_OWN,
        Permission.DOCUMENT_VIEW_OWN, Permission.DOCUMENT_UPLOAD,
    },
}

#: Rank used only to decide which roles a creator/editor may assign to
#: someone else (see `apps.users.services.create_user` /
#: `_assert_can_assign_role`) - never used for permission checks themselves.
ROLE_RANK = {
    Role.SUPER_ADMIN: 100,
    Role.ADMIN: 80,
    Role.HR: 50,
    Role.MANAGER: 30,
    Role.EMPLOYEE: 10,
}


def default_permissions_for(role: str) -> set:
    if role == Role.SUPER_ADMIN:
        return set(Permission.ALL)
    return set(DEFAULT_ROLE_PERMISSIONS.get(role, ()))


def effective_permissions(organization, role: str) -> set:
    """The permission set actually in effect for `role` in `organization`.

    SUPER_ADMIN always gets everything and is not stored/editable. Every
    other role falls back to `DEFAULT_ROLE_PERMISSIONS` until an org saves a
    `RolePermission` override for it.
    """
    if role == Role.SUPER_ADMIN:
        return set(Permission.ALL)

    from apps.users.models import RolePermission

    override = RolePermission.objects.filter(organization=organization, role=role).first()
    if override is not None:
        return set(override.permissions)
    return default_permissions_for(role)


def has_permission(user, permission: str) -> bool:
    if not user:
        return False
    if user.role == Role.SUPER_ADMIN:
        return True
    return permission in effective_permissions(user.organization, user.role)


#: The blast radius here is large enough (org-wide role edits, security
#: settings, the audit trail, bulk salary access) that holding the
#: permission is not enough - the account itself must not be a single
#: password away from compromise.  Everything else stays reachable without
#: MFA so an org isn't locked out of day-to-day admin work by this alone.
MFA_REQUIRED_PERMISSIONS = frozenset({
    Permission.ROLE_MANAGE,
    Permission.PERMISSION_MANAGE,
    Permission.SECURITY_MANAGE,
    Permission.AUDIT_VIEW,
    Permission.PAYROLL_VIEW_ALL,
    Permission.PAYROLL_EXPORT,
})


def assert_mfa_satisfied(user, permission: str):
    """Raise `MfaRequired` if `permission` is high-risk and `user` has not
    turned MFA on.  SUPER_ADMIN is not exempt - "highly privileged" is
    exactly who this is for."""
    from core.exceptions import MfaRequired

    if permission in MFA_REQUIRED_PERMISSIONS and not user.mfa_enabled:
        raise MfaRequired()


def assert_can_assign_role(assigner_role: str, target_role: str):
    """A creator/editor may only hand out a role ranked below their own.

    SUPER_ADMIN is exempt (an org must be able to mint co-super-admins).
    This is what stops, e.g., an HR account provisioning a new SUPER_ADMIN
    or ADMIN account through the ordinary "create employee" form.
    """
    from core.exceptions import PermissionDenied

    if assigner_role == Role.SUPER_ADMIN:
        return
    assigner_rank = ROLE_RANK.get(assigner_role, 0)
    target_rank = ROLE_RANK.get(target_role, 0)
    if target_rank >= assigner_rank:
        raise PermissionDenied(
            "You cannot assign a role equal to or higher than your own.",
            code="role_assignment_denied",
        )
