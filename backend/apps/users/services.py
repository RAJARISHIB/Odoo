"""User + authentication business logic.

Controllers handle the HTTP conversation; everything that touches Mongo or makes
a domain decision lives here, so the same logic can be reused from a management
command, a seed script or a background job.
"""
import logging
from datetime import datetime, timezone

from django.conf import settings

from apps.organization.models import Organization
from apps.users.models import RefreshToken, User
from core.constants import Role, UserStatus
from core.exceptions import AuthenticationError, Conflict, NotFound, ValidationError
from core.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from core.utils import random_password, slugify
from core.validators import (
    validate_choice,
    validate_email,
    validate_password,
    validate_phone,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token issuing
# ---------------------------------------------------------------------------
def issue_token_pair(user: User, *, ip_address: str = "", user_agent: str = "") -> dict:
    """Mint an access + refresh pair and record the refresh session."""
    access_token, _, access_expires = create_access_token(user)
    refresh_token, refresh_jti, refresh_expires = create_refresh_token(user)

    RefreshToken(
        user=user,
        jti=refresh_jti,
        expires_at=refresh_expires,
        ip_address=ip_address,
        user_agent=user_agent,
    ).save()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_at": access_expires.isoformat(),
        "expires_in": int(settings.JWT["ACCESS_TTL"].total_seconds()),
    }


def authenticate(email: str, password: str) -> User:
    """Verify credentials.  The failure message is deliberately identical for
    unknown-email and wrong-password so the endpoint cannot enumerate users."""
    email = validate_email(email)
    user = User.objects.filter(email=email, is_deleted=False).first()

    if not user or not user.check_password(password):
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            user.save()
        raise AuthenticationError("Invalid email or password.", code="invalid_credentials")

    if user.status != UserStatus.ACTIVE:
        raise AuthenticationError(
            "Your account is {}. Contact your administrator.".format(user.status),
            code="account_inactive",
        )
    return user


def login(email: str, password: str, *, ip_address: str = "", user_agent: str = "") -> dict:
    user = authenticate(email, password)
    user.mark_logged_in()
    tokens = issue_token_pair(user, ip_address=ip_address, user_agent=user_agent)
    return {"user": user.to_dict(), "tokens": tokens}


def refresh_session(refresh_token: str, *, ip_address: str = "", user_agent: str = "") -> dict:
    """Rotate a refresh token: the presented one is revoked and a new pair issued."""
    payload = decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)

    stored = RefreshToken.objects.filter(jti=payload["jti"]).first()
    if not stored or not stored.is_active:
        raise AuthenticationError("Session expired or revoked. Please sign in again.",
                                  code="refresh_revoked")

    user = User.objects.filter(id=payload["sub"], is_deleted=False).first()
    if not user or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("Account is no longer active.", code="account_inactive")

    stored.revoke()  # single-use rotation
    tokens = issue_token_pair(user, ip_address=ip_address, user_agent=user_agent)
    return {"user": user.to_dict(), "tokens": tokens}


def logout(refresh_token: str = None, user: User = None, *, all_sessions: bool = False) -> int:
    """Revoke one session, or every session this user has open."""
    if all_sessions and user:
        sessions = RefreshToken.objects.filter(user=user, revoked=False)
        count = sessions.count()
        sessions.update(revoked=True, revoked_at=datetime.now(timezone.utc))
        return count

    if not refresh_token:
        return 0
    try:
        payload = decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    except AuthenticationError:
        return 0  # already unusable - logging out is still a success
    stored = RefreshToken.objects.filter(jti=payload["jti"], revoked=False).first()
    if stored:
        stored.revoke()
        return 1
    return 0


def list_sessions(user: User):
    return RefreshToken.objects.filter(user=user, revoked=False).order_by("-created_at")


# ---------------------------------------------------------------------------
# Registration / provisioning
# ---------------------------------------------------------------------------
def register_organization(data: dict, *, ip_address: str = "", user_agent: str = "") -> dict:
    """Bootstrap signup: create an organization plus its first super admin.

    This is the only way an account comes into existence without an invite -
    everyone else is created by an admin through `create_user`.
    """
    email = validate_email(data.get("email"))
    validate_password(data.get("password"))

    if User.objects.filter(email=email).first():
        raise Conflict("An account with this email already exists.", code="email_taken")

    org_name = (data.get("organization_name") or "").strip()
    if not org_name:
        raise ValidationError(
            "Organization name is required.",
            details={"organization_name": "This field is required."},
        )

    slug = _unique_org_slug(org_name)
    organization = Organization(
        name=org_name,
        slug=slug,
        email=email,
        phone=validate_phone(data.get("phone", "")),
    ).save()

    user = User(
        organization=organization,
        email=email,
        first_name=(data.get("first_name") or "").strip() or org_name,
        last_name=(data.get("last_name") or "").strip(),
        phone=data.get("phone", ""),
        role=Role.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
    )
    user.set_password(data["password"])
    user.save()

    logger.info("Registered organization %s with owner %s", organization.slug, user.email)
    tokens = issue_token_pair(user, ip_address=ip_address, user_agent=user_agent)
    return {"user": user.to_dict(), "organization": organization.to_dict(), "tokens": tokens}


