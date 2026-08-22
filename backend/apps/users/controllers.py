import logging

logger = logging.getLogger(__name__)


"""User + auth controllers.

Each public method maps 1:1 to a route in `apps/users/urls.py`.  They read the
request through `BaseController`, delegate the work to `services.py`, and return
the standard envelope.
"""
from apps.users import services
from apps.users.models import User
from core.base_controller import BaseController
from core.constants import RealtimeEvent, Role, Permissions
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
            "can_manage_users": user.has_permission(Permissions.USERS_EDIT) or user.has_permission(Permissions.USERS_CREATE),
            "can_manage_organization": user.has_permission(Permissions.ORG_MANAGE),
            "can_view_all_attendance": user.has_permission(Permissions.ATTENDANCE_VIEW_ALL),
            "can_approve_attendance": user.has_permission(Permissions.ATTENDANCE_MANAGE) or user.has_permission(Permissions.ATTENDANCE_VIEW_TEAM),
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

        self.notify_relevant(RealtimeEvent.USER_CREATED, {"user": user.to_dict()}, subject_user=user)
        return self.created(
            payload, "Employee created. Login ID: {}.".format(user.login_id)
        )

    def invite(self):
        """Send an email invitation to a new employee."""
        self.require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.HR)
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
        user = services.update_user(user, self.data, editor=self.user)

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

        self.emit_to_user(user.id, RealtimeEvent.NOTIFICATION,
                          {"title": "Password reset", "body": "An admin reset your password."})
        return self.ok({"temporary_password": temporary_password}, "Password reset.")

    def stats(self):
        """Headline counters for the admin dashboard."""
        self.require_permissions(Permissions.USERS_VIEW)
        queryset = User.objects.filter(organization=self.user.organization, is_deleted=False)
        roles = getattr(self.user, "organization", None) and Role.objects.filter(organization=self.user.organization).all() or []; by_role = {r.name: queryset.filter(role=r).count() for r in roles}
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


class RoleController(BaseController):
    """CRUD for custom roles in an organization."""

    def catalog(self):
        """Return the hardcoded permission definitions grouped by module."""
        return self.success(data=Permissions.CATALOG)

    def list(self):
        roles = services.list_roles(self.organization)
        return self.success(data=[r.to_dict() for r in roles])

    def retrieve(self, role_id: str):
        role = services.get_role(self.organization, role_id)
        if not role:
            return self.not_found("Role not found.")
        
        # Optionally fetch users assigned to this role
        users_count = services.get_role_users_count(role)
        data = role.to_dict()
        data["users_count"] = users_count
        return self.success(data=data)

    def create(self):
        self.require_fields("name", "permissions")
        role = services.create_role(
            organization=self.organization,
            name=self.field("name"),
            description=self.field("description", ""),
            permissions=self.field("permissions"),
        )
        # Assuming RealtimeService publishes event
        return self.success(data=role.to_dict(), message="Role created successfully.", status_code=201)

    def update(self, role_id: str):
        role = services.update_role(
            organization=self.organization,
            role_id=role_id,
            name=self.field("name"),
            description=self.field("description"),
            permissions=self.field("permissions"),
        )
        return self.success(data=role.to_dict(), message="Role updated successfully.")

    def destroy(self, role_id: str):
        services.delete_role(self.organization, role_id)
        return self.success(message="Role deleted.")

    def assign(self, role_id: str):
        self.require_fields("user_ids")
        services.assign_role(self.organization, role_id, self.field("user_ids"))
        return self.success(message="Role assigned successfully.")
