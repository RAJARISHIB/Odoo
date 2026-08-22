"""Teams domain - mongoengine documents mapped to Mongo collections.

Collections
    teams                 : organization teams
    team_hierarchy_levels : configurable hierarchy levels within a team
    team_members          : employee team memberships and hierarchy assignments
"""
from datetime import datetime, timezone

from mongoengine import (
    BooleanField,
    DateTimeField,
    IntField,
    ReferenceField,
    StringField,
)

from core.base_model import BaseDocument


class Team(BaseDocument):
    """A team inside an organization."""

    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = (STATUS_ACTIVE, STATUS_INACTIVE)

    organization = ReferenceField("Organization", required=True)
    name = StringField(required=True, max_length=150)
    description = StringField(max_length=500, default="")
    status = StringField(choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    meta = {
        "collection": "teams",
        "indexes": [
            "organization",
            "status",
            {"fields": ("organization", "name"), "sparse": True},
        ],
        "ordering": ["name"],
    }

    def __repr__(self):
        return "<Team {}>".format(self.name)


class TeamHierarchyLevel(BaseDocument):
    """A level in a team's hierarchy (e.g. Director, Manager, Lead, Developer, Intern)."""

    team = ReferenceField(Team, required=True)
    name = StringField(required=True, max_length=100)
    order = IntField(required=True, default=1)
    is_active = BooleanField(default=True)

    meta = {
        "collection": "team_hierarchy_levels",
        "indexes": [
            "team",
            "is_active",
            ("team", "order"),
        ],
        "ordering": ["order", "name"],
    }

    def __repr__(self):
        return "<TeamHierarchyLevel {} (Order {})>".format(self.name, self.order)


class TeamMember(BaseDocument):
    """Membership connecting an employee to a team and hierarchy level."""

    organization = ReferenceField("Organization", required=True)
    team = ReferenceField(Team, required=True)
    employee = ReferenceField("User", required=True)
    hierarchy_level = ReferenceField(TeamHierarchyLevel, null=True)
    is_active = BooleanField(default=True)
    joined_at = DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "team_members",
        "indexes": [
            "organization",
            "team",
            "employee",
            "is_active",
            ("team", "employee"),
            ("organization", "employee"),
        ],
        "ordering": ["joined_at"],
    }

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)

        if self.employee:
            user = self.employee
            data["employee"] = {
                "id": str(user.id),
                "full_name": user.full_name,
                "email": user.email,
                "employee_id": user.employee_id,
                "designation": user.designation,
                "avatar_url": user.avatar_url,
                "date_of_birth": user.date_of_birth.strftime("%Y-%m-%d") if user.date_of_birth else None,
            }

        try:
            if self.hierarchy_level:
                level = self.hierarchy_level
                data["hierarchy_level"] = {
                    "id": str(level.id),
                    "name": level.name,
                    "order": level.order,
                }
            else:
                data["hierarchy_level"] = None
        except Exception:
            data["hierarchy_level"] = None

        return data

    def __repr__(self):
        return "<TeamMember {} in {}>".format(self.employee_id, self.team_id)
