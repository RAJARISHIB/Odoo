"""Every endpoint answers with the same envelope so the Angular client only
ever needs one response shape:

    {"success": true,  "data": {...}, "message": "...", "meta": {...}}
    {"success": false, "error": {"code": "...", "message": "...", "details": {...}}}
"""
import json
from datetime import date, datetime
from decimal import Decimal

from bson import ObjectId
from django.http import JsonResponse


class ApiJSONEncoder(json.JSONEncoder):
    """Serialises the types Mongo documents actually contain."""

    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return super().default(obj)


def _envelope(payload: dict, status: int) -> JsonResponse:
    return JsonResponse(payload, status=status, encoder=ApiJSONEncoder, safe=False)


def success(data=None, message: str = None, meta: dict = None, status: int = 200) -> JsonResponse:
    payload = {"success": True, "data": data}
    if message:
        payload["message"] = message
    if meta:
        payload["meta"] = meta
    return _envelope(payload, status)


def created(data=None, message: str = "Created successfully.") -> JsonResponse:
    return success(data=data, message=message, status=201)


def error(message: str, *, code: str = "bad_request", details=None, status: int = 400) -> JsonResponse:
    payload = {"success": False, "error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return _envelope(payload, status)


def from_exception(exc) -> JsonResponse:
    """Render an `ApiError` into the error envelope."""
    return _envelope({"success": False, "error": exc.to_dict()}, exc.status_code)
