"""Attendance domain - mongoengine documents mapped to Mongo collections.

Collections
    attendance         : one document per user per calendar day
    attendance_sessions: embedded check-in/check-out pairs within a day
"""
from datetime import datetime, timezone

from mongoengine import (
    BooleanField,
    DateTimeField,
    DictField,
    EmbeddedDocument,
    EmbeddedDocumentListField,
    FloatField,
    IntField,
    ReferenceField,
    StringField,
)

from core.base_model import BaseDocument
from core.constants import AttendanceSource, AttendanceStatus


class WorkSession(EmbeddedDocument):
    """A single check-in/check-out pair.

    Kept as an embedded list so a day can hold several sessions (a lunch break
    splits the day) while still being one document read.
    """

    check_in = DateTimeField(required=True)
    check_out = DateTimeField(null=True)
    source = StringField(choices=AttendanceSource.ALL, default=AttendanceSource.WEB)
    ip_address = StringField(max_length=64)
    user_agent = StringField(max_length=255)
    note = StringField(max_length=300)

    @property
    def is_open(self) -> bool:
        return self.check_out is None

    @property
    def duration_seconds(self) -> int:
        if not self.check_out:
            return 0
        return int((self.check_out - self.check_in).total_seconds())

    def to_dict(self) -> dict:
        return {
            "check_in": self.check_in.isoformat() if self.check_in else None,
            "check_out": self.check_out.isoformat() if self.check_out else None,
            "source": self.source,
            "note": self.note,
            "is_open": self.is_open,
            "duration_seconds": self.duration_seconds,
        }


class Attendance(BaseDocument):
    """One user's attendance for one calendar day.

    `(organization, user, date)` is unique, so check-in/check-out mutate the
    same document instead of creating rows per punch.
    """

    organization = ReferenceField("Organization", required=True)
    user = ReferenceField("User", required=True)

    #: Midnight UTC of the attendance day - the key the UI filters on.
    date = DateTimeField(required=True)
    sessions = EmbeddedDocumentListField(WorkSession, default=list)

    status = StringField(choices=AttendanceStatus.ALL, default=AttendanceStatus.PRESENT)
    first_check_in = DateTimeField(null=True)
    last_check_out = DateTimeField(null=True)
    total_seconds = IntField(default=0)
    overtime_seconds = IntField(default=0)
    late_minutes = IntField(default=0)

    is_manual = BooleanField(default=False)
    approved_by = ReferenceField("User", null=True)
    note = StringField(max_length=500)
    #: Optional geo/device payload captured at punch time.
    location = DictField(default=dict)

    meta = {
        "collection": "attendance",
        "indexes": [
            "organization",
            "user",
            "date",
            "status",
            {"fields": ("organization", "user", "date"), "unique": True},
            ("organization", "date"),
        ],
        "ordering": ["-date"],
    }

    # -- derived -----------------------------------------------------------
    @property
    def open_session(self):
        """The session still running, if the user is currently checked in."""
        for session in self.sessions:
            if session.is_open:
                return session
        return None

    @property
    def is_checked_in(self) -> bool:
        return self.open_session is not None

    @property
    def total_hours(self) -> float:
        return round(self.total_seconds / 3600.0, 2)

    def recalculate(self):
        """Recompute the day roll-ups from the embedded sessions."""
        closed = [s for s in self.sessions if s.check_out]
        self.total_seconds = sum(s.duration_seconds for s in closed)
        if self.sessions:
            self.first_check_in = min(s.check_in for s in self.sessions)
        if closed:
            self.last_check_out = max(s.check_out for s in closed)
        return self

    def to_dict(self, exclude=(), include_deleted_meta: bool = False) -> dict:
        data = super().to_dict(exclude=exclude, include_deleted_meta=include_deleted_meta)
        data["sessions"] = [session.to_dict() for session in self.sessions]
        data["total_hours"] = self.total_hours
        data["is_checked_in"] = self.is_checked_in
        return data

    def __repr__(self):
        return "<Attendance {} {}>".format(self.user_id, self.date)


class AttendanceSummary(BaseDocument):
    """Optional pre-aggregated month roll-up per user.

    Written by a nightly job (not part of this initialisation); the admin
    dashboard reads it when present and falls back to live aggregation.
    """

    organization = ReferenceField("Organization", required=True)
    user = ReferenceField("User", required=True)
    year = IntField(required=True)
    month = IntField(required=True, min_value=1, max_value=12)

    present_days = IntField(default=0)
    absent_days = IntField(default=0)
    late_days = IntField(default=0)
    leave_days = IntField(default=0)
    total_hours = FloatField(default=0.0)
    generated_at = DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "attendance_summaries",
        "indexes": [
            {"fields": ("organization", "user", "year", "month"), "unique": True},
        ],
        "ordering": ["-year", "-month"],
    }
