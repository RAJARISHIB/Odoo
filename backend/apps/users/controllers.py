import logging

logger = logging.getLogger(__name__)


"""User + auth controllers.

Each public method maps 1:1 to a route in `apps/users/urls.py`.  They read the
request through `BaseController`, delegate the work to `services.py`, and return
the standard envelope.
"""
from apps.users import services
from apps.users.models import Role as RoleDoc, User
from core.base_controller import BaseController
from core.constants import AuditAction, Permissions, RealtimeEvent, Role as RoleEnum
from core.exceptions import NotFound, ValidationError
from core.ratelimit import check_and_increment
from core.realtime import panel_channel, user_channel


class AuthController(BaseController):
    """Public authentication surface: /api/v1/auth/*"""

    def register(self):
        """Bootstrap an organization and its first super admin.

        Accepts JSON, or multipart when the signup form carries a company logo.
        """
        self.require("organization_name", "email", "password")
        result = services.register_organization(
            self.data, logo=self.file("logo"), **self._session_meta()
        )
        return self.created(
            result,
            "Organization registered. Your login ID is {}.".format(result["user"]["login_id"]),
        )

    def login(self):
        """Sign in with either a login ID or an email address.

        The form has one field for both; `identifier` is what the UI sends, and
        `login_id` / `email` are accepted as aliases.
        """
        identifier = self.field("identifier") or self.field("login_id") or self.field("email")
        if not identifier:
            raise ValidationError(
                "Enter your login ID or email.",
                details={"identifier": "This field is required."},
            )
        self.require("password")

        # IP + identifier, not just IP: keyed together so one abusive client
        # can't exhaust the budget for every account behind a shared IP
        # (office NAT, corporate VPN), while still rate-limiting real abuse.
        check_and_increment(
            "login", "{}:{}".format(self.client_meta["ip_address"], identifier.lower()),
            limit=10, window_seconds=15 * 60,
        )

        result = services.login(identifier, self.field("password"), **self._session_meta())
        if result.get("mfa_required"):
            return self.ok(result, "Enter your authentication code to continue.")

        result["realtime"] = self._realtime_hints(result["user"])
        return self.ok(result, "Signed in successfully.")

    def mfa_verify(self):
        """Second login step for an MFA-enabled account - exchanges the
        `mfa_pending_token` from `login()` plus a TOTP/recovery code for a
        real session."""
        self.require("mfa_pending_token", "code")
        check_and_increment(
            "mfa_verify", self.client_meta["ip_address"], limit=10, window_seconds=15 * 60,
        )
        result = services.verify_mfa_login(
            self.field("mfa_pending_token"), self.field("code"), **self._session_meta()
        )
        result["realtime"] = self._realtime_hints(result["user"])
        return self.ok(result, "Signed in successfully.")

    def refresh(self):
        """Exchange a refresh token for a new pair (the old one is revoked)."""
        self.require("refresh_token")
        result = services.refresh_session(self.field("refresh_token"), **self._session_meta())
        return self.ok(result, "Session refreshed.")

    def get_invite_details(self):
        """Public endpoint to fetch invitation details using an invite token."""
        token = self.param("token") or self.field("token")
        result = services.get_invite_details(token)
        return self.ok(result)

    def accept_invite(self):
        """Public endpoint to accept an invitation and set password."""
        token = self.field("token")
        result = services.accept_invitation(token, self.data, **self._session_meta())
        return self.ok(result, result.get("message", "Invitation accepted successfully."))

    def logout(self):
        """Revoke this session, or every session with `?all=true`."""
        all_sessions = self.param("all", "false").lower() == "true"
        revoked = services.logout(
            refresh_token=self.field("refresh_token"),
            user=self.user,
            all_sessions=all_sessions,
        )
        if self.user:
            self.audit(
                AuditAction.LOGOUT,
                resource_type="user", resource_id=str(self.user.id),
                metadata={"all_sessions": all_sessions, "revoked": revoked},
            )
        return self.ok({"revoked_sessions": revoked}, "Signed out.")

    def me(self):
        """Current identity + the metadata the UI needs to pick a panel."""
        user = self.require_user()
        organization = user.organization
        return self.ok(
            {
                "user": user.to_dict(),
                "organization": organization.to_dict() if organization else None,
                "permissions": self._permissions(user),
                "realtime": self._realtime_hints(user.to_dict()),
            }
        )

    def sessions(self):
        """Active refresh sessions - powers a "signed-in devices" screen."""
        user = self.require_user()
        current_sid = (self.token_payload or {}).get("sid")
        items = [
            {
                "id": str(session.id),
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "expires_at": session.expires_at.isoformat() if session.expires_at else None,
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
                "is_current": bool(current_sid) and session.jti == current_sid,
            }
            for session in services.list_sessions(user)
        ]
        return self.ok(items, meta={"total": len(items)})

    def revoke_session(self, session_id):
        """Sign out one specific *other* device from the sessions list -
        distinct from `logout`, which only ever acts on the caller's own
        current session or all of them at once."""
        user = self.require_user()
        self.object_id(session_id)
        revoked = services.revoke_session(user, session_id)
        self.audit(
            AuditAction.SESSION_REVOKED, resource_type="session", resource_id=session_id,
            result="success" if revoked else "not_found",
        )
        return self.ok({"revoked": revoked}, "Session signed out." if revoked else "Session not found.")

    def change_password(self):
        user = self.require_user()
        self.require("current_password", "new_password")
        services.change_password(user, self.field("current_password"), self.field("new_password"))
        self.audit(AuditAction.PASSWORD_CHANGED, resource_type="user", resource_id=str(user.id))
        return self.ok(None, "Password updated. Please sign in again.")

    def forgot_password(self):
        """Always answers the same way, whether or not the account exists -
        this is the anti-enumeration behaviour the security spec asks for."""
        self.require("identifier")
        identifier = self.field("identifier")
        check_and_increment(
            "forgot_password", "{}:{}".format(self.client_meta["ip_address"], identifier.lower()),
            limit=5, window_seconds=15 * 60,
        )
        services.request_password_reset(identifier, **self._session_meta())
        return self.ok(None, "If an account exists for that email or login ID, a reset link has been sent.")

    def reset_password(self):
        self.require("token", "new_password")
        services.reset_password_with_token(
            self.field("token"), self.field("new_password"), **self._session_meta()
        )
        return self.ok(None, "Password reset. Please sign in with your new password.")

    def verify_email(self):
        self.require("token")
        services.verify_email_token(self.field("token"))
        return self.ok(None, "Email verified.")

    def resend_verification(self):
        user = self.require_user()
        check_and_increment(
            "resend_verification", str(user.id), limit=3, window_seconds=15 * 60,
        )
        services.send_verification_email(user)
        return self.ok(None, "Verification email sent.")

    # -- helpers -----------------------------------------------------------
    def _session_meta(self) -> dict:
        return self.client_meta
    @staticmethod
    def _permissions(user) -> dict:
        """Capability flags the Angular guards and menus read.

        Includes both the original coarse flags (kept for existing UI code)
        and every fine-grained permission string from `core.constants.Permissions`,
        so `capabilityGuard('leaves.approve')`-style route guards can check the
        same permission the backend actually enforces - see `User.has_permission`.
        """
        flags = {
            "panel": user.panel,
            # True until a system-generated password has been replaced.
            "must_change_password": bool(user.must_change_password),
            "mfa_enabled": bool(user.mfa_enabled),
            "can_manage_users": user.has_permission(Permissions.USERS_EDIT) or user.has_permission(Permissions.USERS_CREATE),
            "can_manage_organization": user.has_permission(Permissions.ORG_MANAGE),
            "can_view_all_attendance": user.has_permission(Permissions.ATTENDANCE_VIEW_ALL),
            "can_approve_attendance": user.has_permission(Permissions.ATTENDANCE_MANAGE) or user.has_permission(Permissions.ATTENDANCE_VIEW_TEAM),
        }
        for permission in Permissions.ALL:
            flags[permission] = user.has_permission(permission)
        return flags


    @staticmethod
    def _realtime_hints(user_dict: dict) -> dict:
        """Which websocket channels this client should subscribe to on connect."""
        org_id = user_dict.get("organization_id")
        channels = [user_channel(user_dict["id"])]
        if org_id:
            channels.append(panel_channel(org_id, user_dict.get("panel")))
        return {"channels": channels}


