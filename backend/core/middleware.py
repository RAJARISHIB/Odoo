"""Request/response middleware.

`RequestContextMiddleware` resolves the bearer token once per request so every
view and controller can read `request.auth_user`.  `ExceptionHandlerMiddleware`
turns raised exceptions into the standard JSON error envelope, which is why
controllers can raise freely instead of catching.
"""
import logging
import time
import traceback

from django.conf import settings
from django.http import Http404
from mongoengine.errors import DoesNotExist
from mongoengine.errors import ValidationError as MongoValidationError

from core import responses
from core.exceptions import ApiError, AuthenticationError, NotFound
from core.security import decode_token, extract_bearer_token
from core.utils import new_request_id

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware:
    """Headers that apply to every JSON API response.

    This is separate from the CSP the Angular app itself ships in its
    `index.html` - that one protects the SPA's own document; this one protects
    whatever ends up rendering an API response directly (an error page opened
    in a browser, a downloaded file, ...).
    """

    #: Deliberately restrictive - this middleware only ever serves JSON/media,
    #: never a page that legitimately needs scripts, styles or third-party
    #: frames.
    _CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Content-Security-Policy"] = self._CSP
        response["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.setdefault("X-Content-Type-Options", "nosniff")
        return response


class RequestContextMiddleware:
    """Attach `request_id` and the authenticated user to every request.

    A bad token is recorded on `request.auth_error` rather than raised here, so
    public endpoints (login, refresh, health) still work when the browser is
    holding a stale token.  `@auth_required` is what raises it.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.META.get("HTTP_X_REQUEST_ID") or new_request_id()
        request.auth_user = None
        request.auth_payload = None
        request.auth_error = None

        token = extract_bearer_token(request)
        if token:
            self._resolve_user(request, token)

        started = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - started) * 1000

        response["X-Request-Id"] = request.request_id
        logger.info(
            "%s %s -> %s (%.1fms) user=%s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            request.auth_user.email if request.auth_user else "anonymous",
        )
        return response

    @staticmethod
    def _resolve_user(request, token):
        from apps.users.models import User
        from core.constants import UserStatus

        try:
            payload = decode_token(token)
            user = User.objects.filter(id=payload["sub"], is_deleted=False).first()
            if not user:
                raise AuthenticationError("User no longer exists.", code="user_not_found")
            if user.status != UserStatus.ACTIVE:
                raise AuthenticationError(
                    "Account is {}.".format(user.status), code="account_inactive"
                )
            request.auth_user = user
            request.auth_payload = payload
        except ApiError as exc:
            request.auth_error = exc
        except Exception as exc:  # Mongo unreachable, malformed id, ...
            logger.warning("Auth resolution failed: %s", exc)
            request.auth_error = AuthenticationError("Could not verify credentials.")


class ExceptionHandlerMiddleware:
    """Single place where exceptions become JSON."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    #: Exception `code`s worth a security audit entry - denied authorization
    #: and the auth-abuse-shaped failures, not routine 401s from an expired
    #: token (those are normal traffic, not a security event).
    _AUDITED_CODES = {
        "permission_denied", "account_locked", "invalid_mfa_code",
        "mfa_setup_required", "step_up_required", "rate_limited",
    }

    def process_exception(self, request, exception):
        if isinstance(exception, ApiError):
            if exception.status_code >= 500:
                logger.error("[%s] %s", getattr(request, "request_id", "-"), exception)
            if exception.code in self._AUDITED_CODES:
                self._audit_denied(request, exception)
            return responses.from_exception(exception)

        if isinstance(exception, (Http404, DoesNotExist)):
            return responses.from_exception(NotFound())

        if isinstance(exception, MongoValidationError):
            # `to_dict()` is safe (field name -> message, no driver/connection
            # internals); `str(exception)` on some mongoengine errors can
            # include more than that, so it is never used as a fallback here.
            details = exception.to_dict() if hasattr(exception, "to_dict") else None
            return responses.error(
                "The document failed validation.",
                code="validation_error",
                details=details,
                status=422,
            )

        logger.error(
            "[%s] Unhandled exception on %s %s\n%s",
            getattr(request, "request_id", "-"),
            request.method,
            request.path,
            traceback.format_exc(),
        )
        details = {"exception": repr(exception)} if settings.DEBUG else None
        return responses.error(
            "An unexpected error occurred.",
            code="internal_error",
            details=details,
            status=500,
        )

    @staticmethod
    def _audit_denied(request, exception):
        from core.audit import record
        from core.constants import AuditAction
        from core.utils import client_ip, user_agent

        user = getattr(request, "auth_user", None)
        record(
            action=AuditAction.ACCESS_DENIED,
            actor=user,
            resource_type="endpoint",
            resource_id=request.path,
            result="denied",
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            metadata={"method": request.method, "reason": exception.code},
        )
