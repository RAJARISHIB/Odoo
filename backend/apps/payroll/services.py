"""Business logic for Payroll, Role Templates, Employee Assignments, and Documents."""
from datetime import date, datetime, time, timezone
import os
from pathlib import Path
import uuid

from django.conf import settings

from apps.claims.services import ATTACHMENT_DIR, MAX_ATTACHMENT_BYTES, _save_attachment_file
from apps.payroll.calculator import calculate_salary_structure
from apps.payroll.models import EmployeePayroll, PayrollDocument, RoleSalaryTemplate, SalaryComponent
from apps.users.models import User
from core.constants import Role
from core.exceptions import NotFound, PermissionDenied, ValidationError
from core.validators import parse_date, require_fields, validate_choice, validate_object_id


# ---------------------------------------------------------------------------
# Default Default Salary Components Template
# ---------------------------------------------------------------------------
def get_default_salary_components(monthly_wage: float = 50000.0) -> list:
    """Returns default standard salary components breakdown for a wage."""
    return [
        {
            "name": "Basic Salary",
            "calculation_type": SalaryComponent.CALC_PERCENTAGE,
            "value": 50.0,
            "depends_on": "WAGE",
            "is_fixed_allowance_remainder": False,
        },
        {
            "name": "House Rent Allowance",
            "calculation_type": SalaryComponent.CALC_PERCENTAGE,
            "value": 50.0,
            "depends_on": "Basic Salary",
            "is_fixed_allowance_remainder": False,
        },
        {
            "name": "Standard Allowance",
            "calculation_type": SalaryComponent.CALC_PERCENTAGE,
            "value": 16.67,
            "depends_on": "WAGE",
            "is_fixed_allowance_remainder": False,
        },
        {
            "name": "Performance Bonus",
            "calculation_type": SalaryComponent.CALC_PERCENTAGE,
            "value": 8.33,
            "depends_on": "WAGE",
            "is_fixed_allowance_remainder": False,
        },
        {
            "name": "Leave Travel Allowance",
            "calculation_type": SalaryComponent.CALC_PERCENTAGE,
            "value": 8.33,
            "depends_on": "WAGE",
            "is_fixed_allowance_remainder": False,
        },
        {
            "name": "Fixed Allowance",
            "calculation_type": SalaryComponent.CALC_FIXED,
            "value": 0.0,
            "depends_on": "WAGE",
            "is_fixed_allowance_remainder": True,
        },
    ]


# ---------------------------------------------------------------------------
# 1. Role Salary Templates
# ---------------------------------------------------------------------------
def list_role_templates(organization):
    """List all role salary templates for an organization."""
    return RoleSalaryTemplate.objects.filter(organization=organization, is_deleted=False)


def get_role_template(organization, template_id_or_role: str) -> RoleSalaryTemplate:
    """Get a role salary template by ID or Role name."""
    template = RoleSalaryTemplate.objects.filter(
        id=template_id_or_role, organization=organization, is_deleted=False
    ).first()
    if not template:
        template = RoleSalaryTemplate.objects.filter(
            role=template_id_or_role, organization=organization, is_deleted=False
        ).first()
    if not template:
        raise NotFound("Role salary template not found.")
    return template


