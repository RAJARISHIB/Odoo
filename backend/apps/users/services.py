"""User + authentication business logic.

Controllers handle the HTTP conversation; everything that touches Mongo or makes
a domain decision lives here, so the same logic can be reused from a management
command, a seed script or a background job.
"""
import logging
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone

from django.conf import settings
from django.core.mail import send_mail

from apps.organization.models import Department, Organization
from apps.users.models import EmailVerificationToken, PasswordResetToken, RefreshToken, Role, User
from core.audit import record as audit_record
from core.constants import AuditAction, Permissions, RealtimeEvent, Role as RoleEnum, UserStatus
from core.identifiers import generate_login_id, organization_code, split_full_name
from core.exceptions import AuthenticationError, Conflict, NotFound, PermissionDenied, ValidationError
from core.mailer import send as send_email
from core.security import (
    TOKEN_TYPE_MFA_PENDING,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_mfa_pending_token,
    create_refresh_token,
    decode_token,
    generate_raw_token,
    generate_recovery_codes,
    generate_totp_secret,
    hash_password,
    hash_token,
    totp_uri,
    verify_password,
    verify_totp,
)
from core.permissions import assert_can_assign_role
from core.storage import save_image
from core.utils import random_password, slugify
from core.validators import (
    parse_date,
    parse_datetime,
    validate_choice,
    validate_email,
    validate_password,
    validate_phone,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token issuing
# ---------------------------------------------------------------------------
def issue_token_pair(user: User, *, ip_address: str = "", user_agent: str = "",
                     reauth_at: datetime = None) -> dict:
    """Mint an access + refresh pair and record the refresh session.

    `reauth_at` is when the caller last fully proved their identity (password
    + MFA if enabled). A fresh login/MFA-verify leaves it unset (defaults to
    now); rotating a refresh token passes the *original* session's value
    through unchanged - see `refresh_session`.
    """
    reauth_at = reauth_at or datetime.now(timezone.utc)
    refresh_token, refresh_jti, refresh_expires = create_refresh_token(user)
    access_token, _, access_expires = create_access_token(
        user, reauth_at=reauth_at, session_jti=refresh_jti
    )

    RefreshToken(
        user=user,
        jti=refresh_jti,
        expires_at=refresh_expires,
        ip_address=ip_address,
        user_agent=user_agent,
        reauth_at=reauth_at,
    ).save()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_at": access_expires.isoformat(),
        "expires_in": int(settings.JWT["ACCESS_TTL"].total_seconds()),
    }


