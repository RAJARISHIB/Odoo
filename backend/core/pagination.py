"""Uniform list pagination for every collection endpoint."""
from django.conf import settings


def paginate(queryset, page: int = 1, page_size: int = None, serializer=None) -> tuple:
    """Slice a mongoengine queryset.

    Returns `(items, meta)`, where `meta` carries everything the Angular tables
    need to render a pager.
    """
    default_size = settings.API["DEFAULT_PAGE_SIZE"]
    max_size = settings.API["MAX_PAGE_SIZE"]

    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or default_size), 1), max_size)

    total = queryset.count()
    start = (page - 1) * page_size
    items = list(queryset.skip(start).limit(page_size))

    if serializer:
        items = [serializer(item) for item in items]

    total_pages = (total + page_size - 1) // page_size if total else 0
    meta = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }
    return items, meta