def _unique_org_slug(name: str) -> str:
    base = slugify(name) or "org"
    slug, suffix = base, 1
    while Organization.objects.filter(slug=slug).first():
        suffix += 1
        slug = "{}-{}".format(base, suffix)
    return slug


def create_user(organization: Organization, data: dict, *, created_by: User = None) -> tuple:
    """Admin-side user provisioning.

    Returns `(user, temporary_password)`; the temporary password is `None` when
    the caller supplied one.
    """
    email = validate_email(data.get("email"))
    if User.objects.filter(email=email).first():
        raise Conflict("An account with this email already exists.", code="email_taken")

    raw_password = data.get("password")
    temporary_password = None
    if raw_password:
        validate_password(raw_password)
    else:
        raw_password = temporary_password = random_password()

    role = validate_choice(data.get("role", Role.EMPLOYEE), Role.ALL, "role")

    user = User(
        organization=organization,
        email=email,
        first_name=(data.get("first_name") or "").strip(),
        last_name=(data.get("last_name") or "").strip(),
        phone=validate_phone(data.get("phone", "")),
        employee_id=data.get("employee_id"),
        designation=data.get("designation"),
        role=role,
        status=data.get("status", UserStatus.ACTIVE),
        must_change_password=temporary_password is not None,
    )
    if data.get("department_id"):
        user.department = _department_or_404(organization, data["department_id"])
    if data.get("reporting_to_id"):
        user.reporting_to = get_user_in_org(organization, data["reporting_to_id"])

    user.set_password(raw_password)
    user.save()

    logger.info(
        "User %s created in org %s by %s",
        user.email, organization.slug, created_by.email if created_by else "system",
    )
    return user, temporary_password


def update_user(user: User, data: dict, *, editor: User = None) -> User:
    """Patch a user.  Only whitelisted fields are writable over the API."""
    editable = (
        "first_name", "last_name", "phone", "designation",
        "employee_id", "avatar_url", "preferences",
    )
    for field in editable:
        if field in data:
            setattr(user, field, data[field])

    # Role and status are privileged, and nobody may demote themselves.
    if "role" in data and editor and editor.role in (Role.SUPER_ADMIN, Role.ADMIN):
        if str(editor.id) == str(user.id) and data["role"] != user.role:
            raise ValidationError("You cannot change your own role.", details={"role": "Not allowed."})
        user.role = validate_choice(data["role"], Role.ALL, "role")

    if "status" in data and editor and editor.is_admin:
        user.status = validate_choice(data["status"], UserStatus.ALL, "status")

    if "department_id" in data:
        user.department = (
            _department_or_404(user.organization, data["department_id"])
            if data["department_id"] else None
        )

    user.save()
    return user


def change_password(user: User, current_password: str, new_password: str) -> User:
    if not user.check_password(current_password):
        raise AuthenticationError("Current password is incorrect.", code="invalid_password")
    validate_password(new_password, "new_password")
    user.set_password(new_password)
    user.must_change_password = False
    user.save()
    logout(user=user, all_sessions=True)  # force every other device to re-auth
    return user


def reset_password(user: User, new_password: str = None) -> str:
    """Admin-driven reset.  Returns the password to hand to the employee."""
    raw_password = new_password or random_password()
    validate_password(raw_password, "new_password")
    user.set_password(raw_password)
    user.must_change_password = True
    user.save()
    logout(user=user, all_sessions=True)
    return raw_password


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def get_user_in_org(organization: Organization, user_id: str) -> User:
    user = User.objects.filter(id=user_id, organization=organization, is_deleted=False).first()
    if not user:
        raise NotFound("User not found in this organization.")
    return user


def search_users(organization: Organization, *, search: str = None, role: str = None,
                 status: str = None, department_id: str = None):
    """Filtered, tenant-scoped user queryset for the admin panel's employee list."""
    queryset = User.objects.filter(organization=organization, is_deleted=False)

    if search:
        queryset = queryset.filter(
            __raw__={
                "$or": [
                    {"first_name": {"$regex": search, "$options": "i"}},
                    {"last_name": {"$regex": search, "$options": "i"}},
                    {"email": {"$regex": search, "$options": "i"}},
                    {"employee_id": {"$regex": search, "$options": "i"}},
                ]
            }
        )
    if role:
        queryset = queryset.filter(role=validate_choice(role, Role.ALL, "role"))
    if status:
        queryset = queryset.filter(status=validate_choice(status, UserStatus.ALL, "status"))
    if department_id:
        queryset = queryset.filter(department=department_id)

    return queryset.order_by("first_name")


def _department_or_404(organization: Organization, department_id: str):
    from apps.organization.models import Department

    department = Department.objects.filter(
        id=department_id, organization=organization, is_deleted=False
    ).first()
    if not department:
        raise NotFound("Department not found.")
    return department
