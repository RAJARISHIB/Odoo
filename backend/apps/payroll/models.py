"""Payroll module MongoEngine documents.

Collections
    role_salary_templates : Pre-configured salary structures per Role / Designation
    employee_payrolls     : Assigned employee payrolls (ROLE vs MANUAL sources)
    payroll_documents     : Employee payslips, offer letters, CTC documents
"""
from datetime import datetime, timezone

from mongoengine import (
    BooleanField,
    DateTimeField,
    EmbeddedDocument,
    EmbeddedDocumentListField,
    FloatField,
    IntField,
    ReferenceField,
    StringField,
)

from core.base_model import BaseDocument
from core.constants import Role


class SalaryComponent(EmbeddedDocument):
    """Component of a salary structure (e.g. Basic Salary, HRA, Fixed Allowance)."""

    CALC_PERCENTAGE = "PERCENTAGE"
    CALC_FIXED = "FIXED_AMOUNT"

    CALC_CHOICES = (CALC_PERCENTAGE, CALC_FIXED)

    name = StringField(required=True, max_length=100)
    calculation_type = StringField(choices=CALC_CHOICES, default=CALC_PERCENTAGE)
    value = FloatField(default=0.0)  # e.g., 50.0 (%) or 2918.0 (INR)
    depends_on = StringField(default="WAGE")  # "WAGE" or name of another component, e.g. "Basic Salary"
    is_fixed_allowance_remainder = BooleanField(default=False)
    calculated_amount = FloatField(default=0.0)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "calculation_type": self.calculation_type,
            "value": round(float(self.value or 0), 2),
            "depends_on": self.depends_on or "WAGE",
            "is_fixed_allowance_remainder": bool(self.is_fixed_allowance_remainder),
            "calculated_amount": round(float(self.calculated_amount or 0), 2),
        }


class RoleSalaryTemplate(BaseDocument):
    """Preconfigured salary structure template for an organization Role/Designation."""

    WAGE_FIXED = "FIXED_WAGE"
    WAGE_CHOICES = (WAGE_FIXED,)

    organization = ReferenceField("Organization", required=True)
    role = StringField(choices=Role.CHOICES, required=True)
    designation = StringField(default="")
    wage_type = StringField(choices=WAGE_CHOICES, default=WAGE_FIXED)
    monthly_wage = FloatField(required=True)
    yearly_wage = FloatField(required=True)
    components = EmbeddedDocumentListField(SalaryComponent)

    employee_pf_rate = FloatField(default=12.0)  # %
    employer_pf_rate = FloatField(default=12.0)  # %
    pf_base_component = StringField(default="Basic Salary")
    professional_tax = FloatField(default=200.0)
    other_deductions = FloatField(default=0.0)
    working_days_per_week = IntField(default=5)

    meta = {
        "collection": "role_salary_templates",
        "indexes": [
            ("organization", "role"),
            ("organization", "designation"),
        ],
    }

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)
        data["components"] = [c.to_dict() for c in (self.components or [])]
        data["monthly_wage"] = round(float(self.monthly_wage or 0), 2)
        data["yearly_wage"] = round(float(self.yearly_wage or 0), 2)
        return data


class EmployeePayroll(BaseDocument):
    """Assigned payroll record for an individual employee (ROLE or MANUAL source)."""

    SOURCE_ROLE = "ROLE"
    SOURCE_MANUAL = "MANUAL"
    SOURCE_CHOICES = (SOURCE_ROLE, SOURCE_MANUAL)

    organization = ReferenceField("Organization", required=True)
    employee = ReferenceField("User", required=True, unique=True)
    salary_source = StringField(choices=SOURCE_CHOICES, default=SOURCE_ROLE)
    role_template = ReferenceField(RoleSalaryTemplate, null=True)

    wage_type = StringField(default="FIXED_WAGE")
    monthly_wage = FloatField(required=True)
    yearly_wage = FloatField(required=True)
    components = EmbeddedDocumentListField(SalaryComponent)

    employee_pf_rate = FloatField(default=12.0)
    employer_pf_rate = FloatField(default=12.0)
    pf_base_component = StringField(default="Basic Salary")
    professional_tax = FloatField(default=200.0)
    other_deductions = FloatField(default=0.0)

    gross_salary = FloatField(default=0.0)
    total_deductions = FloatField(default=0.0)
    net_salary = FloatField(default=0.0)
    employee_pf_amount = FloatField(default=0.0)
    employer_pf_amount = FloatField(default=0.0)

    effective_from = DateTimeField(default=lambda: datetime.now(timezone.utc))
    is_active = BooleanField(default=True)

    meta = {
        "collection": "employee_payrolls",
        "indexes": [
            "organization",
            "employee",
            "salary_source",
        ],
    }

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)
        if self.employee:
            data["employee"] = {
                "id": str(self.employee.id),
                "full_name": self.employee.full_name,
                "email": self.employee.email,
                "employee_id": self.employee.employee_id,
                "designation": self.employee.designation,
                "role": self.employee.role,
            }
        data["components"] = [c.to_dict() for c in (self.components or [])]
        data["monthly_wage"] = round(float(self.monthly_wage or 0), 2)
        data["yearly_wage"] = round(float(self.yearly_wage or 0), 2)
        data["gross_salary"] = round(float(self.gross_salary or 0), 2)
        data["total_deductions"] = round(float(self.total_deductions or 0), 2)
        data["net_salary"] = round(float(self.net_salary or 0), 2)
        data["employee_pf_amount"] = round(float(self.employee_pf_amount or 0), 2)
        data["employer_pf_amount"] = round(float(self.employer_pf_amount or 0), 2)
        if self.effective_from:
            data["effective_from"] = self.effective_from.strftime("%Y-%m-%d")
        return data


class PayrollDocument(BaseDocument):
    """Employee payroll document (Payslip, Offer Letter, CTC Details, Salary Revision)."""

    DOC_PAYSLIP = "PAYSLIP"
    DOC_OFFER_LETTER = "OFFER_LETTER"
    DOC_CTC_DETAILS = "CTC_DETAILS"
    DOC_REVISION_LETTER = "REVISION_LETTER"
    DOC_OTHER = "OTHER"

    DOC_CHOICES = (
        DOC_PAYSLIP,
        DOC_OFFER_LETTER,
        DOC_CTC_DETAILS,
        DOC_REVISION_LETTER,
        DOC_OTHER,
    )

    organization = ReferenceField("Organization", required=True)
    employee = ReferenceField("User", required=True)

    document_type = StringField(choices=DOC_CHOICES, required=True)
    title = StringField(required=True, max_length=200)
    payroll_month = StringField(default="")  # e.g., "2026-08"
    payroll_year = IntField(null=True)  # e.g., 2026

    # Stored in attachment_assets/
    filename = StringField(required=True, max_length=255)
    original_filename = StringField(required=True, max_length=255)
    uploaded_by = ReferenceField("User", required=True)

    meta = {
        "collection": "payroll_documents",
        "indexes": [
            "organization",
            "employee",
            "document_type",
            "payroll_year",
        ],
        "ordering": ["-created_at"],
    }

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)
        if self.employee:
            data["employee"] = {
                "id": str(self.employee.id),
                "full_name": self.employee.full_name,
                "email": self.employee.email,
                "employee_id": self.employee.employee_id,
            }
        if self.uploaded_by:
            data["uploaded_by"] = {
                "id": str(self.uploaded_by.id),
                "full_name": self.uploaded_by.full_name,
            }
        return data