def upsert_role_template(organization, data: dict) -> RoleSalaryTemplate:
    """Create or update a role salary template.

    Recalculates structure and automatically updates all employees with
    salary_source == 'ROLE' matching this role template. Employees with
    salary_source == 'MANUAL' are preserved and untouched.
    """
    require_fields(data, ["role", "monthly_wage"])
    role_val = validate_choice(data["role"], Role.CHOICES, "role")

    try:
        monthly_wage = float(data["monthly_wage"])
        if monthly_wage <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValidationError("Monthly wage must be greater than zero.", details={"monthly_wage": "Must be > 0."})

    components_raw = data.get("components")
    if not components_raw:
        components_raw = get_default_salary_components(monthly_wage)

    employee_pf_rate = float(data.get("employee_pf_rate", 12.0) or 12.0)
    employer_pf_rate = float(data.get("employer_pf_rate", 12.0) or 12.0)
    pf_base = str(data.get("pf_base_component", "Basic Salary")).strip() or "Basic Salary"
    prof_tax = float(data.get("professional_tax", 200.0) or 0.0)
    other_ded = float(data.get("other_deductions", 0.0) or 0.0)

    # Execute backend calculation engine
    calc_res = calculate_salary_structure(
        monthly_wage=monthly_wage,
        components_data=components_raw,
        employee_pf_rate=employee_pf_rate,
        employer_pf_rate=employer_pf_rate,
        pf_base_component=pf_base,
        professional_tax=prof_tax,
        other_deductions=other_ded,
    )

    template = RoleSalaryTemplate.objects.filter(organization=organization, role=role_val, is_deleted=False).first()
    if not template:
        template = RoleSalaryTemplate(organization=organization, role=role_val)

    template.designation = str(data.get("designation", "")).strip()
    template.wage_type = RoleSalaryTemplate.WAGE_FIXED
    template.monthly_wage = calc_res["monthly_wage"]
    template.yearly_wage = calc_res["yearly_wage"]
    template.employee_pf_rate = calc_res["employee_pf_rate"]
    template.employer_pf_rate = calc_res["employer_pf_rate"]
    template.pf_base_component = calc_res["pf_base_component"]
    template.professional_tax = calc_res["professional_tax"]
    template.other_deductions = calc_res["other_deductions"]
    template.working_days_per_week = int(data.get("working_days_per_week", 5) or 5)

    template.components = [
        SalaryComponent(
            name=c["name"],
            calculation_type=c["calculation_type"],
            value=c["value"],
            depends_on=c["depends_on"],
            is_fixed_allowance_remainder=c["is_fixed_allowance_remainder"],
            calculated_amount=c["calculated_amount"],
        )
        for c in calc_res["components"]
    ]
    template.save()

    # Cascade updates to employees with salary_source == 'ROLE' inheriting this role's template
    role_payrolls = EmployeePayroll.objects.filter(
        organization=organization,
        salary_source=EmployeePayroll.SOURCE_ROLE,
        is_deleted=False,
    )
    for emp_payroll in role_payrolls:
        if emp_payroll.employee and emp_payroll.employee.role == role_val:
            emp_payroll.role_template = template
            emp_payroll.monthly_wage = template.monthly_wage
            emp_payroll.yearly_wage = template.yearly_wage
            emp_payroll.components = template.components
            emp_payroll.employee_pf_rate = template.employee_pf_rate
            emp_payroll.employer_pf_rate = template.employer_pf_rate
            emp_payroll.pf_base_component = template.pf_base_component
            emp_payroll.professional_tax = template.professional_tax
            emp_payroll.other_deductions = template.other_deductions
            emp_payroll.gross_salary = calc_res["gross_salary"]
            emp_payroll.employee_pf_amount = calc_res["employee_pf_amount"]
            emp_payroll.employer_pf_amount = calc_res["employer_pf_amount"]
            emp_payroll.total_deductions = calc_res["total_deductions"]
            emp_payroll.net_salary = calc_res["net_salary"]
            emp_payroll.save()

    return template


# ---------------------------------------------------------------------------
# 2. Employee Payroll Assignments
# ---------------------------------------------------------------------------
def get_employee_payroll(organization, user: User) -> EmployeePayroll:
    """Get payroll record for an employee. Generates default if none exists."""
    payroll = EmployeePayroll.objects.filter(organization=organization, employee=user, is_deleted=False).first()
    if not payroll:
        # Check if role salary template exists for employee's role
        role_tpl = RoleSalaryTemplate.objects.filter(organization=organization, role=user.role, is_deleted=False).first()
        monthly_wage = role_tpl.monthly_wage if role_tpl else 50000.0
        components_data = [c.to_dict() for c in role_tpl.components] if role_tpl else get_default_salary_components(monthly_wage)

        calc_res = calculate_salary_structure(
            monthly_wage=monthly_wage,
            components_data=components_data,
            employee_pf_rate=role_tpl.employee_pf_rate if role_tpl else 12.0,
            employer_pf_rate=role_tpl.employer_pf_rate if role_tpl else 12.0,
            pf_base_component=role_tpl.pf_base_component if role_tpl else "Basic Salary",
            professional_tax=role_tpl.professional_tax if role_tpl else 200.0,
            other_deductions=role_tpl.other_deductions if role_tpl else 0.0,
        )

        payroll = EmployeePayroll(
            organization=organization,
            employee=user,
            salary_source=EmployeePayroll.SOURCE_ROLE,
            role_template=role_tpl,
            wage_type="FIXED_WAGE",
            monthly_wage=calc_res["monthly_wage"],
            yearly_wage=calc_res["yearly_wage"],
            employee_pf_rate=calc_res["employee_pf_rate"],
            employer_pf_rate=calc_res["employer_pf_rate"],
            pf_base_component=calc_res["pf_base_component"],
            professional_tax=calc_res["professional_tax"],
            other_deductions=calc_res["other_deductions"],
            gross_salary=calc_res["gross_salary"],
            employee_pf_amount=calc_res["employee_pf_amount"],
            employer_pf_amount=calc_res["employer_pf_amount"],
            total_deductions=calc_res["total_deductions"],
            net_salary=calc_res["net_salary"],
            components=[
                SalaryComponent(
                    name=c["name"],
                    calculation_type=c["calculation_type"],
                    value=c["value"],
                    depends_on=c["depends_on"],
                    is_fixed_allowance_remainder=c["is_fixed_allowance_remainder"],
                    calculated_amount=c["calculated_amount"],
                )
                for c in calc_res["components"]
            ],
        )
        payroll.save()

    return payroll