class UserController(BaseController):
    """Admin-side employee directory: /api/v1/users/*"""

    def list(self):
        self.require_permissions(Permissions.USERS_VIEW)
        queryset = services.search_users(
            self.user.organization,
            search=self.param("search"),
            role=self.param("role"),
            status=self.param("status"),
            department_id=self.param("department_id"),
        )
        return self.paginated(queryset)

    def create(self):
        """Provision an employee.

        The system allocates the login ID, and a first-time password too unless
        the admin supplied one - a normal user never registers themselves.
        """
        self.require_permissions(Permissions.USERS_EDIT)
        self.require("email")
        # The form may send a single "name" or separate first/last names.
        if not self.field("name") and not self.field("first_name"):
            raise ValidationError(
                "The employee's name is required.", details={"name": "This field is required."}
            )

        user, temporary_password = services.create_user(
            self.user.organization, self.data, created_by=self.user
        )

        payload = user.to_dict()
        if temporary_password:
            # Returned once, never stored in clear - the admin passes it on.
            payload["temporary_password"] = temporary_password

        self.audit(
            AuditAction.USER_CREATED, resource_type="user", resource_id=str(user.id),
            metadata={"role": user.role},
        )
        self.notify_relevant(RealtimeEvent.USER_CREATED, {"user": user.to_dict()}, subject_user=user)
        return self.created(
            payload, "Employee created. Login ID: {}.".format(user.login_id)
        )

    def invite(self):
        """Send an email invitation to a new employee."""
        self.require_roles(RoleEnum.SUPER_ADMIN, RoleEnum.ADMIN, RoleEnum.HR)
        self.require("email", "first_name")
        result = services.invite_employee(self.user.organization, inviter=self.user, data=self.data)
        self.emit_to_admins(RealtimeEvent.USER_CREATED, {"user": result["user"]})
        return self.created(result, result.get("message", "Employee invitation sent."))

    def retrieve(self, user_id):
        self.assert_self_or_admin(user_id)
        user = services.get_user_in_org(self.user.organization, user_id)
        return self.ok(user.to_dict())

    def update(self, user_id):
        self.assert_self_or_admin(user_id)
        user = services.get_user_in_org(self.user.organization, user_id)
        role_changing = "role" in self.data and self.data["role"] != user.role
        if role_changing:
            # A role change is a privilege change, not an ordinary profile
            # edit - it needs a recently-proven session even if this one
            # hasn't expired yet.
            self.require_step_up()
        previous_role = user.role
        user = services.update_user(user, self.data, editor=self.user)

        if role_changing:
            self.audit(
                AuditAction.ROLE_CHANGED, resource_type="user", resource_id=str(user.id),
                metadata={"from": previous_role, "to": user.role},
            )
        else:
            self.audit(AuditAction.USER_UPDATED, resource_type="user", resource_id=str(user.id))

        self.emit_to_user(user.id, RealtimeEvent.USER_UPDATED, {"user": user.to_dict()})
        self.notify_relevant(RealtimeEvent.USER_UPDATED, {"user": user.to_dict()}, subject_user=user)
        return self.ok(user.to_dict(), "Employee updated.")

    def destroy(self, user_id):
        """Soft delete - the document stays for attendance history."""
        self.require_permissions(Permissions.USERS_CREATE)
        if self.is_self(user_id):
            raise ValidationError("You cannot delete your own account.")
        user = services.get_user_in_org(self.user.organization, user_id)
        services.assert_editable_by(self.user, user)
        user.soft_delete()
        services.logout(user=user, all_sessions=True)

        self.audit(AuditAction.USER_DELETED, resource_type="user", resource_id=str(user.id))
        self.notify_relevant(
            RealtimeEvent.USER_STATUS_CHANGED, {"user_id": str(user.id), "status": "deleted"}, subject_user=user
        )
        return self.deleted("Employee removed.")

    def reset_password(self, user_id):
        self.require_permissions(Permissions.USERS_EDIT)
        user = services.get_user_in_org(self.user.organization, user_id)
        # A password reset is as consequential as an edit - it hands the actor
        # the target's account outright, so it gets the same hierarchy guard.
        services.assert_editable_by(self.user, user)
        temporary_password = services.reset_password(user, self.field("new_password"))

        self.audit(AuditAction.ADMIN_PASSWORD_RESET, resource_type="user", resource_id=str(user.id))
        self.emit_to_user(user.id, RealtimeEvent.NOTIFICATION,
                          {"title": "Password reset", "body": "An admin reset your password."})
        return self.ok({"temporary_password": temporary_password}, "Password reset.")

    def stats(self):
        """Headline counters for the admin dashboard."""
        self.require_permissions(Permissions.USERS_VIEW)
        queryset = User.objects.filter(organization=self.user.organization, is_deleted=False)
        roles = RoleDoc.objects.filter(organization=self.user.organization) if self.user.organization else []
        by_role = {r.name: queryset.filter(role=r).count() for r in roles}
        return self.ok(
            {
                "total": queryset.count(),
                "active": queryset.filter(status="active").count(),
                "suspended": queryset.filter(status="suspended").count(),
                "by_role": by_role,
            }
        )


