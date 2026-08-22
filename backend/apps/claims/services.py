"""Business logic for Claims, Fines, and Employee Requests."""
from datetime import date, datetime, time, timezone
import os
from pathlib import Path
import uuid

from django.conf import settings

from apps.claims.models import EmployeeRequest, ExpenseClaim, Fine
from apps.users.models import User
from core.exceptions import NotFound, PermissionDenied, ValidationError
from core.validators import parse_date, require_fields, validate_choice, validate_object_id

ATTACHMENT_DIR = Path(settings.BASE_DIR).parent / "attachment_assets"
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB


def _ensure_attachment_dir():
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)


def _save_attachment_file(uploaded_file) -> tuple:
    """Save an uploaded file directly into attachment_assets/ folder.

    Returns (saved_filename, original_filename).
    """
    if not uploaded_file:
        return ("", "")

    if uploaded_file.size > MAX_ATTACHMENT_BYTES:
        raise ValidationError(
            "File size exceeds limit.",
            details={"file": "Maximum file size is 10 MB."},
        )

    _ensure_attachment_dir()
    original_name = getattr(uploaded_file, "name", "file")
    ext = os.path.splitext(original_name)[1].lower()
    saved_filename = f"{uuid.uuid4().hex}{ext}"
    target_path = ATTACHMENT_DIR / saved_filename

    with open(target_path, "wb") as target:
        for chunk in uploaded_file.chunks():
            target.write(chunk)

    return (saved_filename, original_name)


# ---------------------------------------------------------------------------
# 1. Expense Claims Services
# ---------------------------------------------------------------------------
def list_employee_claims(organization, employee: User):
    """Get claims submitted by signed-in employee."""
    return ExpenseClaim.objects.filter(
        organization=organization, employee=employee, is_deleted=False
    )


def create_claim(organization, employee: User, data: dict, receipt_file=None) -> ExpenseClaim:
    """Submit a new expense claim."""
    require_fields(data, ["expense_type", "amount", "expense_date", "description"])

    expense_type = validate_choice(
        data["expense_type"], ExpenseClaim.TYPE_CHOICES, "expense_type"
    )

    try:
        amount = float(data["amount"])
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValidationError("Amount must be greater than zero.", details={"amount": "Must be > 0."})

    expense_d = parse_date(data["expense_date"], "expense_date")
    expense_dt = datetime.combine(expense_d, time.min, tzinfo=timezone.utc)

    other_desc = ""
    if expense_type == ExpenseClaim.TYPE_OTHER:
        other_desc = str(data.get("other_type_description", "")).strip()
        if not other_desc:
            raise ValidationError(
                "Please specify the custom expense type.",
                details={"other_type_description": "Description required for Other expense type."},
            )

    saved_file, orig_name = _save_attachment_file(receipt_file)

    claim = ExpenseClaim(
        organization=organization,
        employee=employee,
        expense_type=expense_type,
        other_type_description=other_desc,
        amount=amount,
        expense_date=expense_dt,
        description=str(data["description"]).strip(),
        receipt_filename=saved_file,
        receipt_original_name=orig_name,
        status=ExpenseClaim.STATUS_PENDING,
    )
    return claim.save()


def list_admin_claims(organization, status: str = None):
    """List all organization claims for admin review."""
    qs = ExpenseClaim.objects.filter(organization=organization, is_deleted=False)
    if status:
        qs = qs.filter(status=status)
    return qs


def approve_claim(organization, claim_id: str, admin_user: User, comment: str = "") -> ExpenseClaim:
    """Approve an expense claim."""
    cid = validate_object_id(claim_id, "claim_id")
    claim = ExpenseClaim.objects.filter(id=cid, organization=organization, is_deleted=False).first()
    if not claim:
        raise NotFound("Expense claim not found.")

    claim.status = ExpenseClaim.STATUS_APPROVED
    claim.admin_comment = str(comment).strip()
    claim.processed_by = admin_user
    claim.processed_at = datetime.now(timezone.utc)
    return claim.save()


def reject_claim(organization, claim_id: str, admin_user: User, comment: str = "") -> ExpenseClaim:
    """Reject an expense claim."""
    cid = validate_object_id(claim_id, "claim_id")
    claim = ExpenseClaim.objects.filter(id=cid, organization=organization, is_deleted=False).first()
    if not claim:
        raise NotFound("Expense claim not found.")

    claim.status = ExpenseClaim.STATUS_REJECTED
    claim.admin_comment = str(comment).strip()
    claim.processed_by = admin_user
    claim.processed_at = datetime.now(timezone.utc)
    return claim.save()


def get_claim_attachment(organization, user: User, claim_id: str) -> tuple:
    """Retrieve receipt file path for a claim after verifying authorization."""
    cid = validate_object_id(claim_id, "claim_id")
    claim = ExpenseClaim.objects.filter(id=cid, organization=organization, is_deleted=False).first()
    if not claim or not claim.receipt_filename:
        raise NotFound("Receipt attachment not found.")

    # Authorization check: employee owner or admin
    if not user.is_admin and str(claim.employee.id) != str(user.id):
        raise PermissionDenied("You are not authorized to access this receipt.")

    file_path = ATTACHMENT_DIR / claim.receipt_filename
    if not file_path.exists():
        raise NotFound("Receipt file missing on server.")

    return (file_path, claim.receipt_original_name or claim.receipt_filename)