def list_all_employee_payrolls(organization):
    """List all employee payroll records in the organization."""
    return EmployeePayroll.objects.filter(organization=organization, is_deleted=False)


def assign_employee_payroll(organization, data: dict) -> EmployeePayroll:
    """Assign or update employee payroll configuration (ROLE or MANUAL source)."""
    require_fields(data, ["employee_id", "salary_source"])
    uid = validate_object_id(data["employee_id"], "employee_id")
    user = User.objects.filter(id=uid, organization=organization, is_deleted=False).first()
    if not user:
        raise ValidationError("Employee not found.", details={"employee_id": "Invalid employee."})

    salary_source = validate_choice(data["salary_source"], EmployeePayroll.SOURCE_CHOICES, "salary_source")

    role_template = None
    if salary_source == EmployeePayroll.SOURCE_ROLE:
        role_template = RoleSalaryTemplate.objects.filter(organization=organization, role=user.role, is_deleted=False).first()
        if not role_template and data.get("role_template_id"):
            tid = validate_object_id(data["role_template_id"], "role_template_id")
            role_template = RoleSalaryTemplate.objects.filter(id=tid, organization=organization, is_deleted=False).first()

        if role_template:
            monthly_wage = role_template.monthly_wage
            components_raw = [c.to_dict() for c in role_template.components]
            employee_pf_rate = role_template.employee_pf_rate
            employer_pf_rate = role_template.employer_pf_rate
            pf_base = role_template.pf_base_component
            prof_tax = role_template.professional_tax
            other_ded = role_template.other_deductions
        else:
            monthly_wage = float(data.get("monthly_wage", 50000.0) or 50000.0)
            components_raw = data.get("components") or get_default_salary_components(monthly_wage)
            employee_pf_rate = float(data.get("employee_pf_rate", 12.0) or 12.0)
            employer_pf_rate = float(data.get("employer_pf_rate", 12.0) or 12.0)
            pf_base = str(data.get("pf_base_component", "Basic Salary")).strip() or "Basic Salary"
            prof_tax = float(data.get("professional_tax", 200.0) or 0.0)
            other_ded = float(data.get("other_deductions", 0.0) or 0.0)
    else:  # MANUAL source
        require_fields(data, ["monthly_wage"])
        monthly_wage = float(data["monthly_wage"])
        components_raw = data.get("components") or get_default_salary_components(monthly_wage)
        employee_pf_rate = float(data.get("employee_pf_rate", 12.0) or 12.0)
        employer_pf_rate = float(data.get("employer_pf_rate", 12.0) or 12.0)
        pf_base = str(data.get("pf_base_component", "Basic Salary")).strip() or "Basic Salary"
        prof_tax = float(data.get("professional_tax", 200.0) or 0.0)
        other_ded = float(data.get("other_deductions", 0.0) or 0.0)

    # Compute breakdown using backend calculation engine
    calc_res = calculate_salary_structure(
        monthly_wage=monthly_wage,
        components_data=components_raw,
        employee_pf_rate=employee_pf_rate,
        employer_pf_rate=employer_pf_rate,
        pf_base_component=pf_base,
        professional_tax=prof_tax,
        other_deductions=other_ded,
    )

    payroll = EmployeePayroll.objects.filter(organization=organization, employee=user, is_deleted=False).first()
    if not payroll:
        payroll = EmployeePayroll(organization=organization, employee=user)

    payroll.salary_source = salary_source
    payroll.role_template = role_template
    payroll.monthly_wage = calc_res["monthly_wage"]
    payroll.yearly_wage = calc_res["yearly_wage"]
    payroll.employee_pf_rate = calc_res["employee_pf_rate"]
    payroll.employer_pf_rate = calc_res["employer_pf_rate"]
    payroll.pf_base_component = calc_res["pf_base_component"]
    payroll.professional_tax = calc_res["professional_tax"]
    payroll.other_deductions = calc_res["other_deductions"]
    payroll.gross_salary = calc_res["gross_salary"]
    payroll.employee_pf_amount = calc_res["employee_pf_amount"]
    payroll.employer_pf_amount = calc_res["employer_pf_amount"]
    payroll.total_deductions = calc_res["total_deductions"]
    payroll.net_salary = calc_res["net_salary"]

    if data.get("effective_from"):
        eff_d = parse_date(data["effective_from"], "effective_from")
        payroll.effective_from = datetime.combine(eff_d, time.min, tzinfo=timezone.utc)

    payroll.components = [
        SalaryComponent(
            name=c["name"],
            calculation_type=c["calculation_type"],
            value=c["value"],
            depends_on=c["depends_on"],
            is_fixed_allowance_remainder=c["is_fixed_allowance_remainder"],
            calculated_amount=c["calculated_amount"],
        )
        for c in calc_res["components"]
    ]
    return payroll.save()


