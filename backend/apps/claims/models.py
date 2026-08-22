"""Claims, Fines, and Employee Requests domain - MongoEngine documents.

Collections
    expense_claims    : employee reimbursement expense claims
    fines             : fines applied by admin to employees
    employee_requests : generic employee requests (ID Card, Laptop, Other)
"""
from datetime import datetime, timezone

from mongoengine import (
    DateTimeField,
    FloatField,
    ReferenceField,
    StringField,
)

from core.base_model import BaseDocument


class ExpenseClaim(BaseDocument):
    """Expense claim submitted by an employee for business expenses."""

    TYPE_TRAVEL = "Travel"
    TYPE_FOOD = "Food"
    TYPE_ACCOMMODATION = "Accommodation"
    TYPE_TRANSPORTATION = "Transportation"
    TYPE_OTHER = "Other"

    TYPE_CHOICES = (
        TYPE_TRAVEL,
        TYPE_FOOD,
        TYPE_ACCOMMODATION,
        TYPE_TRANSPORTATION,
        TYPE_OTHER,
    )

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = (
        STATUS_PENDING,
        STATUS_APPROVED,
        STATUS_REJECTED,
    )

    organization = ReferenceField("Organization", required=True)
    employee = ReferenceField("User", required=True)

    expense_type = StringField(required=True, choices=TYPE_CHOICES)
    other_type_description = StringField(max_length=250, default="")
    amount = FloatField(required=True)
    expense_date = DateTimeField(required=True)
    description = StringField(required=True, max_length=500)

    # Local receipt file stored in attachment_assets/
    receipt_filename = StringField(max_length=255, default="")
    receipt_original_name = StringField(max_length=255, default="")

    status = StringField(choices=STATUS_CHOICES, default=STATUS_PENDING)
    admin_comment = StringField(max_length=500, default="")
    processed_by = ReferenceField("User", null=True)
    processed_at = DateTimeField(null=True)

    meta = {
        "collection": "expense_claims",
        "indexes": [
            "organization",
            "employee",
            "status",
            "expense_type",
            "expense_date",
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
                "designation": self.employee.designation,
                "avatar_url": self.employee.avatar_url,
            }
        if self.expense_date:
            data["expense_date"] = self.expense_date.strftime("%Y-%m-%d")
        if self.processed_by:
            data["processed_by"] = {
                "id": str(self.processed_by.id),
                "full_name": self.processed_by.full_name,
            }
        data["has_receipt"] = bool(self.receipt_filename)
        return data


class Fine(BaseDocument):
    """Fine applied to an employee by an admin."""

    STATUS_ACTIVE = "ACTIVE"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = (STATUS_ACTIVE, STATUS_CANCELLED)

    organization = ReferenceField("Organization", required=True)
    employee = ReferenceField("User", required=True)
    amount = FloatField(required=True)
    reason = StringField(required=True, max_length=500)
    date = DateTimeField(required=True)
    status = StringField(choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    applied_by = ReferenceField("User", required=True)

    meta = {
        "collection": "fines",
        "indexes": [
            "organization",
            "employee",
            "status",
            "date",
        ],
        "ordering": ["-date"],
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
        if self.applied_by:
            data["applied_by"] = {
                "id": str(self.applied_by.id),
                "full_name": self.applied_by.full_name,
            }
        if self.date:
            data["date"] = self.date.strftime("%Y-%m-%d")
        return data


class EmployeeRequest(BaseDocument):
    """Generic request submitted by an employee (ID Card, Laptop, Other)."""

    TYPE_ID_CARD = "id_card"
    TYPE_LAPTOP = "laptop"
    TYPE_OTHER = "other"

    TYPE_CHOICES = (
        TYPE_ID_CARD,
        TYPE_LAPTOP,
        TYPE_OTHER,
    )

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = (
        STATUS_PENDING,
        STATUS_APPROVED,
        STATUS_REJECTED,
    )

    organization = ReferenceField("Organization", required=True)
    employee = ReferenceField("User", required=True)

    # Strictly single-select request type
    request_type = StringField(required=True, choices=TYPE_CHOICES)
    description = StringField(required=True, max_length=1000)

    # Attachment stored in attachment_assets/
    attachment_filename = StringField(max_length=255, default="")
    attachment_original_name = StringField(max_length=255, default="")

    status = StringField(choices=STATUS_CHOICES, default=STATUS_PENDING)
    rejection_reason = StringField(max_length=500, default="")
    processed_by = ReferenceField("User", null=True)
    processed_at = DateTimeField(null=True)

    meta = {
        "collection": "employee_requests",
        "indexes": [
            "organization",
            "employee",
            "status",
            "request_type",
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
                "designation": self.employee.designation,
                "avatar_url": self.employee.avatar_url,
            }
        if self.processed_by:
            data["processed_by"] = {
                "id": str(self.processed_by.id),
                "full_name": self.processed_by.full_name,
            }
        data["has_attachment"] = bool(self.attachment_filename)
        return data
