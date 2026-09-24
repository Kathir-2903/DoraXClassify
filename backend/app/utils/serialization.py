"""Convert MongoDB documents into JSON-safe structures for API responses."""
from datetime import datetime
from typing import Any

from bson import ObjectId

from app.utils.datetime_utils import ensure_utc


def serialize(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out["id" if k == "_id" else k] = serialize(v)
        return out
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    return value
