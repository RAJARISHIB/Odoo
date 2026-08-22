"""MongoDB connection lifecycle.

`connect_mongo()` is called once from `core.apps.CoreConfig.ready()`, so every
mongoengine Document in `apps/*/models.py` is bound to the same connection.
"""
import logging

from django.conf import settings
from mongoengine import connect, disconnect, get_connection
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

DEFAULT_ALIAS = "default"
_connected = False


def connect_mongo(alias: str = DEFAULT_ALIAS):
    """Register the mongoengine connection.  Idempotent and lazy - pymongo does
    not dial the server until the first query, so a missing Mongo will not stop
    Django from booting."""
    global _connected
    if _connected:
        return get_connection(alias)

    conn = connect(
        db=settings.MONGO["DB_NAME"],
        host=settings.MONGO["URI"],
        alias=alias,
        uuidRepresentation="standard",
        serverSelectionTimeoutMS=5000,
        tz_aware=True,
    )
    _connected = True
    logger.info("Mongo connection registered: db=%s", settings.MONGO["DB_NAME"])
    return conn


def disconnect_mongo(alias: str = DEFAULT_ALIAS):
    global _connected
    disconnect(alias=alias)
    _connected = False


def ping() -> dict:
    """Health-check helper used by `GET /api/v1/health`."""
    try:
        connect_mongo()
        get_connection().admin.command("ping")
        return {"status": "up", "database": settings.MONGO["DB_NAME"]}
    except PyMongoError as exc:
        logger.warning("Mongo ping failed: %s", exc)
        return {"status": "down", "database": settings.MONGO["DB_NAME"], "error": str(exc)}
