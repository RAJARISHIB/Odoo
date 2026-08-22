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

    path("roles/permissions", views.permissions_catalog, name="roles-permissions"),
    path("roles", views.role_collection, name="roles-collection"),
    path("roles/<str:role_id>", views.role_detail, name="roles-detail"),
    path("roles/<str:role_id>/assign", views.role_assign, name="roles-assign"),
    path("roles/permissions", views.permissions_catalog, name="roles-permissions"),
    path("roles", views.role_collection, name="roles-collection"),
    path("roles/<str:role_id>", views.role_detail, name="roles-detail"),
    path("roles/<str:role_id>/assign", views.role_assign, name="roles-assign"),
]


# /api/v1/users/... and /api/v1/profile
urlpatterns = [
    path("profile", views.profile, name="profile"),
    path("users", views.user_collection, name="user-collection"),
    path("users/stats", views.user_stats, name="user-stats"),
    path("users/<str:user_id>", views.user_detail, name="user-detail"),
    path("users/<str:user_id>/reset-password", views.user_reset_password, name="user-reset-password"),
    path("roles/permissions", views.permissions_catalog, name="roles-permissions"),
    path("roles", views.role_collection, name="roles-collection"),
    path("roles/<str:role_id>", views.role_detail, name="roles-detail"),
    path("roles/<str:role_id>/assign", views.role_assign, name="roles-assign"),
]
