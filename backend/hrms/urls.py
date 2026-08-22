"""Root URL configuration.

    /                           redirects to the Angular sign-in page
    /api/v1/                    route map
    /api/v1/auth/...            authentication (public + session)
    /api/v1/users, /profile     employee directory + self-service
    /api/v1/organization, /departments
    /api/v1/attendance/...      employee punches (user panel)
    /api/v1/admin/...           admin panel surface
    /api/v1/internal/...        service-to-service (Express hub)
    /media/...                  uploaded logos and avatars (dev only)
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path

from apps.attendance.urls import admin_urlpatterns as attendance_admin_urls
from apps.teams.urls import admin_urlpatterns as teams_admin_urls
from apps.leaves.urls import admin_urlpatterns as leaves_admin_urls
from apps.users.urls import admin_urlpatterns as users_admin_urls
from apps.users.urls import auth_urlpatterns
from core import views as core_views

API_PREFIX = "api/v1/"

urlpatterns = [
    # A browser hitting the API host should land somewhere useful rather than
    # on a 404, so the bare host and a few common paths bounce to the UI.
    path("", core_views.root, name="root"),
    path("login", core_views.root, name="root-login"),
    path("api/", core_views.root, name="root-api"),

    path(API_PREFIX, core_views.index, name="api-index"),
    path(API_PREFIX + "health", core_views.health, name="health"),

    path(API_PREFIX + "auth/", include((auth_urlpatterns, "auth"))),
    path(API_PREFIX, include("apps.users.urls")),
    path(API_PREFIX, include("apps.organization.urls")),
    path(API_PREFIX, include("apps.attendance.urls")),
    path(API_PREFIX, include("apps.leaves.urls")),
    path(API_PREFIX, include("apps.teams.urls")),

    path(API_PREFIX + "admin/", include((attendance_admin_urls, "admin"))),
    path(API_PREFIX + "admin/", include((leaves_admin_urls, "admin-leaves"))),
    path(API_PREFIX + "admin/", include((teams_admin_urls, "admin-teams"))),
    path(API_PREFIX + "admin/", include((users_admin_urls, "admin-users"))),

    path(API_PREFIX + "internal/realtime/presence", core_views.realtime_presence,
         name="internal-realtime-presence"),
]

# In production the uploads directory is served by nginx or object storage.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Catch-all, registered last.  `handler404` alone is not enough: Django only
# consults it when DEBUG is off, and an unknown path should behave the same in
# development - JSON for API clients, a redirect to the UI for browsers.
urlpatterns += [re_path(r"^.*$", core_views.not_found)]

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
