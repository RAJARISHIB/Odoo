"""Organization + department business logic."""
import logging

from apps.organization.models import Department, Organization
from core.exceptions import Conflict, NotFound, ValidationError
from core.utils import deep_merge
from core.validators import pick, validate_email, validate_phone

logger = logging.getLogger(__name__)

#: Fields an admin may edit over the API.
EDITABLE_ORG_FIELDS = (
    "name", "phone", "website",
    "address_line1", "address_line2", "city", "state", "country", "postal_code",
    "timezone", "work_start_time", "work_end_time",
    "full_day_hours", "half_day_hours", "late_grace_minutes", "working_days",
)

EDITABLE_DEPARTMENT_FIELDS = ("name", "code", "description", "is_active")


def get_organization(org_id: str) -> Organization:
    organization = Organization.objects.filter(id=org_id, is_deleted=False).first()
    if not organization:
        raise NotFound("Organization not found.")
    return organization


def update_organization(organization: Organization, data: dict) -> Organization:
    updates = pick(data, EDITABLE_ORG_FIELDS)

    if "email" in data:
        updates["email"] = validate_email(data["email"])
    if "phone" in data:
        updates["phone"] = validate_phone(data["phone"])
    if "working_days" in updates:
        updates["working_days"] = _validate_working_days(updates["working_days"])
    for field in ("work_start_time", "work_end_time"):
        if field in updates:
            updates[field] = _validate_hhmm(updates[field], field)

    for field, value in updates.items():
        setattr(organization, field, value)

    # `settings` is merged, not replaced, so a partial update cannot wipe flags.
    if "settings" in data:
        if not isinstance(data["settings"], dict):
            raise ValidationError("Settings must be an object.", details={"settings": "Expected an object."})
        organization.settings = deep_merge(organization.settings, data["settings"])

    organization.save()
    return organization


def _validate_working_days(days) -> list:
    if not isinstance(days, list) or any(not isinstance(d, int) or d < 0 or d > 6 for d in days):
        raise ValidationError(
            "Invalid working days.",
            details={"working_days": "Expected a list of integers 0 (Mon) to 6 (Sun)."},
        )
    return sorted(set(days))


def _validate_hhmm(value: str, field: str) -> str:
    parts = str(value).split(":")
    valid = (
        len(parts) == 2
        and parts[0].isdigit() and parts[1].isdigit()
        and 0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59
    )
    if not valid:
        raise ValidationError("Invalid time.", details={field: "Use 24-hour HH:MM."})
    return "{:02d}:{:02d}".format(int(parts[0]), int(parts[1]))


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------
def list_departments(organization: Organization, *, search: str = None, active_only: bool = False):
    queryset = Department.objects.filter(organization=organization, is_deleted=False)
    if search:
        queryset = queryset.filter(name__icontains=search)
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


def get_department(organization: Organization, department_id: str) -> Department:
    department = Department.objects.filter(
        id=department_id, organization=organization, is_deleted=False
    ).first()
    if not department:
        raise NotFound("Department not found.")
    return department


def create_department(organization: Organization, data: dict) -> Department:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("Name is required.", details={"name": "This field is required."})

    duplicate = Department.objects.filter(
        organization=organization, name=name, is_deleted=False
    ).first()
    if duplicate:
        raise Conflict("A department with this name already exists.", code="department_exists")

    department = Department(organization=organization, name=name,
                            **pick(data, ("code", "description")))
    if data.get("head_id"):
        department.head = _user_in_org(organization, data["head_id"])
    department.save()
    return department


def update_department(organization: Organization, department: Department, data: dict) -> Department:
    for field, value in pick(data, EDITABLE_DEPARTMENT_FIELDS).items():
        setattr(department, field, value)
    if "head_id" in data:
        department.head = _user_in_org(organization, data["head_id"]) if data["head_id"] else None
    department.save()
    return department


def department_headcount(organization: Organization) -> list:
    """Employee count per department - feeds the admin dashboard chart."""
    from apps.users.models import User

    result = []
    for department in list_departments(organization):
        result.append(
            {
                "department_id": str(department.id),
                "name": department.name,
                "headcount": User.objects.filter(
                    organization=organization, department=department, is_deleted=False
                ).count(),
            }
        )
    return result


def _user_in_org(organization: Organization, user_id: str):
    from apps.users.models import User

    user = User.objects.filter(id=user_id, organization=organization, is_deleted=False).first()
    if not user:
        raise NotFound("User not found in this organization.")
    return user
