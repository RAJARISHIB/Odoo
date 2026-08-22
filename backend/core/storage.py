"""Uploaded-file store for company logos and avatars.

Files land under `MEDIA_ROOT` (a plain directory, so it can be a Docker volume
in deployment) and are served back at `MEDIA_URL`.  Only the public URL is kept
on the document - nothing binary goes into Mongo.
"""
import uuid
from pathlib import Path

from django.conf import settings

from core.exceptions import ValidationError

MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB


def _sniff_image(head: bytes) -> str:
    """Identify an image by its magic bytes, returning a file extension.

    The declared extension and content type both come from the client, so
    neither is trusted; a renamed executable cannot pass this.  (Written out by
    hand because `imghdr` was removed in Python 3.13.)
    """
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head[:512]):
        return "svg"
    return ""


def save_image(uploaded_file, folder: str, field: str = "logo") -> str:
    """Validate and store an uploaded image, returning its public URL."""
    if not uploaded_file:
        raise ValidationError("No file was uploaded.", details={field: "This field is required."})

    if uploaded_file.size > MAX_IMAGE_BYTES:
        raise ValidationError(
            "File is too large.",
            details={field: "Maximum size is {} MB.".format(MAX_IMAGE_BYTES // (1024 * 1024))},
        )

    head = uploaded_file.read(512)
    uploaded_file.seek(0)

    extension = _sniff_image(head)
    if not extension:
        raise ValidationError(
            "Unsupported file type.",
            details={field: "Upload a PNG, JPEG, GIF, WebP or SVG image."},
        )

    filename = "{}.{}".format(uuid.uuid4().hex, extension)
    directory = Path(settings.MEDIA_ROOT) / folder
    directory.mkdir(parents=True, exist_ok=True)

    with open(directory / filename, "wb") as target:
        for chunk in uploaded_file.chunks():
            target.write(chunk)

    return "{}{}/{}".format(settings.MEDIA_URL, folder, filename)


def absolute_media_url(path: str) -> str:
    """Turn a stored media path into a URL another origin can fetch.

    Values are stored relative ("/media/logos/...") so the database survives a
    host change; callers on a different origin need the full URL.
    """
    if not path:
        return None
    if path.startswith(("http://", "https://", "data:")):
        return path
    return settings.API_PUBLIC_URL.rstrip("/") + "/" + path.lstrip("/")


def delete_file(public_url: str) -> bool:
    """Remove a previously stored file.

    Accepts either form the value can take: the relative path as stored, or the
    absolute URL that `absolute_media_url` handed to a client.
    """
    if not public_url:
        return False

    relative_url = public_url.replace(settings.API_PUBLIC_URL.rstrip("/"), "", 1)
    # Anything outside the media directory is not ours to delete.
    if not relative_url.startswith(settings.MEDIA_URL):
        return False

    relative = relative_url[len(settings.MEDIA_URL):].lstrip("/")
    try:
        (Path(settings.MEDIA_ROOT) / relative).unlink()
        return True
    except OSError:
        return False