def find_by_identifier(identifier: str) -> User:
    """Look a user up by login ID or email address.

    The sign-in form has one field for both, so anything containing "@" is
    treated as an email and everything else as a login ID.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    if "@" in identifier:
        return User.objects.filter(email=identifier.lower(), is_deleted=False).first()
    return User.objects.filter(login_id=identifier.upper(), is_deleted=False).first()


#: Temporary lockout, not a permanent ban - see `core.ratelimit` for the
#: pre-auth (IP-based) throttle layered on top of this per-account one.
LOGIN_MAX_FAILED_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15


def authenticate(identifier: str, password: str) -> User:
    """Verify credentials.  The failure message is deliberately identical for
    an unknown account and a wrong password so the endpoint cannot enumerate
    users."""
    user = find_by_identifier(identifier)

    if user and user.locked_until:
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > datetime.now(timezone.utc):
            raise AuthenticationError(
                "Too many failed attempts. Try again in a few minutes.",
                code="account_locked",
            )

    if not user or not user.check_password(password):
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= LOGIN_MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
            user.save()
        raise AuthenticationError(
            "Invalid login ID / email or password.", code="invalid_credentials"
        )

    if user.status != UserStatus.ACTIVE:
        raise AuthenticationError(
            "Your account is {}. Contact your administrator.".format(user.status),
            code="account_inactive",
        )
    return user


def login(identifier: str, password: str, *, ip_address: str = "", user_agent: str = "") -> dict:
    """Password step.  For an MFA-enabled account this deliberately does not
    return usable tokens - only a narrow `mfa_pending_token` good for
    `verify_mfa_login` - so a stolen/guessed password alone never yields a
    session."""
    try:
        user = authenticate(identifier, password)
    except AuthenticationError as exc:
        # A cheap re-lookup only for audit context (organization, resource_id)
        # - authenticate() already did the real credential check above and
        # this never changes the response, so it cannot be used to
        # enumerate accounts.
        matched_user = find_by_identifier(identifier)
        audit_record(
            action=(
                AuditAction.ACCOUNT_LOCKED if exc.code == "account_locked" else AuditAction.LOGIN_FAILED
            ),
            actor=matched_user, organization=matched_user.organization if matched_user else None,
            resource_type="user", resource_id=str(matched_user.id) if matched_user else identifier,
            result="failure", ip_address=ip_address, user_agent=user_agent,
            metadata={"identifier": identifier, "reason": exc.code},
        )
        raise

    if user.mfa_enabled:
        pending_token, _, expires_at = create_mfa_pending_token(user)
        audit_record(
            action=AuditAction.MFA_CHALLENGE_ISSUED, actor=user,
            resource_type="user", resource_id=str(user.id),
            ip_address=ip_address, user_agent=user_agent,
        )
        return {
            "mfa_required": True,
            "mfa_pending_token": pending_token,
            "expires_at": expires_at.isoformat(),
        }

    user.mark_logged_in()
    tokens = issue_token_pair(user, ip_address=ip_address, user_agent=user_agent)
    audit_record(
        action=AuditAction.LOGIN_SUCCESS, actor=user,
        resource_type="user", resource_id=str(user.id),
        ip_address=ip_address, user_agent=user_agent,
    )
    return {"mfa_required": False, "user": user.to_dict(), "tokens": tokens}


def verify_mfa_login(mfa_pending_token: str, code: str, *,
                     ip_address: str = "", user_agent: str = "") -> dict:
    """Second step for an MFA-enabled account: exchange the pending token +
    a TOTP/recovery code for a real session."""
    try:
        payload = decode_token(mfa_pending_token, expected_type=TOKEN_TYPE_MFA_PENDING)
    except AuthenticationError:
        raise AuthenticationError(
            "Your sign-in session expired. Please sign in again.", code="mfa_session_expired"
        )

    user = User.objects.filter(id=payload["sub"], is_deleted=False).first()
    if not user or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("Account is no longer active.", code="account_inactive")
    if not user.mfa_enabled:
        raise AuthenticationError("MFA is not enabled for this account.", code="mfa_not_enabled")

    if not _consume_mfa_code(user, code):
        audit_record(
            action=AuditAction.MFA_FAILED, actor=user,
            resource_type="user", resource_id=str(user.id), result="failure",
            ip_address=ip_address, user_agent=user_agent,
        )
        raise AuthenticationError("Invalid authentication code.", code="invalid_mfa_code")

    user.mark_logged_in()
    reauth_at = datetime.now(timezone.utc)
    tokens = issue_token_pair(user, ip_address=ip_address, user_agent=user_agent, reauth_at=reauth_at)
    audit_record(
        action=AuditAction.LOGIN_SUCCESS, actor=user,
        resource_type="user", resource_id=str(user.id),
        ip_address=ip_address, user_agent=user_agent, metadata={"via": "mfa"},
    )
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
    # Carried forward, not reset to "now": a refreshed session is not a
    # freshly re-authenticated one, so `require_step_up` should judge it by
    # when the credentials were actually last proven.
    tokens = issue_token_pair(
        user, ip_address=ip_address, user_agent=user_agent, reauth_at=stored.reauth_at
    )
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


def revoke_session(user: User, session_id: str) -> bool:
    """Revoke one of `user`'s own sessions by id - e.g. "sign out this
    device" from a list, as opposed to the current session's own logout or a
    blanket `all_sessions=True`."""
    session = RefreshToken.objects.filter(id=session_id, user=user, revoked=False).first()
    if not session:
        return False
    session.revoke()
    return True


# ---------------------------------------------------------------------------
# MFA (TOTP) - see `core.security` for the RFC 6238 primitives.
# ---------------------------------------------------------------------------
def _consume_mfa_code(user: User, code: str) -> bool:
    """Accepts either a current TOTP code or an unused recovery code (which
    is then marked used - each is single-use)."""
    code = (code or "").strip()
    if not code:
        return False
    if user.mfa_secret and verify_totp(user.mfa_secret, code):
        return True

    normalized = code.upper()
    for entry in user.mfa_recovery_codes:
        if entry.get("used_at"):
            continue
        if verify_password(normalized, entry.get("hash", "")):
            entry["used_at"] = datetime.now(timezone.utc).isoformat()
            user.save()
            return True
    return False


def mfa_enroll_start(user: User) -> dict:
    """Generates a new TOTP secret and stores it *unconfirmed*
    (`mfa_enabled` stays False until `mfa_enroll_confirm` proves the user's
    authenticator app actually has it)."""
    secret = generate_totp_secret()
    user.mfa_secret = secret
    user.mfa_enabled = False
    user.save()
    return {"secret": secret, "otpauth_uri": totp_uri(secret, account_name=user.email)}


def mfa_enroll_confirm(user: User, code: str) -> list:
    """Proves enrollment with one real code, turns MFA on, and returns the
    one-time recovery codes (only ever shown here - only their hashes are
    kept)."""
    if not user.mfa_secret:
        raise ValidationError(
            "Start MFA enrollment first.", details={"code": "No enrollment in progress."}
        )
    if not verify_totp(user.mfa_secret, code):
        raise ValidationError("Incorrect code.", details={"code": "Invalid or expired code."})

    raw_codes = generate_recovery_codes()
    user.mfa_recovery_codes = [{"hash": hash_password(c), "used_at": None} for c in raw_codes]
    user.mfa_enabled = True
    user.save()
    return raw_codes


def mfa_disable(user: User, current_password: str, code: str) -> None:
    """Disabling MFA weakens the account, so it demands the same proof MFA
    itself would: the password, plus one more TOTP/recovery code. Every
    other session is then forced to re-authenticate."""
    if not user.check_password(current_password):
        raise AuthenticationError("Current password is incorrect.", code="invalid_password")
    if not _consume_mfa_code(user, code):
        raise ValidationError(
            "Invalid authentication code.", details={"code": "Incorrect code or recovery code."}
        )

    user.mfa_enabled = False
    user.mfa_secret = ""
    user.mfa_recovery_codes = []
    user.save()
    logout(user=user, all_sessions=True)


def mfa_regenerate_recovery_codes(user: User, current_password: str, code: str) -> list:
    if not user.check_password(current_password):
        raise AuthenticationError("Current password is incorrect.", code="invalid_password")
    if not user.mfa_enabled:
        raise ValidationError("MFA is not enabled.", details={"code": "Enable MFA first."})
    if not _consume_mfa_code(user, code):
        raise ValidationError(
            "Invalid authentication code.", details={"code": "Incorrect code or recovery code."}
        )

    raw_codes = generate_recovery_codes()
    user.mfa_recovery_codes = [{"hash": hash_password(c), "used_at": None} for c in raw_codes]
    user.save()
    return raw_codes


# ---------------------------------------------------------------------------
# Registration / provisioning
# ---------------------------------------------------------------------------
def register_organization(data: dict, *, logo=None, ip_address: str = "", user_agent: str = "") -> dict:
    """Bootstrap signup: create an organization plus its first super admin.

    This is the only way an account comes into existence without an invite -
    every other user is created by an HR officer or admin via `create_user`.
    The owner receives a generated login ID just like everybody else.
    """
    email = validate_email(data.get("email"))
    password = data.get("password")
    validate_password(password)

    # The form asks for the password twice; only enforce it when the client
    # actually sent the confirmation.
    confirm = data.get("confirm_password")
    if confirm is not None and confirm != password:
        raise ValidationError(
            "Passwords do not match.",
            details={"confirm_password": "Does not match the password."},
        )

    if User.objects.filter(email=email).first():
        raise Conflict("An account with this email already exists.", code="email_taken")

    org_name = (data.get("organization_name") or "").strip()
    if not org_name:
        raise ValidationError(
            "Organization name is required.",
            details={"organization_name": "This field is required."},
        )

    # The form has a single "Name" field, but a login ID needs both halves.
    first_name, last_name = _resolve_name(data)
    if not first_name:
        raise ValidationError("Your name is required.", details={"name": "This field is required."})

    organization = Organization(
        name=org_name,
        slug=_unique_org_slug(org_name),
        code=_unique_org_code(org_name),
        email=email,
        phone=validate_phone(data.get("phone", "")),
    ).save()

    if logo is not None:
        organization.logo_url = save_image(logo, "logos/{}".format(organization.id))
        organization.save()

    # Provision default roles for the new organization
    roles = {}
    for r_slug, r_name, perms in [
        (RoleEnum.SUPER_ADMIN, "Super Admin", list(Permissions.ALL)),
        (RoleEnum.ADMIN, "Admin", list(Permissions.ALL)),
        (RoleEnum.HR, "HR Manager", [p for p in Permissions.ALL if p.startswith('users.') or p.startswith('leaves.') or p in (Permissions.ATTENDANCE_VIEW_ALL, Permissions.ATTENDANCE_MANAGE, Permissions.ORG_VIEW, Permissions.DEPARTMENTS_MANAGE, Permissions.ROLES_VIEW, Permissions.ROLES_ASSIGN, Permissions.CLAIMS_VIEW_ALL, Permissions.CLAIMS_MANAGE)]),
        (RoleEnum.MANAGER, "Manager", [Permissions.USERS_VIEW, Permissions.ATTENDANCE_PUNCH, Permissions.ATTENDANCE_VIEW_OWN, Permissions.ATTENDANCE_VIEW_TEAM, Permissions.LEAVES_APPLY, Permissions.LEAVES_VIEW_OWN, Permissions.LEAVES_VIEW_TEAM, Permissions.LEAVES_APPROVE, Permissions.ORG_VIEW]),
        (RoleEnum.EMPLOYEE, "Employee", [Permissions.USERS_VIEW, Permissions.ATTENDANCE_PUNCH, Permissions.ATTENDANCE_VIEW_OWN, Permissions.LEAVES_APPLY, Permissions.LEAVES_VIEW_OWN, Permissions.ORG_VIEW])
    ]:
        from apps.users.models import Role
        roles[r_slug] = Role(organization=organization, name=r_name, slug=r_slug, is_system=True, permissions=perms).save()

    joined_at = datetime.now(timezone.utc)
    user = User(
        organization=organization,
        login_id=generate_login_id(organization, first_name, last_name, joined_at),
        email=email,
        first_name=first_name,
        last_name=last_name,
        phone=data.get("phone", ""),
        role=roles[RoleEnum.SUPER_ADMIN],
        status=UserStatus.ACTIVE,
        date_of_joining=joined_at,
        # They just proved control of this address by completing signup with
        # it - unlike an employee invited by someone else, there is nothing
        # further to verify.
        email_verified=True,
    )
    user.set_password(password)
    user.save()

    logger.info(
        "Registered organization %s (%s) with owner %s",
        organization.slug, organization.code, user.login_id,
    )
    tokens = issue_token_pair(user, ip_address=ip_address, user_agent=user_agent)
    return {"user": user.to_dict(), "organization": organization.to_dict(), "tokens": tokens}


def _resolve_name(data: dict) -> tuple:
    """Accept either a single `name` or separate `first_name`/`last_name`."""
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    if not first_name and data.get("name"):
        first_name, last_name = split_full_name(data["name"])
    return first_name, last_name


def _unique_org_code(name: str) -> str:
    """Two-letter organization code, suffixed with a digit only on collision."""
    base = organization_code(name)
    if not Organization.objects.filter(code=base).first():
        return base
    for suffix in range(1, 100):
        candidate = "{}{}".format(base, suffix)
        if not Organization.objects.filter(code=candidate).first():
            return candidate
    raise Conflict("Could not allocate an organization code.", code="code_exhausted")


def _unique_org_slug(name: str) -> str:
    base = slugify(name) or "org"
    slug, suffix = base, 1
    while Organization.objects.filter(slug=slug).first():
        suffix += 1
        slug = "{}-{}".format(base, suffix)
    return slug


def create_user(organization: Organization, data: dict, *, created_by: User = None) -> tuple:
    """Admin-side user provisioning - the only way an employee account is born.

    The employee chooses nothing: the system allocates their login ID and, when
    no password is supplied, a first-time password too.  They sign in with those
    and are then required to set their own password.

    Returns `(user, temporary_password)`; the temporary password is `None` when
    the caller supplied one.
    """
    email = validate_email(data.get("email"))
    if User.objects.filter(email=email).first():
        raise Conflict("An account with this email already exists.", code="email_taken")

    first_name, last_name = _resolve_name(data)
    if not first_name:
        raise ValidationError(
            "The employee's name is required.", details={"first_name": "This field is required."}
        )

    raw_password = data.get("password")
    temporary_password = None
    if raw_password:
        validate_password(raw_password)
    else:
        raw_password = temporary_password = random_password()

    role_slug = validate_choice(data.get("role", RoleEnum.EMPLOYEE), RoleEnum.ALL, "role")
    # A creator may only hand out a role ranked below their own - otherwise an
    # HR account could provision a new SUPER_ADMIN through the ordinary
    # "create employee" form.
    if created_by is not None:
        assert_can_assign_role(getattr(created_by.role, "slug", None), role_slug)
    role_obj = Role.objects.filter(organization=organization, slug=role_slug).first()
    if not role_obj:
        role_obj = Role.objects.filter(organization=organization, slug=RoleEnum.EMPLOYEE).first()
    joined_at = parse_datetime(data.get("date_of_joining")) or datetime.now(timezone.utc)

    user = User(
        organization=organization,
        login_id=generate_login_id(organization, first_name, last_name, joined_at),
        email=email,
        first_name=first_name,
        last_name=last_name,
        phone=validate_phone(data.get("phone", "")),
        employee_id=data.get("employee_id"),
        designation=data.get("designation"),
        date_of_joining=joined_at,
        role=role_obj,
        status=data.get("status", UserStatus.ACTIVE),
        must_change_password=temporary_password is not None,
    )
    if data.get("date_of_birth"):
        dob_d = parse_date(data["date_of_birth"], "date_of_birth")
        if dob_d > date.today():
            raise ValidationError("Date of birth cannot be in the future.", details={"date_of_birth": "Must be today or in the past."})
        user.date_of_birth = datetime.combine(dob_d, time.min, tzinfo=timezone.utc)

    if data.get("department_id"):
        user.department = _department_or_404(organization, data["department_id"])
    if data.get("reporting_to_id"):
        user.reporting_to = get_user_in_org(organization, data["reporting_to_id"])

    user.set_password(raw_password)
    user.save()
    send_verification_email(user)

    logger.info(
        "User %s (%s) created in org %s by %s",
        user.login_id, user.email, organization.slug,
        created_by.login_id if created_by else "system",
    )
    return user, temporary_password


# Ranked strictly, not by ADMIN_PANEL membership: two roles both being
# "admin-panel" roles doesn't mean either may act on the other.
_ROLE_RANK = {
    RoleEnum.SUPER_ADMIN: 4,
    RoleEnum.ADMIN: 3,
    RoleEnum.HR: 2,
    RoleEnum.MANAGER: 1,
    RoleEnum.EMPLOYEE: 0,
}


def _role_rank(user: User) -> int:
    slug = getattr(user.role, "slug", None)
    return _ROLE_RANK.get(slug, 0)


def assert_editable_by(editor: User, target: User) -> None:
    """An admin may act on anyone ranked strictly below them - never a peer,
    never a superior.  Applies uniformly, including two `super_admin`s: one
    cannot silently demote or delete another without their consent.  A no-op
    for self-edits and for internal calls with no editor (e.g. the
    self-service profile update, which never touches role/status anyway)."""
    if editor is None or str(editor.id) == str(target.id):
        return
    if _role_rank(editor) <= _role_rank(target):
        raise PermissionDenied("You cannot modify a user with equal or higher privilege.")


def update_user(user: User, data: dict, *, editor: User = None) -> User:
    """Patch a user.  Only whitelisted fields are writable over the API."""
    assert_editable_by(editor, user)

    editable = (
        "first_name", "last_name", "designation",
        "employee_id", "avatar_url", "preferences",
    )
    for field in editable:
        if field in data:
            setattr(user, field, data[field])

    if "phone" in data:
        user.phone = validate_phone(data["phone"]) if data["phone"] else ""

    if "date_of_birth" in data:
        raw_dob = data["date_of_birth"]
        if raw_dob in (None, ""):
            user.date_of_birth = None
        else:
            dob_d = parse_date(raw_dob, "date_of_birth")
            if dob_d > date.today():
                raise ValidationError("Date of birth cannot be in the future.", details={"date_of_birth": "Must be today or in the past."})
            user.date_of_birth = datetime.combine(dob_d, time.min, tzinfo=timezone.utc)


    # Role and status are privileged, and nobody may demote themselves.
    if "role" in data and editor and (editor.has_permission(Permissions.ROLES_ASSIGN) or editor.has_permission(Permissions.USERS_EDIT)):
        target_role = str(data["role"])
        current_slug = getattr(user.role, "slug", "")
        current_id = str(user.role.id) if user.role else ""
        if str(editor.id) == str(user.id) and target_role not in (current_slug, current_id):
            raise ValidationError("You cannot change your own role.", details={"role": "Not allowed."})
        role_doc = get_role(user.organization, target_role)
        if not role_doc:
            raise ValidationError("Role not found.", details={"role": "Invalid role ID or slug."})
        # A creator may only hand out a role ranked below their own - otherwise
        # an HR account could promote someone straight to SUPER_ADMIN.
        assert_can_assign_role(getattr(editor.role, "slug", None), getattr(role_doc, "slug", None))
        user.role = role_doc

    if "status" in data and editor and editor.has_permission(Permissions.USERS_EDIT):
        if str(editor.id) == str(user.id) and data["status"] == UserStatus.SUSPENDED:
            raise ValidationError("You cannot suspend your own account.", details={"status": "Not allowed."})
        new_status = validate_choice(data["status"], UserStatus.ALL, "status")
        was_active = user.status == UserStatus.ACTIVE
        user.status = new_status
        if was_active and new_status != UserStatus.ACTIVE:
            # Belt-and-braces: both `refresh_session` and the auth middleware
            # already re-check live status on every use, so a disabled
            # account cannot get a new access token or use an old one
            # regardless - this just makes the revocation explicit rather
            # than "happens to fail the next status check".
            logout(user=user, all_sessions=True)

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
# Self-service password reset.  The response is identical whether or not the
# account exists (see `request_password_reset`), and the raw token only ever
# appears in the email body - the API never echoes it back, and only its hash
# is persisted (`core.security.hash_token`), same principle as `RefreshToken`.
# ---------------------------------------------------------------------------
PASSWORD_RESET_TTL = timedelta(hours=1)
EMAIL_VERIFICATION_TTL = timedelta(days=3)


def request_password_reset(identifier: str, *, ip_address: str = "", user_agent: str = "") -> None:
    user = find_by_identifier(identifier)
    if user and user.status == UserStatus.ACTIVE:
        raw_token = generate_raw_token()
        PasswordResetToken(
            user=user,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + PASSWORD_RESET_TTL,
        ).save()
        link = "{}{}?token={}".format(
            settings.FRONTEND_URL.rstrip("/"), "/auth/reset-password", raw_token
        )
        send_email(
            user.email,
            "Reset your Dayflow password",
            "Someone requested a password reset for your account.\n\n"
            "Reset it here (valid for 1 hour, one-time use): {}\n\n"
            "If this wasn't you, no action is needed.".format(link),
        )
        audit_record(
            action=AuditAction.PASSWORD_RESET_REQUESTED, actor=user,
            resource_type="user", resource_id=str(user.id),
            ip_address=ip_address, user_agent=user_agent,
        )
    else:
        # Logged without an `actor` (no matching, active account) so this
        # stays a security signal (repeated probing of unknown identifiers)
        # without letting the log itself become an enumeration oracle - the
        # API response above is identical either way.
        audit_record(
            action=AuditAction.PASSWORD_RESET_REQUESTED, result="unknown_account",
            resource_type="user", resource_id=identifier,
            ip_address=ip_address, user_agent=user_agent,
        )
    # Identical outcome either way - the caller cannot tell whether the
    # account exists from this response.


def reset_password_with_token(raw_token: str, new_password: str, *,
                              ip_address: str = "", user_agent: str = "") -> User:
    token = PasswordResetToken.objects.filter(token_hash=hash_token(raw_token)).first()
    if not token or not token.is_active:
        audit_record(
            action=AuditAction.PASSWORD_RESET_COMPLETED, result="invalid_token",
            ip_address=ip_address, user_agent=user_agent,
        )
        raise ValidationError(
            "This reset link is invalid or has expired.",
            details={"token": "Request a new password reset."},
        )
    user = User.objects.filter(id=token.user.id, is_deleted=False).first()
    if not user or user.status != UserStatus.ACTIVE:
        raise ValidationError("This reset link is no longer valid.", details={"token": "Invalid."})

    validate_password(new_password, "new_password")
    user.set_password(new_password)
    user.must_change_password = False
    user.locked_until = None
    user.failed_login_attempts = 0
    user.save()

    token.used_at = datetime.now(timezone.utc)
    token.save()
    logout(user=user, all_sessions=True)
    audit_record(
        action=AuditAction.PASSWORD_RESET_COMPLETED, actor=user,
        resource_type="user", resource_id=str(user.id),
        ip_address=ip_address, user_agent=user_agent,
    )
    return user


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------
def send_verification_email(user: User) -> None:
    if user.email_verified:
        return
    raw_token = generate_raw_token()
    EmailVerificationToken(
        user=user,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + EMAIL_VERIFICATION_TTL,
    ).save()
    link = "{}{}?token={}".format(
        settings.FRONTEND_URL.rstrip("/"), "/auth/verify-email", raw_token
    )
    send_email(
        user.email,
        "Verify your Dayflow email address",
        "Welcome to Dayflow. Verify your email address here (valid for 3 days): {}".format(link),
    )


def verify_email_token(raw_token: str) -> User:
    token = EmailVerificationToken.objects.filter(token_hash=hash_token(raw_token)).first()
    if not token or not token.is_active:
        raise ValidationError(
            "This verification link is invalid or has expired.",
            details={"token": "Request a new verification email."},
        )
    user = User.objects.filter(id=token.user.id, is_deleted=False).first()
    if not user:
        raise ValidationError("This verification link is no longer valid.", details={"token": "Invalid."})

    user.email_verified = True
    user.save()
    token.used_at = datetime.now(timezone.utc)
    token.save()
    audit_record(
        action=AuditAction.EMAIL_VERIFIED, actor=user, resource_type="user", resource_id=str(user.id),
    )
    return user


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
        # Escaped so a search term can never be read as a regex - an
        # unescaped `.*` or `(a+)+` from the client would otherwise let it
        # widen the match arbitrarily or cause a ReDoS.
        pattern = re.escape(search)
        queryset = queryset.filter(
            __raw__={
                "$or": [
                    {"first_name": {"$regex": pattern, "$options": "i"}},
                    {"last_name": {"$regex": pattern, "$options": "i"}},
                    {"email": {"$regex": pattern, "$options": "i"}},
                    {"employee_id": {"$regex": pattern, "$options": "i"}},
                    {"login_id": {"$regex": pattern, "$options": "i"}},
                ]
            }
        )
    if role:
        role_doc = get_role(organization, role)
        if role_doc:
            queryset = queryset.filter(role=role_doc)
        else:
            return queryset.none()
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


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
from django.utils.text import slugify
from core.realtime import notify_user

def list_roles(organization):
    return Role.objects.filter(organization=organization).all()

def get_role(organization, role_id_or_slug: str):
    if not role_id_or_slug:
        return None
    from bson.objectid import ObjectId
    if ObjectId.is_valid(role_id_or_slug):
        role = Role.objects.filter(id=role_id_or_slug, organization=organization).first()
        if role:
            return role
    return Role.objects.filter(slug=role_id_or_slug, organization=organization).first()

def get_role_users_count(role):
    return User.objects.filter(role=role, is_deleted=False).count()

def create_role(organization, name: str, description: str, permissions: list):
    slug = slugify(name)
    if Role.objects.filter(organization=organization, slug=slug).first():
        raise ValidationError("A role with a similar name already exists.", code="duplicate_role")
        
    invalid_perms = set(permissions) - set(Permissions.ALL)
    if invalid_perms:
        raise ValidationError(f"Invalid permissions: {invalid_perms}")

    role = Role(
        organization=organization,
        name=name,
        slug=slug,
        description=description,
        permissions=list(set(permissions)),
        is_system=False
    ).save()
    return role

def update_role(organization, role_id: str, name: str = None, description: str = None, permissions: list = None):
    role = get_role(organization, role_id)
    if not role:
        raise ValidationError("Role not found.", code="not_found")
    
    if role.is_system and name and name != role.name:
        raise ValidationError("Cannot rename system roles.", code="system_role")

    if name and not role.is_system:
        role.name = name
        role.slug = slugify(name)
    
    if description is not None:
        role.description = description
        
    if permissions is not None:
        invalid_perms = set(permissions) - set(Permissions.ALL)
        if invalid_perms:
            raise ValidationError(f"Invalid permissions: {invalid_perms}")
        role.permissions = list(set(permissions))
        
    role.save()
    
    # Notify users with this role
    # RealtimeService.publish(...)
    
    return role

def delete_role(organization, role_id: str):
    role = get_role(organization, role_id)
    if not role:
        raise ValidationError("Role not found.", code="not_found")
        
    if role.is_system:
        raise ValidationError("Cannot delete system roles.", code="system_role")
        
    if get_role_users_count(role) > 0:
        raise ValidationError("Cannot delete role while users are assigned to it.", code="role_in_use")
        
    role.delete()

def assign_role(organization, role_id: str, user_ids: list):
    role = get_role(organization, role_id)
    if not role:
        raise ValidationError("Role not found.", code="not_found")
        
    users = User.objects.filter(organization=organization, id__in=user_ids, is_deleted=False)
    for user in users:
        user.role = role
        user.save()
        # Revoke tokens if role downgraded? Optional for now.
        
        # Notify
        try:
            notify_user(user.id, RealtimeEvent.USER_UPDATED, user.to_dict())
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Employee Invitations & Onboarding Flow
# ---------------------------------------------------------------------------
def _async_send_mail(subject, message, from_email, recipient_list, html_message):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=True,
        )
    except Exception as exc:
        logger.warning("SMTP email sending failed: %s", exc)


def send_invitation_email(user: User, invite_url: str):
    """Dispatch invitation email to the employee via SMTP asynchronously."""
    import threading

    subject = f"You're invited to join {user.organization.name} on HRMS Portal"
    message = (
        f"Hello {user.first_name},\n\n"
        f"You have been invited to join {user.organization.name} as a {user.designation or 'Team Member'}.\n\n"
        f"Please click the link below to accept your invitation and complete your onboarding:\n"
        f"{invite_url}\n\n"
        f"This link will expire in 7 days.\n\n"
        f"Best regards,\n"
        f"{user.organization.name} HR Team"
    )
    html_message = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; background-color: #ffffff;">
      <h2 style="color: #0f766e; margin-top: 0;">Welcome to {user.organization.name}!</h2>
      <p style="color: #334155; font-size: 15px;">Hello <strong>{user.first_name}</strong>,</p>
      <p style="color: #334155; font-size: 15px;">You have been invited to join <strong>{user.organization.name}</strong> as a <strong>{user.designation or 'Team Member'}</strong>.</p>
      <p style="color: #334155; font-size: 15px;">Please click the button below to accept your invitation and complete your onboarding:</p>
      <div style="text-align: center; margin: 32px 0;">
        <a href="{invite_url}" style="background-color: #0f766e; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block; font-size: 15px;">Accept Invitation & Complete Onboarding</a>
      </div>
      <p style="color: #64748b; font-size: 13px;">Or copy and paste this URL into your browser:<br><a href="{invite_url}" style="color: #0f766e; word-break: break-all;">{invite_url}</a></p>
      <p style="color: #94a3b8; font-size: 12px; margin-top: 32px; border-top: 1px solid #f1f5f9; padding-top: 16px;">This invitation link will expire in 7 days.</p>
    </div>
    """
    threading.Thread(
        target=_async_send_mail,
        args=(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], html_message),
        daemon=True,
    ).start()


