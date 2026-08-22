"""Lightweight Mongo-backed rate limiting.

No Redis: a `ThrottleBucket` collection with a `window_expires_at` TTL index
does the same job `RefreshToken.expires_at` already does for sessions -
exhausted buckets clean themselves up on their own.  Good enough for login
throttling / abuse protection without adding new infrastructure.
"""
from datetime import datetime, timedelta, timezone

from mongoengine import DateTimeField, Document, IntField, StringField
from mongoengine.errors import NotUniqueError

from core.exceptions import TooManyRequests


class ThrottleBucket(Document):
    """One row per `(scope, key)` sliding window, e.g. scope="login",
    key="<ip>:<identifier>"."""

    scope = StringField(required=True, max_length=64)
    key = StringField(required=True, max_length=255)
    count = IntField(default=0)
    window_expires_at = DateTimeField(required=True)

    meta = {
        "collection": "throttle_buckets",
        "indexes": [
            {"fields": ("scope", "key"), "unique": True},
            {"fields": ["window_expires_at"], "expireAfterSeconds": 0},
        ],
    }


def check_and_increment(scope: str, key: str, *, limit: int, window_seconds: int) -> None:
    """Raise `TooManyRequests` once `key` has been seen more than `limit`
    times inside the current `window_seconds` window; otherwise record this
    attempt and return.
    """
    now = datetime.now(timezone.utc)

    # Atomic increment of an already-open window.
    bucket = ThrottleBucket.objects(scope=scope, key=key, window_expires_at__gt=now).modify(
        upsert=False, new=True, inc__count=1
    )

    if bucket is None:
        # No open window (first attempt, or the previous one expired) - start
        # a fresh one. A concurrent request racing to do the same thing is
        # rare and harmless: the loser just retries the increment above.
        try:
            ThrottleBucket.objects(scope=scope, key=key).update_one(
                upsert=True,
                set__count=1,
                set__window_expires_at=now + timedelta(seconds=window_seconds),
            )
        except NotUniqueError:
            ThrottleBucket.objects(scope=scope, key=key, window_expires_at__gt=now).modify(
                upsert=False, inc__count=1
            )
        return

    if bucket.count > limit:
        retry_after = max(int((bucket.window_expires_at - now).total_seconds()), 1)
        raise TooManyRequests(
            "Too many attempts. Try again in {} seconds.".format(retry_after),
            code="rate_limited",
            details={"retry_after_seconds": retry_after},
        )


def reset(scope: str, key: str) -> None:
    """Clear a bucket early, e.g. after a successful login."""
    ThrottleBucket.objects(scope=scope, key=key).delete()