class SecurityController(BaseController):
    """Self-service MFA: /api/v1/security/mfa/*

    Enrollment (`enroll_start`/`enroll_confirm`) needs no step-up - turning
    MFA *on* only strengthens the account. Turning it off, or replacing the
    recovery codes, demands the caller's password plus one more MFA code -
    see `services.mfa_disable` / `mfa_regenerate_recovery_codes`.
    """

    def enroll_start(self):
        user = self.require_user()
        data = services.mfa_enroll_start(user)
        return self.ok(
            {
                "secret": data["secret"],
                "otpauth_uri": data["otpauth_uri"],
                "qr_svg": _totp_qr_svg(data["otpauth_uri"]),
            },
            "Scan the QR code (or enter the secret manually), then confirm with a code.",
        )

    def enroll_confirm(self):
        user = self.require_user()
        self.require("code")
        recovery_codes = services.mfa_enroll_confirm(user, self.field("code"))
        self.audit(AuditAction.MFA_ENABLED, resource_type="user", resource_id=str(user.id))
        return self.ok(
            {"recovery_codes": recovery_codes},
            "MFA enabled. Save these recovery codes now - they will not be shown again.",
        )

    def disable(self):
        user = self.require_user()
        self.require_step_up()
        self.require("current_password", "code")
        services.mfa_disable(user, self.field("current_password"), self.field("code"))
        self.audit(AuditAction.MFA_DISABLED, resource_type="user", resource_id=str(user.id))
        return self.ok(None, "MFA disabled. You have been signed out on all other devices.")

    def regenerate_recovery_codes(self):
        user = self.require_user()
        self.require_step_up()
        self.require("current_password", "code")
        recovery_codes = services.mfa_regenerate_recovery_codes(
            user, self.field("current_password"), self.field("code")
        )
        self.audit(
            AuditAction.MFA_RECOVERY_CODES_REGENERATED, resource_type="user", resource_id=str(user.id)
        )
        return self.ok(
            {"recovery_codes": recovery_codes},
            "Recovery codes regenerated. The old ones no longer work.",
        )