def invite_employee(organization, inviter: User, data: dict) -> dict:
    """Invite a new employee via SMTP email with an invitation acceptance link."""
    email = validate_email(data.get("email"), "email")

    existing = User.objects.filter(organization=organization, email=email, is_deleted=False).first()
    if existing:
        if existing.status == UserStatus.INVITED:
            # Re-send invite
            token = uuid.uuid4().hex
            existing.invite_token = token
            existing.invite_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            existing.invited_by = inviter
            existing.invited_at = datetime.now(timezone.utc)
            existing.save()

            invite_url = f"{settings.FRONTEND_URL}/auth/accept-invite?token={token}"
            send_invitation_email(existing, invite_url)
            return {"user": existing.to_dict(), "invite_url": invite_url, "message": f"Invitation re-sent to {email} successfully."}

        raise Conflict("A user with this email address already exists.", details={"email": "Email in use."})

    first_name = str(data.get("first_name", "")).strip()
    if not first_name:
        raise ValidationError("First name is required.", details={"first_name": "This field is required."})

    last_name = str(data.get("last_name", "")).strip()
    designation = str(data.get("designation", "")).strip()
    employee_id = str(data.get("employee_id", "")).strip()

    # Department
    department = None
    if data.get("department_id"):
        department = Department.objects.filter(id=data["department_id"], organization=organization).first()

    # Role lookup
    role_input = data.get("role", RoleEnum.EMPLOYEE)
    role_obj = None
    if isinstance(role_input, str):
        role_obj = Role.objects.filter(organization=organization, slug=role_input).first()
        if not role_obj:
            role_obj = Role.objects.filter(organization=organization, slug=RoleEnum.EMPLOYEE).first()

    if not role_obj:
        raise ValidationError("Invalid role specified.")

    login_id = generate_login_id(organization, first_name, last_name)
    temp_pass = random_password()
    invite_token = uuid.uuid4().hex

    user = User(
        organization=organization,
        department=department,
        login_id=login_id,
        email=email,
        first_name=first_name,
        last_name=last_name,
        designation=designation,
        employee_id=employee_id,
        role=role_obj,
        status=UserStatus.INVITED,
        invite_token=invite_token,
        invite_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by=inviter,
        invited_at=datetime.now(timezone.utc),
    )
    user.set_password(temp_pass)
    user.save()

    invite_url = f"{settings.FRONTEND_URL}/auth/accept-invite?token={invite_token}"
    send_invitation_email(user, invite_url)

    return {
        "user": user.to_dict(),
        "invite_url": invite_url,
        "message": f"Invitation sent to {email} successfully.",
    }


