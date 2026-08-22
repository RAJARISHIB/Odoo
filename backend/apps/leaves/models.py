"""Leaves domain - mongoengine documents mapped to Mongo collections.

Collections
    holidays       : government and organization holidays
    leave_requests : employee leave applications
"""
from datetime import datetime, timezone

from mongoengine import (
    BooleanField,
    DateTimeField,
    ReferenceField,
    StringField,
)

from core.base_model import BaseDocument


class Holiday(BaseDocument):
    """A government or organization holiday."""

    TYPE_GOVERNMENT = "government"
    TYPE_ORGANIZATION = "organization"
    TYPE_CHOICES = (TYPE_GOVERNMENT, TYPE_ORGANIZATION)

    organization = ReferenceField("Organization", required=True)
    name = StringField(required=True, max_length=150)
    date = DateTimeField(required=True)
    type = StringField(required=True, choices=TYPE_CHOICES, default=TYPE_GOVERNMENT)
    description = StringField(max_length=500, default="")
    is_active = BooleanField(default=True)

    meta = {
        "collection": "holidays",
        "indexes": [
            "organization",
            "date",
            "type",
            "is_active",
            {"fields": ("organization", "date"), "unique": True},
        ],
        "ordering": ["date"],
    }

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)
        if self.date:
            data["date"] = self.date.strftime("%Y-%m-%d")
        return data

    def __repr__(self):
        return "<Holiday {} ({}) {}>".format(self.name, self.type, self.date)


class LeaveRequest(BaseDocument):
    """An employee's leave request."""

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_CANCELLED)

    organization = ReferenceField("Organization", required=True)
    employee = ReferenceField("User", required=True)

    start_date = DateTimeField(required=True)
    end_date = DateTimeField(required=True)
    reason = StringField(required=True, max_length=1000)
    status = StringField(required=True, choices=STATUS_CHOICES, default=STATUS_PENDING)

    meta = {
        "collection": "leave_requests",
        "indexes": [
            "organization",
            "employee",
            "start_date",
            "end_date",
            "status",
            ("organization", "employee", "start_date"),
        ],
        "ordering": ["-created_at"],
    }

    @property
    def total_days(self) -> int:
        """Inclusive count of calendar days in the request."""
        if not self.start_date or not self.end_date:
            return 0
        delta = (self.end_date.date() - self.start_date.date()).days
        return max(1, delta + 1)

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)
        if self.start_date:
            data["start_date"] = self.start_date.strftime("%Y-%m-%d")
        if self.end_date:
            data["end_date"] = self.end_date.strftime("%Y-%m-%d")
        data["total_days"] = self.total_days
        return data

    def __repr__(self):
        return "<LeaveRequest {} {} to {} ({})>".format(
            self.employee_id, self.start_date, self.end_date, self.status
        )
