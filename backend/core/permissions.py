"""Security policy that sits on top of the dynamic RBAC system.

Role -> permission resolution itself lives on `apps.users.models.Role`
(per-organization, DB-backed, editable via `apps.users.controllers.RoleController`)
and `User.has_permission`. This module adds two things the role/permission
model alone does not cover:

- `assert_mfa_satisfied` - a handful of high-risk permissions require the
  caller to have MFA turned on, regardless of what their role grants.
- `assert_can_assign_role` - a creator/editor may not hand out a role ranked
  at or above their own, even if they hold `roles.assign` - otherwise an HR
  account could use the ordinary "create employee" form to provision a new
  SUPER_ADMIN.

Object-level checks (a user's own record vs. someone else's) are a separate
concern already covered by `BaseController.assert_self_or_admin` /
`assert_same_organization`.
"""
from core.constants import Permissions, Role


#: The blast radius here is large enough (org-wide role edits, security
#: settings, the audit trail) that holding the permission is not enough -
#: the account itself must not be a single password away from compromise.
#: Everything else stays reachable without MFA so an org isn't locked out of
#: day-to-day admin work by this alone.
MFA_REQUIRED_PERMISSIONS = frozenset({
    Permissions.ROLES_MANAGE,
    Permissions.ROLES_ASSIGN,
    Permissions.SECURITY_MANAGE,
    Permissions.AUDIT_VIEW,
})


def assert_mfa_satisfied(user, permission: str):
    """Raise `MfaRequired` if `permission` is high-risk and `user` has not
    turned MFA on. No role is exempt - "highly privileged" is exactly who
    this is for."""
    from core.exceptions import MfaRequired

    if permission in MFA_REQUIRED_PERMISSIONS and not getattr(user, "mfa_enabled", False):
        raise MfaRequired()


#: Rank used only to decide which of the five built-in roles a creator/editor
#: may assign to someone else (see `apps.users.services.create_user` /
#: `update_user`) - never used for permission checks themselves. Custom,
#: org-defined roles (not one of these five slugs) rank at 0, so only
#: SUPER_ADMIN may hand them out until an org's own policy says otherwise.
ROLE_RANK = {
    Role.SUPER_ADMIN: 100,
    Role.ADMIN: 80,
    Role.HR: 50,
    Role.MANAGER: 30,
    Role.EMPLOYEE: 10,
}


def assert_can_assign_role(assigner_role_slug, target_role_slug):
    """A creator/editor may only hand out a role ranked below their own.

    SUPER_ADMIN is exempt (an org must be able to mint co-super-admins).
    This is what stops, e.g., an HR account provisioning a new SUPER_ADMIN
    or ADMIN account through the ordinary "create employee" form.
    """
    from core.exceptions import PermissionDenied

    if assigner_role_slug == Role.SUPER_ADMIN:
        return
    assigner_rank = ROLE_RANK.get(assigner_role_slug, 0)
    target_rank = ROLE_RANK.get(target_role_slug, 0)
    if target_rank >= assigner_rank:
        raise PermissionDenied(
            "You cannot assign a role equal to or higher than your own.",
            code="role_assignment_denied",
        )
