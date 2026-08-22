"""Thin wrapper over Django's built-in email framework.

No new dependency: `django.core.mail` ships with Django.  In development
(`EMAIL_HOST` unset) it prints to the console via `EMAIL_BACKEND`; the same
call sends real SMTP mail the moment `EMAIL_HOST`/credentials are set in
`.env` - see `hrms/settings.py`.
"""
import logging

from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send(to_email: str, subject: str, body: str) -> None:
    """Best-effort send - a broken mail server must never break the request
    that triggered it (e.g. `forgot_password` still returns its generic
    success message either way)."""
    try:
        send_mail(subject, body, None, [to_email], fail_silently=False)
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
