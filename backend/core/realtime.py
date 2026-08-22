"""Django -> Express bridge.

Django never holds websocket connections itself.  When something happens that a
connected UI should know about, a controller calls one of the helpers below,
which POSTs to the Express hub's internal publish endpoint; the hub fans the
message out to the sockets subscribed to that channel.

    Django  --HTTP POST /internal/publish (x-internal-key)-->  Express  --WS-->  Angular

Delivery is best-effort by design: if the hub is down the API call still
succeeds and the failure is logged.  Never let a notification break a write.
"""
import logging
import uuid
from datetime import datetime, timezone

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Channel naming - must match `realtime/src/lib/channels.js`
# ---------------------------------------------------------------------------
def user_channel(user_id) -> str:
    return "user:{}".format(user_id)


def org_channel(org_id) -> str:
    return "org:{}".format(org_id)


def role_channel(org_id, role) -> str:
    return "org:{}:role:{}".format(org_id, role)


def panel_channel(org_id, panel) -> str:
    """`panel` is 'admin' or 'user' - lets you target a whole panel's screens."""
    return "org:{}:panel:{}".format(org_id, panel)


BROADCAST_CHANNEL = "broadcast"


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------
import threading


def _do_publish(url, message, headers, timeout):
    try:
        response = requests.post(url, json=message, headers=headers, timeout=timeout)
        if response.status_code >= 400:
            logger.warning("Realtime publish rejected (%s): %s", response.status_code, response.text[:200])
    except Exception as exc:
        logger.warning("Realtime hub unreachable (%s): %s", url, exc)


def publish(channels, event: str, payload: dict = None, *, actor_id=None) -> bool:
    """Send one event to one or more channels asynchronously."""
    if not settings.REALTIME["ENABLED"]:
        return False

    if isinstance(channels, str):
        channels = [channels]

    message = {
        "id": uuid.uuid4().hex,
        "event": event,
        "channels": list(channels),
        "payload": payload or {},
        "actor_id": str(actor_id) if actor_id else None,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "source": "django",
    }

    url = settings.REALTIME["HTTP_URL"].rstrip("/") + "/internal/publish"
    headers = {
        "Content-Type": "application/json",
        "x-internal-key": settings.REALTIME["INTERNAL_API_KEY"],
    }
    threading.Thread(
        target=_do_publish,
        args=(url, message, headers, 1),
        daemon=True,
    ).start()
    return True


def notify_user(user_id, event: str, payload: dict = None, *, actor_id=None) -> bool:
    """Deliver to every socket a single user has open."""
    return publish(user_channel(user_id), event, payload, actor_id=actor_id)


def notify_org(org_id, event: str, payload: dict = None, *, actor_id=None) -> bool:
    return publish(org_channel(org_id), event, payload, actor_id=actor_id)


def notify_admins(org_id, event: str, payload: dict = None, *, actor_id=None) -> bool:
    """Deliver to the admin panel screens of one organization."""
    from core.constants import Panel

    return publish(panel_channel(org_id, Panel.ADMIN), event, payload, actor_id=actor_id)


def broadcast(event: str, payload: dict = None, *, actor_id=None) -> bool:
    return publish(BROADCAST_CHANNEL, event, payload, actor_id=actor_id)


def hub_health() -> dict:
    """Ask the hub how it is doing - surfaced by `GET /api/v1/health`."""
    url = settings.REALTIME["HTTP_URL"].rstrip("/") + "/health"
    try:
        response = requests.get(url, timeout=settings.REALTIME["TIMEOUT_SECONDS"])
        if response.ok:
            return {"status": "up", **response.json()}
        return {"status": "down", "http_status": response.status_code}
    except requests.RequestException as exc:
        return {"status": "down", "error": str(exc)}
