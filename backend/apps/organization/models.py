"""Organization domain - mongoengine documents mapped to Mongo collections.

Collections
    organizations : one tenant (a company) per document
    departments   : org sub-units employees are assigned to
"""
from mongoengine import (
    BooleanField,
    DictField,
    EmailField,
    IntField,
    ListField,
    ReferenceField,
    StringField,
)

from core.base_model import BaseDocument
from core.storage import absolute_media_url


class Organization(BaseDocument):
    """A tenant.  Every other document hangs off one of these."""

    name = StringField(required=True, max_length=150)
    slug = StringField(required=True, unique=True, max_length=150)
    #: Two-letter prefix of every login ID issued here ("Odoo India" -> "OI").
    #: Set once at signup; changing it would orphan existing login IDs.
    code = StringField(required=True, unique=True, max_length=4)
    #: Public URL of the uploaded logo - see `core.storage`.
    logo_url = StringField(max_length=500)
    email = EmailField(required=True)
    phone = StringField(max_length=25)
    website = StringField(max_length=200)

    address_line1 = StringField(max_length=200)
    address_line2 = StringField(max_length=200)
    city = StringField(max_length=100)
    state = StringField(max_length=100)
    country = StringField(max_length=100, default="India")
    postal_code = StringField(max_length=20)

    timezone = StringField(default="Asia/Kolkata", max_length=64)
    #: Working-hours policy the attendance module reads when marking late/half-day.
    work_start_time = StringField(default="09:30", max_length=5)   # HH:MM, org-local
    work_end_time = StringField(default="18:30", max_length=5)
    full_day_hours = IntField(default=8)
    half_day_hours = IntField(default=4)
    late_grace_minutes = IntField(default=15)
    #: 0 = Monday ... 6 = Sunday
    working_days = ListField(IntField(), default=lambda: [0, 1, 2, 3, 4])

    is_active = BooleanField(default=True)
    #: Free-form feature flags / preferences, merged with `core.utils.deep_merge`.
    settings = DictField(default=dict)

    meta = {
        "collection": "organizations",
        "indexes": ["slug", "code", "name", "is_active"],
        "ordering": ["name"],
    }

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)
        # Stored relative, served absolute - the UI runs on another origin.
        data["logo_url"] = absolute_media_url(self.logo_url)
        return data

    def __repr__(self):
        return "<Organization {}>".format(self.name)


class Department(BaseDocument):
    """A team inside an organization."""

    organization = ReferenceField(Organization, required=True)
    name = StringField(required=True, max_length=120)
    code = StringField(max_length=30)
    description = StringField(max_length=500)
    #: Set to a User id; declared as a string ref to avoid a circular import.
    head = ReferenceField("User", null=True)
    is_active = BooleanField(default=True)

    meta = {
        "collection": "departments",
        "indexes": [
            "organization",
            {"fields": ("organization", "name"), "unique": True, "sparse": True},
        ],
        "ordering": ["name"],
    }

    def __repr__(self):
        return "<Department {}>".format(self.name)
