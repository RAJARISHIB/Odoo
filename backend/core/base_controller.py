"""BaseController - the shared behaviour behind every API controller.

Views stay thin (parse the URL, hand off) and all request handling lives here:
body/query access, validation entry points, the authenticated user, tenant
scoping, pagination, the response envelope and realtime emission.

A controller is instantiated per request::

    class AttendanceController(BaseController):
        def check_in(self):
            user = self.require_user()
            record = attendance_service.check_in(user, source=self.field("source", "web"))
            self.emit_to_admins(RealtimeEvent.ATTENDANCE_CHECKED_IN, record.to_dict())
            return self.created(record.to_dict(), "Checked in.")
"""
import logging

from django.conf import settings

from core import realtime, responses
from core.constants import Role
from core.exceptions import AuthenticationError, NotFound, PermissionDenied, ValidationError
from core.pagination import paginate
from core.utils import client_ip, parse_json_body, user_agent
from core.validators import parse_int, require_fields, validate_object_id

logger = logging.getLogger(__name__)


class BaseController:
    """Per-request controller base.  Subclass it, one controller per resource."""

    #: Roles allowed to reach any action on this controller. `None` means "any
    #: authenticated user"; per-action rules go in the action itself.
    allowed_roles = None

    def __init__(self, request):
        self.request = request
        self.user = getattr(request, "auth_user", None)
        self.token_payload = getattr(request, "auth_payload", None)
        self.request_id = getattr(request, "request_id", None)
        self._body_cache = None

        if self.allowed_roles and self.user:
            self.require_roles(*self.allowed_roles)

    # -----------------------------------------------------------------
    # Request data
    # -----------------------------------------------------------------
    @property
    def data(self) -> dict:
        """The request body as a dict (cached).

        Handles both content types the UI sends: JSON for ordinary calls, and
        multipart form data when a file rides along (the signup form posts the
        company logo this way).  Controllers never need to know which arrived.
        """
        if self._body_cache is None:
            if self.is_multipart:
                self._body_cache = self.request.POST.dict()
            else:
                self._body_cache = parse_json_body(self.request)
        return self._body_cache

    @property
    def is_multipart(self) -> bool:
        return self.request.content_type.startswith("multipart/form-data")

    def file(self, name: str, required: bool = False):
        """One uploaded file, or None.  See `core.storage` for validation."""
        uploaded = self.request.FILES.get(name)
        if required and not uploaded:
            raise ValidationError(
                "A file is required.", details={name: "This field is required."}
            )
        return uploaded

    @property
    def query(self):
        return self.request.GET

    def field(self, name: str, default=None):
        """One field from the JSON body."""
        value = self.data.get(name, default)
        return value.strip() if isinstance(value, str) else value

    def param(self, name: str, default=None, cast=None):
        """One query-string parameter, optionally cast."""
        value = self.query.get(name, default)
        if value is None or value == "":
            return default
        return cast(value) if cast else value

    def require(self, *fields) -> dict:
        """Assert the body carries these fields, then return the whole body."""
        return require_fields(self.data, fields)

    def object_id(self, value, field: str = "id") -> str:
        return validate_object_id(value, field)

    def page_params(self) -> tuple:
        return (
            parse_int(self.query.get("page"), 1, "page"),
            parse_int(self.query.get("page_size"), settings.API["DEFAULT_PAGE_SIZE"], "page_size"),
        )

    @property
    def client_meta(self) -> dict:
        """Request provenance, stored on audit-ish records (attendance, sessions)."""
        return {"ip_address": client_ip(self.request), "user_agent": user_agent(self.request)}

    # -----------------------------------------------------------------
    # Authentication / authorisation
    # -----------------------------------------------------------------
    @property
    def is_authenticated(self) -> bool:
        return self.user is not None

    @property
    def role(self):
        if not self.user or not self.user.role:
            return None
        return getattr(self.user.role, "slug", str(self.user.role))

    @property
    def organization_id(self):
        """Tenant the caller belongs to - every list query is scoped by this."""
        if self.user and self.user.organization:
            return self.user.organization.id
        return None

    def require_user(self):
        """The authenticated user, or a 401."""
        if not self.user:
            raise AuthenticationError()
        return self.user

    def require_permissions(self, *permissions):
        """Restrict an action to users holding ALL the specified permissions."""
        user = self.require_user()
        missing = [p for p in permissions if not user.has_permission(p)]
        if missing:
            raise PermissionDenied(
                "This action requires permissions: {}.".format(", ".join(missing))
            )
        return user

    def require_roles(self, *roles):
        """Restrict an action to specific role slugs."""
        user = self.require_user()
        user_role_slug = self.role
        if user_role_slug not in roles:
            raise PermissionDenied(
                "This action requires one of these roles: {}.".format(", ".join(roles))
            )
        return user

    def require_admin(self):
        """Any role that has access to the admin panel."""
        return self.require_roles(*Role.ADMIN_PANEL)

    def require_super_admin(self):
        return self.require_roles(Role.SUPER_ADMIN)

    @property
    def is_admin(self) -> bool:
        return bool(self.user and getattr(self.user.role, "slug", str(self.user.role)) in Role.ADMIN_PANEL)


    def is_self(self, user_id) -> bool:
        return bool(self.user and str(self.user.id) == str(user_id))

    def assert_same_organization(self, document):
        """Block cross-tenant access.  Super admins are exempt."""
        if self.role == Role.SUPER_ADMIN:
            return document
        target_org = getattr(document, "organization", None)
        if target_org is None or self.organization_id is None:
            raise PermissionDenied("Resource is not scoped to your organization.")
        if str(target_org.id) != str(self.organization_id):
            raise PermissionDenied("Resource belongs to another organization.")
        return document

    def assert_self_or_admin(self, user_id):
        """Employees may only touch their own records; admins may touch anyone's."""
        if self.is_self(user_id) or self.is_admin:
            return True
        raise PermissionDenied("You may only access your own records.")

    def scoped(self, document_class):
        """Queryset pre-filtered to live documents in the caller's organization."""
        queryset = document_class.objects.filter(is_deleted=False)
        if self.role != Role.SUPER_ADMIN and self.organization_id:
            queryset = queryset.filter(organization=self.organization_id)
        return queryset

    def get_or_404(self, document_class, object_id, message: str = None):
        """Fetch by id within the caller's tenant, or raise 404."""
        self.object_id(object_id)
        document = self.scoped(document_class).filter(id=object_id).first()
        if not document:
            raise NotFound(message or "{} not found.".format(document_class.__name__))
        return document

    # -----------------------------------------------------------------
    # Responses
    # -----------------------------------------------------------------
    def ok(self, data=None, message: str = None, meta: dict = None):
        return responses.success(data=data, message=message, meta=meta)

    def created(self, data=None, message: str = "Created successfully."):
        return responses.created(data=data, message=message)

    def deleted(self, message: str = "Deleted successfully."):
        return responses.success(data=None, message=message)

    def paginated(self, queryset, serializer=None, message: str = None, extra_meta: dict = None):
        """List response with `meta.page`, `meta.total`, ... for the UI pager."""
        page, page_size = self.page_params()
        serializer = serializer or (lambda item: item.to_dict())
        items, meta = paginate(queryset, page, page_size, serializer)
        if extra_meta:
            meta.update(extra_meta)
        return responses.success(data=items, message=message, meta=meta)

    # -----------------------------------------------------------------
    # Realtime (fire-and-forget, never blocks the response)
    # -----------------------------------------------------------------
    def emit_to_user(self, user_id, event: str, payload: dict = None):
        return realtime.notify_user(user_id, event, payload, actor_id=self.user.id if self.user else None)

    def emit_to_org(self, event: str, payload: dict = None, org_id=None):
        return realtime.notify_org(
            org_id or self.organization_id, event, payload,
            actor_id=self.user.id if self.user else None,
        )

    def emit_to_admins(self, event: str, payload: dict = None, org_id=None):
        return realtime.notify_admins(
            org_id or self.organization_id, event, payload,
            actor_id=self.user.id if self.user else None,
        )

    def notify_relevant(self, event: str, payload: dict = None, *, subject_user=None, department=None, org_id=None):
        """Like `emit_to_admins`, but scoped down from every admin-panel user
        to whoever actually has a reason to see this event: the org's own
        oversight roles (`super_admin`/`admin`/`hr` - unaffected, they already
        see everything and should keep doing so) plus, for an event about one
        employee, that employee's own manager(s) via the team hierarchy; or
        for an event about a department, that department's members. A plain
        `manager` with no relationship to the subject no longer gets it.

        Deferred imports: `core` stays app-agnostic, importing `apps.*` only
        inside the method that needs them rather than at module load time.
        """
        from apps.teams.services import get_managers_of
        from apps.users.models import Role as RoleDoc, User

        org = org_id or self.organization_id
        oversight_roles = list(RoleDoc.objects.filter(
            organization=org, slug__in=(Role.SUPER_ADMIN, Role.ADMIN, Role.HR),
        ))
        recipient_ids = {
            str(u.id) for u in User.objects.filter(organization=org, role__in=oversight_roles, is_deleted=False)
        }

        if subject_user is not None:
            recipient_ids.update(get_managers_of(org, subject_user))
        if department is not None:
            recipient_ids.update(
                str(u.id) for u in User.objects.filter(organization=org, department=department, is_deleted=False)
            )

        for user_id in recipient_ids:
            self.emit_to_user(user_id, event, payload)

    # -----------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------
    def log(self, message: str, *args, level: int = logging.INFO):
        logger.log(
            level,
            "[%s][%s] " + message,
            self.request_id,
            self.user.email if self.user else "anonymous",
            *args,
        )
