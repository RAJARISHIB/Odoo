"""Base mongoengine document every collection inherits from.

Gives all collections the same audit columns, a soft-delete flag, a consistent
`to_dict()` for serialisation and an `active()` queryset helper.
"""
from datetime import datetime, timezone

from bson import ObjectId
from mongoengine import BooleanField, DateTimeField, Document, QuerySet


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SoftDeleteQuerySet(QuerySet):
    def active(self):
        return self.filter(is_deleted=False)


class BaseDocument(Document):
    """Abstract base: audit timestamps + soft delete."""

    created_at = DateTimeField(default=utcnow)
    updated_at = DateTimeField(default=utcnow)
    is_deleted = BooleanField(default=False)
    deleted_at = DateTimeField(null=True)

    meta = {
        "abstract": True,
        "queryset_class": SoftDeleteQuerySet,
        "indexes": ["is_deleted", "created_at"],
    }

    # -- lifecycle ---------------------------------------------------------
    def save(self, *args, **kwargs):
        self.updated_at = utcnow()
        if not self.created_at:
            self.created_at = utcnow()
        return super().save(*args, **kwargs)

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = utcnow()
        self.save()
        return self

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save()
        return self

    # -- serialisation -----------------------------------------------------
    #: Fields never returned by to_dict() - override per document.
    HIDDEN_FIELDS = ()

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        """Convert the document to a JSON-safe dict.

        Reference fields are emitted as plain id strings (organization ->
        organization_id) so the API never leaks a whole nested document by
        accident.
        """
        hidden = set(self.HIDDEN_FIELDS) | set(exclude)
        data = {"id": str(self.id) if self.id else None}

        for name in self._fields_ordered:
            if name in ("id", "_id") or name in hidden:
                continue
            value = getattr(self, name, None)

            if value is None:
                data[name] = None
            elif isinstance(value, Document):
                data[name + "_id"] = str(value.id)
            elif isinstance(value, ObjectId):
                data[name] = str(value)
            elif isinstance(value, datetime):
                data[name] = value.isoformat()
            elif isinstance(value, (list, tuple)):
                data[name] = [
                    str(item.id) if isinstance(item, Document) else item for item in value
                ]
            else:
                data[name] = value

        if not include_deleted_meta:
            data.pop("is_deleted", None)
            data.pop("deleted_at", None)
        return data

    def __str__(self):
        return "<{} {}>".format(self.__class__.__name__, self.id)
