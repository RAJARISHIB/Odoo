"""Root URL configuration.

    /api/v1/auth/...            authentication (public + session)
    /api/v1/users, /profile     employee directory + self-service
    /api/v1/organization, /departments
    /api/v1/attendance/...      employee punches (user panel)
    /api/v1/admin/...           admin panel surface
    /api/v1/internal/...        service-to-service (Express hub)
"""
from django.urls import include, path

from apps.attendance.urls import admin_urlpatterns as attendance_admin_urls
from apps.users.urls import auth_urlpatterns
from core import views as core_views

API_PREFIX = "api/v1/"

urlpatterns = [
    path(API_PREFIX, core_views.index, name="api-index"),
    path(API_PREFIX + "health", core_views.health, name="health"),

    path(API_PREFIX + "auth/", include((auth_urlpatterns, "auth"))),
    path(API_PREFIX, include("apps.users.urls")),
    path(API_PREFIX, include("apps.organization.urls")),
    path(API_PREFIX, include("apps.attendance.urls")),

    path(API_PREFIX + "admin/", include((attendance_admin_urls, "admin"))),

    path(API_PREFIX + "internal/realtime/presence", core_views.realtime_presence,
         name="internal-realtime-presence"),
]

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