def preview_salary_calculation(data: dict) -> dict:
    """Preview live salary calculation breakdown without persisting to database."""
    require_fields(data, ["monthly_wage"])
    monthly_wage = float(data["monthly_wage"])
    components_raw = data.get("components") or get_default_salary_components(monthly_wage)
    employee_pf_rate = float(data.get("employee_pf_rate", 12.0) or 12.0)
    employer_pf_rate = float(data.get("employer_pf_rate", 12.0) or 12.0)
    pf_base = str(data.get("pf_base_component", "Basic Salary")).strip() or "Basic Salary"
    prof_tax = float(data.get("professional_tax", 200.0) or 0.0)
    other_ded = float(data.get("other_deductions", 0.0) or 0.0)

    return calculate_salary_structure(
        monthly_wage=monthly_wage,
        components_data=components_raw,
        employee_pf_rate=employee_pf_rate,
        employer_pf_rate=employer_pf_rate,
        pf_base_component=pf_base,
        professional_tax=prof_tax,
        other_deductions=other_ded,
    )


# ---------------------------------------------------------------------------
# 3. Payroll Documents
# ---------------------------------------------------------------------------
def list_employee_documents(organization, user: User, document_type: str = None):
    """List payroll documents for signed-in employee."""
    qs = PayrollDocument.objects.filter(organization=organization, employee=user, is_deleted=False)
    if document_type:
        qs = qs.filter(document_type=document_type)
    return qs


def list_admin_documents(organization, employee_id: str = None, document_type: str = None):
    """List payroll documents for admin management."""
    qs = PayrollDocument.objects.filter(organization=organization, is_deleted=False)
    if employee_id:
        uid = validate_object_id(employee_id, "employee_id")
        qs = qs.filter(employee=uid)
    if document_type:
        qs = qs.filter(document_type=document_type)
    return qs


def upload_payroll_document(organization, uploader: User, data: dict, file_obj=None) -> PayrollDocument:
    """Upload a payslip, offer letter, or CTC document for an employee."""
    require_fields(data, ["employee_id", "document_type", "title"])
    if not file_obj:
        raise ValidationError("Payroll document file is required.", details={"file": "This field is required."})

    uid = validate_object_id(data["employee_id"], "employee_id")
    emp = User.objects.filter(id=uid, organization=organization, is_deleted=False).first()
    if not emp:
        raise ValidationError("Employee not found.", details={"employee_id": "Invalid employee."})

    doc_type = validate_choice(data["document_type"], PayrollDocument.DOC_CHOICES, "document_type")
    saved_file, orig_name = _save_attachment_file(file_obj)

    doc = PayrollDocument(
        organization=organization,
        employee=emp,
        document_type=doc_type,
        title=str(data["title"]).strip(),
        payroll_month=str(data.get("payroll_month", "")).strip(),
        payroll_year=int(data.get("payroll_year")) if data.get("payroll_year") else None,
        filename=saved_file,
        original_filename=orig_name,
        uploaded_by=uploader,
    )
    return doc.save()


def get_payroll_document_file(organization, user: User, document_id: str) -> tuple:
    """Retrieve payroll document file path after verifying authorization."""
    did = validate_object_id(document_id, "document_id")
    doc = PayrollDocument.objects.filter(id=did, organization=organization, is_deleted=False).first()
    if not doc or not doc.filename:
        raise NotFound("Payroll document not found.")

    # Permission check: employee owner or admin
    if not user.is_admin and str(doc.employee.id) != str(user.id):
        raise PermissionDenied("You are not authorized to access this payroll document.")

    file_path = ATTACHMENT_DIR / doc.filename
    if not file_path.exists():
        raise NotFound("Document file missing on server.")

    return (file_path, doc.original_filename or doc.filename)


def delete_payroll_document(organization, document_id: str) -> bool:
    """Delete a payroll document."""
    did = validate_object_id(document_id, "document_id")
    doc = PayrollDocument.objects.filter(id=did, organization=organization, is_deleted=False).first()
    if not doc:
        raise NotFound("Payroll document not found.")
    doc.soft_delete()
    return True
