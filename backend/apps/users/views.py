"""Users + auth views.

Deliberately thin: declare the method and access rule, hand the request to a
controller.  Anything longer than one line belongs in `controllers.py`.
"""
from apps.users.controllers import (
    AuditController,
    AuthController,
    ProfileController,
    RoleController,
    SecurityController,
    UserController,
)
from core.decorators import admin_required, api_view, auth_required


# ---------------------------------------------------------------------------
# Auth (public)
# ---------------------------------------------------------------------------
@api_view("POST")
def register(request):
    return AuthController(request).register()


@api_view("POST")
def login(request):
    return AuthController(request).login()


@api_view("POST")
def refresh(request):
    return AuthController(request).refresh()


@api_view("POST")
def forgot_password(request):
    return AuthController(request).forgot_password()


@api_view("POST")
def reset_password(request):
    return AuthController(request).reset_password()


@api_view("POST")
def verify_email(request):
    return AuthController(request).verify_email()


@api_view("POST")
def mfa_verify(request):
    # No @auth_required: the caller only has the narrow mfa_pending_token at
    # this point, not a real session yet.
    return AuthController(request).mfa_verify()


# ---------------------------------------------------------------------------
# Auth (authenticated)
# ---------------------------------------------------------------------------
@api_view("POST")
def logout(request):
    # No @auth_required: signing out with an expired access token must still work.
    return AuthController(request).logout()


@api_view("GET")
@auth_required
def me(request):
    return AuthController(request).me()


@api_view("GET")
@auth_required
def sessions(request):
    return AuthController(request).sessions()


@api_view("DELETE")
@auth_required
def session_detail(request, session_id):
    return AuthController(request).revoke_session(session_id)


@api_view("POST")
@auth_required
def change_password(request):
    return AuthController(request).change_password()


@api_view("POST")
@auth_required
def resend_verification(request):
    return AuthController(request).resend_verification()


# ---------------------------------------------------------------------------
# Profile (self-service)
# ---------------------------------------------------------------------------
@api_view("GET", "PATCH", "PUT")
@auth_required
def profile(request):
    controller = ProfileController(request)
    if request.method == "GET":
        return controller.retrieve()
    return controller.update()


# ---------------------------------------------------------------------------
# Employee directory (admin panel)
# ---------------------------------------------------------------------------
@api_view("GET", "POST")
@auth_required
def user_collection(request):
    controller = UserController(request)
    return controller.list() if request.method == "GET" else controller.create()


@api_view("GET", "PATCH", "PUT", "DELETE")
@auth_required
def user_detail(request, user_id):
    controller = UserController(request)
    if request.method == "GET":
        return controller.retrieve(user_id)
    if request.method == "DELETE":
        return controller.destroy(user_id)
    return controller.update(user_id)


@api_view("POST")
@auth_required
def user_reset_password(request, user_id):
    return UserController(request).reset_password(user_id)


@api_view("GET")
@admin_required
def user_stats(request):
    return UserController(request).stats()


# ---------------------------------------------------------------------------
# RBAC (admin panel) - configurable role -> permission grants
# ---------------------------------------------------------------------------
@api_view("GET")
@auth_required
def role_collection(request):
    return RoleController(request).list_roles()


@api_view("GET", "PUT")
@auth_required
def role_detail(request, role):
    controller = RoleController(request)
    if request.method == "GET":
        return controller.retrieve(role)
    return controller.update(role)


# ---------------------------------------------------------------------------
# MFA (self-service security settings)
# ---------------------------------------------------------------------------
@api_view("POST")
@auth_required
def mfa_enroll_start(request):
    return SecurityController(request).enroll_start()


@api_view("POST")
@auth_required
def mfa_enroll_confirm(request):
    return SecurityController(request).enroll_confirm()


@api_view("POST")
@auth_required
def mfa_disable(request):
    return SecurityController(request).disable()


@api_view("POST")
@auth_required
def mfa_recovery_codes_regenerate(request):
    return SecurityController(request).regenerate_recovery_codes()


# ---------------------------------------------------------------------------
# Audit trail (admin panel, read-only)
# ---------------------------------------------------------------------------
@api_view("GET")
@auth_required
def audit_log_collection(request):
    return AuditController(request).list()
