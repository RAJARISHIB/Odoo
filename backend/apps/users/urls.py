"""Routes for authentication, the signed-in profile and the employee directory.

Mounted by `hrms/urls.py` under /api/v1/.
"""
from django.urls import path

from apps.users import views

# /api/v1/auth/...
auth_urlpatterns = [
    path("register", views.register, name="auth-register"),
    path("login", views.login, name="auth-login"),
    path("refresh", views.refresh, name="auth-refresh"),
    path("logout", views.logout, name="auth-logout"),
    path("me", views.me, name="auth-me"),
    path("sessions", views.sessions, name="auth-sessions"),
    path("change-password", views.change_password, name="auth-change-password"),
    path("forgot-password", views.forgot_password, name="auth-forgot-password"),
    path("reset-password", views.reset_password, name="auth-reset-password"),
    path("verify-email", views.verify_email, name="auth-verify-email"),
    path("resend-verification", views.resend_verification, name="auth-resend-verification"),
    path("mfa/verify", views.mfa_verify, name="auth-mfa-verify"),
    path("sessions/<str:session_id>", views.session_detail, name="auth-session-detail"),
]

# /api/v1/users/... and /api/v1/profile
urlpatterns = [
    path("profile", views.profile, name="profile"),
    path("users", views.user_collection, name="user-collection"),
    path("users/stats", views.user_stats, name="user-stats"),
    path("users/<str:user_id>", views.user_detail, name="user-detail"),
    path("users/<str:user_id>/reset-password", views.user_reset_password, name="user-reset-password"),

    # Self-service MFA settings.
    path("security/mfa/enroll/start", views.mfa_enroll_start, name="mfa-enroll-start"),
    path("security/mfa/enroll/confirm", views.mfa_enroll_confirm, name="mfa-enroll-confirm"),
    path("security/mfa/disable", views.mfa_disable, name="mfa-disable"),
    path(
        "security/mfa/recovery-codes/regenerate",
        views.mfa_recovery_codes_regenerate,
        name="mfa-recovery-codes-regenerate",
    ),
]

# /api/v1/admin/roles/... - configurable RBAC
admin_urlpatterns = [
    path("roles", views.role_collection, name="admin-role-collection"),
    path("roles/<str:role>/permissions", views.role_detail, name="admin-role-detail"),
    path("audit-logs", views.audit_log_collection, name="admin-audit-log-collection"),
]
