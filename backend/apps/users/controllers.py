"""User + auth controllers.

Each public method maps 1:1 to a route in `apps/users/urls.py`.  They read the
request through `BaseController`, delegate the work to `services.py`, and return
the standard envelope.
"""
from apps.users import services
from apps.users.models import RolePermission, User
from core.base_controller import BaseController
from core.constants import AuditAction, RealtimeEvent, Role
from core.exceptions import ValidationError
from core.permissions import Permission, default_permissions_for, effective_permissions, has_permission
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
        and every fine-grained permission string from `core.permissions`, so
        `capabilityGuard('leave.approve')`-style route guards can check the
        same permission the backend actually enforces - see
        `core.permissions.has_permission`.
        """
        flags = {
            "panel": user.panel,
            # True until a system-generated password has been replaced.
            "must_change_password": bool(user.must_change_password),
            "can_manage_users": user.role in (Role.SUPER_ADMIN, Role.ADMIN, Role.HR),
            "can_manage_organization": user.role in (Role.SUPER_ADMIN, Role.ADMIN),
            "can_view_all_attendance": user.role in Role.ADMIN_PANEL,
            "can_approve_attendance": user.role in (Role.SUPER_ADMIN, Role.ADMIN, Role.HR, Role.MANAGER),
        }
        for permission in Permission.ALL:
            flags[permission] = has_permission(user, permission)
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
        self.require_admin()
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
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
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
        self.emit_to_admins(RealtimeEvent.USER_CREATED, {"user": user.to_dict()})
        return self.created(
            payload, "Employee created. Login ID: {}.".format(user.login_id)
        )

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
        self.emit_to_admins(RealtimeEvent.USER_UPDATED, {"user": user.to_dict()})
        return self.ok(user.to_dict(), "Employee updated.")

    def destroy(self, user_id):
        """Soft delete - the document stays for attendance history."""
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN)
        if self.is_self(user_id):
            raise ValidationError("You cannot delete your own account.")
        user = services.get_user_in_org(self.user.organization, user_id)
        user.soft_delete()
        services.logout(user=user, all_sessions=True)

        self.audit(AuditAction.USER_DELETED, resource_type="user", resource_id=str(user.id))
        self.emit_to_admins(RealtimeEvent.USER_STATUS_CHANGED,
                            {"user_id": str(user.id), "status": "deleted"})
        return self.deleted("Employee removed.")

    def reset_password(self, user_id):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        user = services.get_user_in_org(self.user.organization, user_id)
        temporary_password = services.reset_password(user, self.field("new_password"))

        self.audit(AuditAction.ADMIN_PASSWORD_RESET, resource_type="user", resource_id=str(user.id))
        self.emit_to_user(user.id, RealtimeEvent.NOTIFICATION,
                          {"title": "Password reset", "body": "An admin reset your password."})
        return self.ok({"temporary_password": temporary_password}, "Password reset.")

    def stats(self):
        """Headline counters for the admin dashboard."""
        self.require_admin()
        queryset = User.objects.filter(organization=self.user.organization, is_deleted=False)
        by_role = {role: queryset.filter(role=role).count() for role in Role.ALL}
        return self.ok(
            {
                "total": queryset.count(),
                "active": queryset.filter(status="active").count(),
                "suspended": queryset.filter(status="suspended").count(),
                "by_role": by_role,
            }
        )


class RoleController(BaseController):
    """Configurable RBAC: /api/v1/admin/roles/*

    A role's permission set is not hardcoded - every role but SUPER_ADMIN
    (always full access) can have its grants viewed and edited here, scoped
    to the caller's organization.  This is what makes RBAC "configurable"
    rather than another fixed Admin/Employee table.
    """

    #: Assignable/editable roles.  SUPER_ADMIN is excluded: its permission
    #: set is always "everything" and is never stored or editable.
    _EDITABLE_ROLES = tuple(r for r in Role.ALL if r != Role.SUPER_ADMIN)

    def list_roles(self):
        self.require_permission(Permission.ROLE_MANAGE)
        return self.ok(
            [
                {
                    "role": role,
                    "permissions": sorted(effective_permissions(self.user.organization, role)),
                    "default_permissions": sorted(default_permissions_for(role)),
                }
                for role in self._EDITABLE_ROLES
            ]
        )

    def retrieve(self, role):
        self.require_permission(Permission.ROLE_MANAGE)
        role = self._validated_role(role)
        return self.ok(
            {
                "role": role,
                "permissions": sorted(effective_permissions(self.user.organization, role)),
                "default_permissions": sorted(default_permissions_for(role)),
            }
        )

    def update(self, role):
        self.require_permission(Permission.ROLE_MANAGE)
        self.require_step_up()
        role = self._validated_role(role)
        self.require("permissions")
        requested = self.data.get("permissions")
        if not isinstance(requested, list):
            raise ValidationError(
                "permissions must be a list.", details={"permissions": "Must be a list of permission strings."}
            )
        unknown = sorted(set(requested) - set(Permission.ALL))
        if unknown:
            raise ValidationError(
                "Unknown permission(s): {}.".format(", ".join(unknown)),
                details={"permissions": "Contains unrecognised permission strings."},
            )

        RolePermission.objects.filter(organization=self.user.organization, role=role).delete()
        RolePermission(
            organization=self.user.organization, role=role, permissions=sorted(set(requested)),
        ).save()

        self.log("Role %s permissions updated by %s", role, self.user.email)
        self.audit(
            AuditAction.PERMISSION_CHANGED, resource_type="role", resource_id=role,
            metadata={"permissions": sorted(set(requested))},
        )
        return self.ok(
            {"role": role, "permissions": sorted(set(requested))}, "Role permissions updated."
        )

    def _validated_role(self, role):
        if role not in self._EDITABLE_ROLES:
            raise ValidationError(
                "Unknown or non-editable role.", details={"role": "Not a configurable role."}
            )
        return role


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
        self.require_permission(Permission.AUDIT_VIEW)
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
