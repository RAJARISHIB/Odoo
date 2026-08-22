"""Append-only security audit trail.

Distinct from ordinary application logging (`core.middleware`'s per-request
log line, meant for debugging): this is the queryable, structured record of
who did what to what, for accountability. There is deliberately no update or
delete path anywhere in this module or `apps.users.controllers.AuditController`
- the only way an `AuditLog` document changes after creation is a controlled
administrative process run directly against the database, never through the
API. `AuditLog` inherits `BaseDocument` for the same created_at/`to_dict()`
conventions every other collection uses; its `soft_delete()`/`restore()`
methods exist on the class but are never called anywhere in this codebase.
"""
import logging

from mongoengine import DictField, ReferenceField, StringField

from core.base_model import BaseDocument

logger = logging.getLogger(__name__)


class AuditLog(BaseDocument):
    organization = ReferenceField("Organization", null=True)
    actor = ReferenceField("User", null=True)
    #: Denormalised at write time - the actor's role *then*, even if it
    #: changes (or the account is later deleted) afterwards.
    actor_role = StringField(max_length=32, default="")
    action = StringField(required=True, max_length=64)
    resource_type = StringField(max_length=64, default="")
    resource_id = StringField(max_length=64, default="")
    result = StringField(default="success", max_length=16)
    ip_address = StringField(max_length=64, default="")
    user_agent = StringField(max_length=255, default="")
    #: Small, pre-built dicts only (ids, enums, counts) - never a raw request
    #: body, and never a password/token/MFA secret/recovery code. Every
    #: `record()` call site below builds this by hand for exactly that reason.
    metadata = DictField(default=dict)

    meta = {
        "collection": "audit_logs",
        "indexes": [
            "organization", "actor", "action",
            {"fields": ("organization", "-created_at")},
        ],
        "ordering": ["-created_at"],
    }

    def __repr__(self):
        return "<AuditLog {} ({})>".format(self.action, self.result)


def record(*, action: str, actor=None, actor_role: str = "", organization=None,
          resource_type: str = "", resource_id="", result: str = "success",
          ip_address: str = "", user_agent: str = "", metadata: dict = None) -> None:
    """Write one audit event.  Never raises - a logging failure must not
    break the request that triggered it (mirrors `core.mailer.send`)."""
    try:
        AuditLog(
            organization=organization or (actor.organization if actor else None),
            actor=actor,
            actor_role=actor_role or (actor.role if actor else ""),
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else "",
            result=result,
            ip_address=ip_address or "",
            user_agent=(user_agent or "")[:255],
            metadata=metadata or {},
        ).save()
    except Exception:
        logger.exception("Failed to write audit log for action=%s", action)