# ---------------------------------------------------------------------------
# 2. Fines Services
# ---------------------------------------------------------------------------
def list_employee_fines(organization, employee: User):
    """Get active fines applied to signed-in employee."""
    return Fine.objects.filter(
        organization=organization, employee=employee, is_deleted=False
    )


def list_admin_fines(organization, employee_id: str = None):
    """List organization fines for admin management."""
    qs = Fine.objects.filter(organization=organization, is_deleted=False)
    if employee_id:
        uid = validate_object_id(employee_id, "employee_id")
        qs = qs.filter(employee=uid)
    return qs


def create_fine(organization, admin_user: User, data: dict) -> Fine:
    """Apply a fine to an employee."""
    require_fields(data, ["employee_id", "amount", "reason"])

    uid = validate_object_id(data["employee_id"], "employee_id")
    emp = User.objects.filter(id=uid, organization=organization, is_deleted=False).first()
    if not emp:
        raise ValidationError("Employee not found.", details={"employee_id": "Invalid employee."})

    try:
        amount = float(data["amount"])
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValidationError("Amount must be greater than zero.", details={"amount": "Must be > 0."})

    fine_d = parse_date(data.get("date"), "date") or date.today()
    fine_dt = datetime.combine(fine_d, time.min, tzinfo=timezone.utc)

    fine = Fine(
        organization=organization,
        employee=emp,
        amount=amount,
        reason=str(data["reason"]).strip(),
        date=fine_dt,
        status=Fine.STATUS_ACTIVE,
        applied_by=admin_user,
    )
    return fine.save()


def update_fine_status(organization, fine_id: str, status: str) -> Fine:
    """Cancel or update fine status."""
    fid = validate_object_id(fine_id, "fine_id")
    fine = Fine.objects.filter(id=fid, organization=organization, is_deleted=False).first()
    if not fine:
        raise NotFound("Fine record not found.")

    status_val = validate_choice(status, Fine.STATUS_CHOICES, "status")
    fine.status = status_val
    return fine.save()


# ---------------------------------------------------------------------------
# 3. Employee Requests Services
# ---------------------------------------------------------------------------
def list_employee_requests(organization, employee: User):
    """List requests submitted by signed-in employee."""
    return EmployeeRequest.objects.filter(
        organization=organization, employee=employee, is_deleted=False
    )


def create_request(organization, employee: User, data: dict, attachment_file=None) -> EmployeeRequest:
    """Submit a new employee request (ID Card, Laptop, Other)."""
    require_fields(data, ["request_type", "description"])

    req_type = validate_choice(
        data["request_type"], EmployeeRequest.TYPE_CHOICES, "request_type"
    )

    saved_file, orig_name = _save_attachment_file(attachment_file)

    req = EmployeeRequest(
        organization=organization,
        employee=employee,
        request_type=req_type,
        description=str(data["description"]).strip(),
        attachment_filename=saved_file,
        attachment_original_name=orig_name,
        status=EmployeeRequest.STATUS_PENDING,
    )
    return req.save()


def list_admin_requests(organization, status: str = None, request_type: str = None):
    """List incoming employee requests for admin processing."""
    qs = EmployeeRequest.objects.filter(organization=organization, is_deleted=False)
    if status:
        qs = qs.filter(status=status)
    if request_type:
        qs = qs.filter(request_type=request_type)
    return qs


def approve_request(organization, request_id: str, admin_user: User) -> EmployeeRequest:
    """Approve an employee request."""
    rid = validate_object_id(request_id, "request_id")
    req = EmployeeRequest.objects.filter(id=rid, organization=organization, is_deleted=False).first()
    if not req:
        raise NotFound("Employee request not found.")

    req.status = EmployeeRequest.STATUS_APPROVED
    req.processed_by = admin_user
    req.processed_at = datetime.now(timezone.utc)
    return req.save()


def reject_request(organization, request_id: str, admin_user: User, rejection_reason: str = "") -> EmployeeRequest:
    """Reject an employee request with optional reason."""
    rid = validate_object_id(request_id, "request_id")
    req = EmployeeRequest.objects.filter(id=rid, organization=organization, is_deleted=False).first()
    if not req:
        raise NotFound("Employee request not found.")

    req.status = EmployeeRequest.STATUS_REJECTED
    req.rejection_reason = str(rejection_reason).strip()
    req.processed_by = admin_user
    req.processed_at = datetime.now(timezone.utc)
    return req.save()


def get_request_attachment(organization, user: User, request_id: str) -> tuple:
    """Retrieve attachment file path for a request after verifying authorization."""
    rid = validate_object_id(request_id, "request_id")
    req = EmployeeRequest.objects.filter(id=rid, organization=organization, is_deleted=False).first()
    if not req or not req.attachment_filename:
        raise NotFound("Attachment not found.")

    # Authorization check: employee owner or admin
    if not user.is_admin and str(req.employee.id) != str(user.id):
        raise PermissionDenied("You are not authorized to access this attachment.")

    file_path = ATTACHMENT_DIR / req.attachment_filename
    if not file_path.exists():
        raise NotFound("Attachment file missing on server.")

    return (file_path, req.attachment_original_name or req.attachment_filename)
