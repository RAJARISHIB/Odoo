"""View decorators.

Views are thin, so the cross-cutting rules (allowed methods, authentication,
role gates, service-to-service keys) are declared right on top of them::

    @api_view("POST")
    @auth_required
    def check_in(request):
        return AttendanceController(request).check_in()
"""
import functools

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from core.constants import Role
from core.exceptions import AuthenticationError, MethodNotAllowed, PermissionDenied, StepUpRequired


def api_view(*methods):
    """Restrict a view to the given HTTP methods and exempt it from CSRF.

    Token-authenticated JSON APIs do not use Django's session CSRF flow.
    OPTIONS is always allowed so the CORS preflight succeeds.
    """
    allowed = {method.upper() for method in methods} or {"GET"}
    allowed.add("OPTIONS")

    def decorator(view):
        @csrf_exempt
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in allowed:
                raise MethodNotAllowed(
                    "Method {} is not allowed here. Allowed: {}.".format(
                        request.method, ", ".join(sorted(allowed - {"OPTIONS"}))
                    )
                )
            return view(request, *args, **kwargs)

        wrapper.allowed_methods = sorted(allowed)
        return wrapper

    return decorator


def auth_required(view):
    """Require a valid access token.

    `RequestContextMiddleware` has already tried to resolve the token; this is
    where a missing or rejected one becomes a 401.
    """

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method == "OPTIONS":
            return view(request, *args, **kwargs)
        auth_error = getattr(request, "auth_error", None)
        if auth_error:
            raise auth_error
        if not getattr(request, "auth_user", None):
            raise AuthenticationError("Authentication required.")
        return view(request, *args, **kwargs)

    wrapper.auth_required = True
    return wrapper


def roles_required(*roles):
    """Require an authenticated user holding one of `roles`."""

    def decorator(view):
        @auth_required
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method == "OPTIONS":
                return view(request, *args, **kwargs)
            user = request.auth_user
            role_slug = getattr(user.role, "slug", str(user.role or "")) if user and user.role else ""
            if role_slug not in roles:
                raise PermissionDenied(
                    "Requires one of these roles: {}.".format(", ".join(roles))
                )
            return view(request, *args, **kwargs)

        wrapper.required_roles = roles
        return wrapper

    return decorator


def permissions_required(*permissions):
    """Require an authenticated user holding all of the specified permissions.

    Also enforces MFA for the small set of permissions the org has flagged as
    high-risk (see `core.permissions.MFA_REQUIRED_PERMISSIONS`), regardless of
    role - a role's `has_permission` grant is necessary but not sufficient for
    those.
    """

    def decorator(view):
        @auth_required
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method == "OPTIONS":
                return view(request, *args, **kwargs)
            from core.permissions import assert_mfa_satisfied

            user = request.auth_user
            missing = [p for p in permissions if not user.has_permission(p)]
            if missing:
                raise PermissionDenied(
                    "Missing required permissions: {}.".format(", ".join(missing))
                )
            for permission in permissions:
                assert_mfa_satisfied(user, permission)
            return view(request, *args, **kwargs)

        wrapper.required_permissions = permissions
        return wrapper

    return decorator


def any_permission_required(*permissions):
    """Require an authenticated user holding at least one of the specified permissions."""

    def decorator(view):
        @auth_required
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method == "OPTIONS":
                return view(request, *args, **kwargs)
            user = request.auth_user
            if not any(user.has_permission(p) for p in permissions):
                raise PermissionDenied(
                    "Requires at least one of these permissions: {}.".format(", ".join(permissions))
                )
            return view(request, *args, **kwargs)

        wrapper.required_any_permissions = permissions
        return wrapper

    return decorator


def step_up_required(max_age_seconds: int = 900):
    """View-level equivalent of `BaseController.require_step_up` - see there
    for what "step up" means. Use this on plain function views; controller
    actions should call `self.require_step_up()` instead."""

    def decorator(view):
        @auth_required
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method == "OPTIONS":
                return view(request, *args, **kwargs)
            import time as _time

            payload = getattr(request, "auth_payload", None) or {}
            reauth_at = payload.get("reauth_at")
            if not reauth_at or (_time.time() - reauth_at) > max_age_seconds:
                raise StepUpRequired()
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def admin_required(view):
    """Shorthand for any role that can reach the admin panel."""
    return roles_required(*Role.ADMIN_PANEL)(view)


def internal_only(view):
    """Service-to-service guard.

    Used by callbacks the Express hub makes back into Django (presence updates,
    for example).  Authenticates with the shared `INTERNAL_API_KEY`, not a JWT.
    """

    @csrf_exempt
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        provided = request.META.get("HTTP_X_INTERNAL_KEY", "")
        expected = settings.REALTIME["INTERNAL_API_KEY"]
        if not provided or provided != expected:
            raise PermissionDenied("Invalid internal service key.", code="invalid_internal_key")
        return view(request, *args, **kwargs)

    wrapper.internal_only = True
    return wrapper