def _totp_qr_svg(data: str) -> str:
    """Renders `data` (the `otpauth://` URI) as an inline SVG string - no
    Pillow, no client-side QR library needed."""
    import io

    import qrcode
    import qrcode.image.svg

    image = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


class AuditController(BaseController):
    """Read-only view onto the security audit trail: /api/v1/admin/audit-logs

    There is deliberately no create/update/delete action here - entries are
    only ever written by `core.audit.record` from inside other controllers/
    services, never accepted from a client. See `core.audit.AuditLog`.
    """

    def list(self):
        self.require_permissions(Permissions.AUDIT_VIEW)
        from core.audit import AuditLog

        queryset = AuditLog.objects.filter(organization=self.user.organization)

        action = self.param("action")
        if action:
            queryset = queryset.filter(action=action)
        actor_id = self.param("actor_id")
        if actor_id:
            queryset = queryset.filter(actor=self.object_id(actor_id, "actor_id"))
        resource_type = self.param("resource_type")
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        result = self.param("result")
        if result:
            queryset = queryset.filter(result=result)

        return self.paginated(queryset.order_by("-created_at"))


class ProfileController(BaseController):
    """The signed-in user's own record: /api/v1/profile"""

    def retrieve(self):
        user = self.require_user()
        return self.ok(user.to_dict())

    def update(self):
        user = self.require_user()
        # Self-service edits never carry privilege changes.
        data = {k: v for k, v in self.data.items() if k not in ("role", "status", "department_id")}
        user = services.update_user(user, data, editor=None)
        self.emit_to_user(user.id, RealtimeEvent.USER_UPDATED, {"user": user.to_dict()})
        return self.ok(user.to_dict(), "Profile updated.")


