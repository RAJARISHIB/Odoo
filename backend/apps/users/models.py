"""User domain - mongoengine documents mapped to Mongo collections.

Collections
    users           : employees and admins (one login per document)
    refresh_tokens  : issued refresh tokens, so sessions can be revoked
"""
from datetime import datetime, timezone

from mongoengine import (
    BooleanField,
    DateTimeField,
    DictField,
    EmailField,
    IntField,
    ListField,
    ReferenceField,
    StringField,
)

from core.base_model import BaseDocument
from core.constants import Panel, Role, UserStatus
from core.security import hash_password, verify_password



class Role(BaseDocument):
    """A dynamically configurable role with specific permissions."""
    organization = ReferenceField("Organization", null=True)
    name = StringField(required=True, max_length=80)
    slug = StringField(required=True, max_length=80)
    description = StringField(max_length=255, default="")
    permissions = ListField(StringField(), default=list)
    is_system = BooleanField(default=False)

    meta = {
        "collection": "roles",
        "indexes": [
            "organization",
            {"fields": ("organization", "slug"), "unique": True, "sparse": True},
        ],
        "ordering": ["name"],
    }

    def __repr__(self):
        return f"<Role {self.name} ({self.slug})>"

class User(BaseDocument):
    """A person who can sign in.  `role` decides which panel the UI opens."""

    organization = ReferenceField("Organization", required=True)
    department = ReferenceField("Department", null=True)

    #: System-generated sign-in identifier, e.g. OIJODO20220001.  Never chosen
    #: by a person and never editable - see `core.identifiers`.
    login_id = StringField(required=True, unique=True, max_length=32)
    email = EmailField(required=True, unique=True)
    #: Never serialised - see HIDDEN_FIELDS.
    password_hash = StringField(required=True)

    first_name = StringField(required=True, max_length=80)
    last_name = StringField(max_length=80, default="")
    phone = StringField(max_length=25)
    avatar_url = StringField(max_length=500)

    employee_id = StringField(max_length=40)
    designation = StringField(max_length=120)
    date_of_joining = DateTimeField(null=True)
    date_of_birth = DateTimeField(null=True)
    reporting_to = ReferenceField("self", null=True)

    role = ReferenceField("Role", required=True)
    status = StringField(required=True, choices=UserStatus.ALL, default=UserStatus.ACTIVE)

    last_login_at = DateTimeField(null=True)
    #: Bumped on every failed login, cleared on success (hook for lockouts).
    failed_login_attempts = IntField(default=0)
    must_change_password = BooleanField(default=False)
    preferences = DictField(default=dict)

    HIDDEN_FIELDS = ("password_hash", "failed_login_attempts")

    meta = {
        "collection": "users",
        "indexes": [
            "login_id",
            "email",
            "organization",
            "role",
            "status",
            {"fields": ("organization", "employee_id"), "sparse": True},
        ],
        "ordering": ["first_name"],
    }

    # -- derived -----------------------------------------------------------
    @property
    def full_name(self) -> str:
        return "{} {}".format(self.first_name, self.last_name or "").strip()

    @property
    def panel(self) -> str:
        """Which Angular panel this user lands on after login."""
        if not self.role or isinstance(self.role, str):
            return Panel.USER
        return Panel.ADMIN if getattr(self.role, "slug", "") in Role.ADMIN_PANEL else Panel.USER

    @property
    def is_admin(self) -> bool:
        return getattr(self.role, "slug", "") in Role.ADMIN_PANEL if self.role and not isinstance(self.role, str) else False


    def has_permission(self, permission_key: str) -> bool:
        if not self.role or isinstance(self.role, str):
            return False
        if "*" in self.role.permissions or getattr(self.role, "slug", "") in (Role.SUPER_ADMIN, Role.ADMIN):
            return True
        return permission_key in self.role.permissions

    # -- passwords ---------------------------------------------------------
    def set_password(self, raw_password: str):
        self.password_hash = hash_password(raw_password)
        return self

    def check_password(self, raw_password: str) -> bool:
        return verify_password(raw_password, self.password_hash)

    def mark_logged_in(self):
        self.last_login_at = datetime.now(timezone.utc)
        self.failed_login_attempts = 0
        self.save()
        return self

    # -- serialisation -----------------------------------------------------
    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)
        data["full_name"] = self.full_name
        data["panel"] = self.panel
        data["is_admin"] = self.is_admin

        if self.date_of_birth:
            data["date_of_birth"] = self.date_of_birth.strftime("%Y-%m-%d")
        else:
            data["date_of_birth"] = None

        if self.role and not isinstance(self.role, str):
            try:
                data["role"] = {"id": str(self.role.id), "name": getattr(self.role, "name", ""), "slug": getattr(self.role, "slug", "")}
                data["permissions"] = getattr(self.role, "permissions", [])
            except Exception:
                pass
        return data

    def __repr__(self):
        return "<User {} ({})>".format(self.email, self.role)


class RefreshToken(BaseDocument):
    """One issued refresh token = one active session.

    Stored by `jti` only (never the raw token), so logout and "revoke all
    sessions" can invalidate a session server-side.
    """

    user = ReferenceField(User, required=True)
    jti = StringField(required=True, unique=True, max_length=64)
    expires_at = DateTimeField(required=True)
    revoked = BooleanField(default=False)
    revoked_at = DateTimeField(null=True)

    ip_address = StringField(max_length=64)
    user_agent = StringField(max_length=255)

    meta = {
        "collection": "refresh_tokens",
        "indexes": ["jti", "user", "revoked", {"fields": ["expires_at"], "expireAfterSeconds": 0}],
        "ordering": ["-created_at"],
    }

    @property
    def is_active(self) -> bool:
        if self.revoked:
            return False
        expires_at = self.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > datetime.now(timezone.utc)

    def revoke(self):
        self.revoked = True
        self.revoked_at = datetime.now(timezone.utc)
        self.save()
        return self

    def __repr__(self):
        return "<RefreshToken {}>".format(self.jti)
