"""API exception hierarchy.

Controllers raise these; `core.middleware.ExceptionHandlerMiddleware` turns them
into the standard JSON error envelope, so no controller needs try/except for
control flow.
"""


class ApiError(Exception):
    status_code = 400
    code = "bad_request"
    message = "The request could not be processed."

    def __init__(self, message: str = None, *, code: str = None, details=None, status_code: int = None):
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)

    def to_dict(self) -> dict:
        payload = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class ValidationError(ApiError):
    status_code = 422
    code = "validation_error"
    message = "One or more fields are invalid."


class AuthenticationError(ApiError):
    status_code = 401
    code = "unauthenticated"
    message = "Authentication credentials were missing or invalid."


class PermissionDenied(ApiError):
    status_code = 403
    code = "permission_denied"
    message = "You do not have permission to perform this action."


class NotFound(ApiError):
    status_code = 404
    code = "not_found"
    message = "The requested resource was not found."


class MethodNotAllowed(ApiError):
    status_code = 405
    code = "method_not_allowed"
    message = "This method is not allowed on this endpoint."


class Conflict(ApiError):
    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state of the resource."


class ServiceUnavailable(ApiError):
    status_code = 503
    code = "service_unavailable"
    message = "A downstream service is unavailable."


class TooManyRequests(ApiError):
    status_code = 429
    code = "too_many_requests"
    message = "Too many attempts. Please try again later."


class MfaRequired(ApiError):
    status_code = 403
    code = "mfa_setup_required"
    message = "Enable multi-factor authentication to perform this action."


class StepUpRequired(ApiError):
    status_code = 401
    code = "step_up_required"
    message = "Please re-enter your password to continue."