class RoleController(BaseController):
    """Configurable RBAC: per-organization custom roles.

    Every route here is already permission-gated at the view layer (see
    `apps/users/views.py`, `roles.view` / `roles.manage` / `roles.assign`),
    and `roles.manage` / `roles.assign` additionally require MFA - see
    `core.permissions.MFA_REQUIRED_PERMISSIONS` - since a role edit changes
    what every holder of that role can do.
    """

    def catalog(self):
        """The full permission catalogue, grouped by module, for the role editor UI."""
        return self.ok(Permissions.CATALOG)

    def list(self):
        roles = services.list_roles(self.user.organization)
        return self.ok([r.to_dict() for r in roles])

    def retrieve(self, role_id: str):
        role = services.get_role(self.user.organization, role_id)
        if not role:
            raise NotFound("Role not found.")

        data = role.to_dict()
        data["users_count"] = services.get_role_users_count(role)
        return self.ok(data)

    def create(self):
        self.require("name", "permissions")
        self.require_step_up()
        role = services.create_role(
            organization=self.user.organization,
            name=self.field("name"),
            description=self.field("description", ""),
            permissions=self.field("permissions"),
        )
        self.audit(
            AuditAction.PERMISSION_CHANGED, resource_type="role", resource_id=str(role.id),
            metadata={"action": "created", "permissions": role.permissions},
        )
        return self.created(role.to_dict(), "Role created successfully.")

    def update(self, role_id: str):
        self.require_step_up()
        role = services.update_role(
            organization=self.user.organization,
            role_id=role_id,
            name=self.field("name"),
            description=self.field("description"),
            permissions=self.field("permissions"),
        )
        self.audit(
            AuditAction.PERMISSION_CHANGED, resource_type="role", resource_id=str(role.id),
            metadata={"action": "updated", "permissions": role.permissions},
        )
        return self.ok(role.to_dict(), "Role updated successfully.")

    def destroy(self, role_id: str):
        self.require_step_up()
        services.delete_role(self.user.organization, role_id)
        self.audit(AuditAction.PERMISSION_CHANGED, resource_type="role", resource_id=role_id,
                   metadata={"action": "deleted"})
        return self.deleted("Role deleted.")

    def assign(self, role_id: str):
        self.require("user_ids")
        self.require_step_up()
        services.assign_role(self.user.organization, role_id, self.field("user_ids"))
        self.audit(
            AuditAction.ROLE_CHANGED, resource_type="role", resource_id=role_id,
            metadata={"user_ids": self.field("user_ids")},
        )
        return self.ok(None, "Role assigned successfully.")
