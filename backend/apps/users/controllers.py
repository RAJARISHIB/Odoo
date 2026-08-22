"""User + auth controllers.

Each public method maps 1:1 to a route in `apps/users/urls.py`.  They read the
request through `BaseController`, delegate the work to `services.py`, and return
the standard envelope.
"""
from apps.users import services
from apps.users.models import User
from core.base_controller import BaseController
from core.constants import RealtimeEvent, Role
from core.exceptions import ValidationError
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

        result = services.login(identifier, self.field("password"), **self._session_meta())
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
        items = [
            {
                "id": str(session.id),
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "expires_at": session.expires_at.isoformat() if session.expires_at else None,
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
            }
            for session in services.list_sessions(user)
        ]
        return self.ok(items, meta={"total": len(items)})

    def change_password(self):
        user = self.require_user()
        self.require("current_password", "new_password")
        services.change_password(user, self.field("current_password"), self.field("new_password"))
        return self.ok(None, "Password updated. Please sign in again.")

    # -- helpers -----------------------------------------------------------
    def _session_meta(self) -> dict:
        return self.client_meta

    @staticmethod
    def _permissions(user) -> dict:
        """Coarse capability flags the Angular guards and menus read."""
        return {
            "panel": user.panel,
            # True until a system-generated password has been replaced.
            "must_change_password": bool(user.must_change_password),
            "can_manage_users": user.role in (Role.SUPER_ADMIN, Role.ADMIN, Role.HR),
            "can_manage_organization": user.role in (Role.SUPER_ADMIN, Role.ADMIN),
            "can_view_all_attendance": user.role in Role.ADMIN_PANEL,
            "can_approve_attendance": user.role in (Role.SUPER_ADMIN, Role.ADMIN, Role.HR, Role.MANAGER),
        }

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
        user = services.update_user(user, self.data, editor=self.user)

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

        self.emit_to_admins(RealtimeEvent.USER_STATUS_CHANGED,
                            {"user_id": str(user.id), "status": "deleted"})
        return self.deleted("Employee removed.")

    def reset_password(self, user_id):
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
        user = services.get_user_in_org(self.user.organization, user_id)
        temporary_password = services.reset_password(user, self.field("new_password"))

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