def get_invite_details(token: str) -> dict:
    """Retrieve invitation details by token for public accept-invite screen."""
    if not token:
        raise ValidationError("Invitation token is required.")

    user = User.objects.filter(invite_token=token, is_deleted=False).first()
    if not user:
        raise NotFound("Invitation link is invalid or expired.")

    if user.status != UserStatus.INVITED:
        raise ValidationError("This invitation has already been accepted or is no longer active.")

    if user.invite_token_expires_at and datetime.now(timezone.utc) > user.invite_token_expires_at:
        raise ValidationError("This invitation link has expired. Please request a new invitation.")

    return {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "designation": user.designation,
        "role_name": user.role.name if hasattr(user.role, "name") else str(user.role),
        "organization_name": user.organization.name if user.organization else "",
        "status": user.status,
        "is_valid": True,
    }


def accept_invitation(token: str, data: dict, *, ip_address: str = "", user_agent: str = "") -> dict:
    """Complete employee onboarding: validate token, set password, mark ACTIVE and sign in."""
    if not token:
        raise ValidationError("Invitation token is required.")

    user = User.objects.filter(invite_token=token, is_deleted=False).first()
    if not user or user.status != UserStatus.INVITED:
        raise ValidationError("Invitation link is invalid, expired, or already accepted.")

    if user.invite_token_expires_at and datetime.now(timezone.utc) > user.invite_token_expires_at:
        raise ValidationError("Invitation link has expired.")

    password = validate_password(data.get("password"), "password")
    user.set_password(password)

    if data.get("first_name"):
        user.first_name = str(data["first_name"]).strip()
    if data.get("last_name"):
        user.last_name = str(data["last_name"]).strip()
    if data.get("phone"):
        user.phone = validate_phone(data["phone"])

    user.status = UserStatus.ACTIVE
    user.must_change_password = False
    user.invite_token = None
    user.invite_token_expires_at = None
    user.mark_logged_in()
    user.save()

    tokens = issue_token_pair(user, ip_address=ip_address, user_agent=user_agent)
    return {
        "user": user.to_dict(),
        "tokens": tokens,
        "message": "Invitation accepted! Welcome to your HRMS Portal.",
    }

