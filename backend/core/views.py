"""Platform-level endpoints that belong to no single domain app:
health checks, the API index, and the callback the Express hub uses to report
websocket presence back to Django.
"""
import logging

from django.conf import settings
from django.shortcuts import redirect

from core import mongo, realtime, responses
from core.base_controller import BaseController
from core.decorators import api_view, internal_only
from core.utils import parse_json_body

logger = logging.getLogger(__name__)


class SystemController(BaseController):
    def health(self):
        """Liveness plus the state of both dependencies."""
        mongo_status = mongo.ping()
        hub_status = realtime.hub_health()
        healthy = mongo_status["status"] == "up"
        return responses.success(
            {
                "service": "hrms-api",
                "status": "ok" if healthy else "degraded",
                "debug": settings.DEBUG,
                "dependencies": {"mongo": mongo_status, "realtime": hub_status},
            },
            status=200 if healthy else 503,
        )

    def index(self):
        """Route map - a quick contract reference while building the UI."""
        return self.ok(
            {
                "service": "hrms-api",
                "version": "v1",
                "endpoints": {
                    "auth": [
                        "POST   /api/v1/auth/register",
                        "POST   /api/v1/auth/login",
                        "POST   /api/v1/auth/refresh",
                        "POST   /api/v1/auth/logout",
                        "GET    /api/v1/auth/me",
                        "GET    /api/v1/auth/sessions",
                        "POST   /api/v1/auth/change-password",
                    ],
                    "profile": [
                        "GET    /api/v1/profile",
                        "PATCH  /api/v1/profile",
                    ],
                    "users": [
                        "GET    /api/v1/users",
                        "POST   /api/v1/users",
                        "GET    /api/v1/users/stats",
                        "GET    /api/v1/users/{id}",
                        "PATCH  /api/v1/users/{id}",
                        "DELETE /api/v1/users/{id}",
                        "POST   /api/v1/users/{id}/reset-password",
                    ],
                    "organization": [
                        "GET    /api/v1/organization",
                        "PATCH  /api/v1/organization",
                        "GET    /api/v1/organization/overview",
                        "GET    /api/v1/departments",
                        "POST   /api/v1/departments",
                        "GET    /api/v1/departments/{id}",
                        "PATCH  /api/v1/departments/{id}",
                        "DELETE /api/v1/departments/{id}",
                    ],
                    "attendance": [
                        "GET    /api/v1/attendance/status",
                        "POST   /api/v1/attendance/check-in",
                        "POST   /api/v1/attendance/check-out",
                        "GET    /api/v1/attendance/me",
                        "GET    /api/v1/attendance/me/summary",
                    ],
                    "admin": [
                        "GET    /api/v1/admin/attendance",
                        "POST   /api/v1/admin/attendance",
                        "GET    /api/v1/admin/attendance/overview",
                        "GET    /api/v1/admin/attendance/{id}",
                        "DELETE /api/v1/admin/attendance/{id}",
                        "GET    /api/v1/admin/attendance/users/{id}/summary",
                    ],
                },
            }
        )


@api_view("GET")
def health(request):
    return SystemController(request).health()


@api_view("GET")
def index(request):
    return SystemController(request).index()


@api_view("POST")
@internal_only
def realtime_presence(request):
    """Called by the Express hub when a client connects or disconnects.

    Authenticated with the shared internal key, not a user token.  Kept as a
    logging hook for now - persist it here when presence needs to be queryable.
    """
    payload = parse_json_body(request)
    logger.info(
        "Presence: user=%s event=%s connections=%s panel=%s",
        payload.get("user_id"),
        payload.get("event"),
        payload.get("connection_count"),
        payload.get("panel"),
    )
    return responses.success({"received": True})


def _frontend_url(path: str = None) -> str:
    return settings.FRONTEND_URL.rstrip("/") + (path or settings.FRONTEND_LOGIN_PATH)


def _wants_html(request) -> bool:
    """True for a person in a browser, false for an API client."""
    accept = request.META.get("HTTP_ACCEPT", "")
    return "text/html" in accept and "application/json" not in accept


@api_view("GET")
def root(request):
    """The API host has no pages of its own.

    A browser gets sent to the Angular sign-in page; anything speaking JSON
    gets the route map instead of a surprise redirect.
    """
    if _wants_html(request):
        return redirect(_frontend_url())
    return SystemController(request).index()


def not_found(request, exception=None):
    """Project-wide 404.

    API clients get the JSON error envelope.  A browser that wandered onto an
    unknown path is sent to the sign-in page - the same reasoning as `root`.
    """
    if _wants_html(request) and not request.path.startswith("/api/"):
        return redirect(_frontend_url())
    return responses.error("Endpoint not found.", code="not_found", status=404)


def server_error(request):
    return responses.error("An unexpected error occurred.", code="internal_error", status=500)
