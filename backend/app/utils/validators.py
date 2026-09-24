"""Input normalisation and validation helpers."""
import re
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from email_validator import EmailNotValidError, validate_email

_PHONE_CLEAN = re.compile(r"[\s\-().]")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_email(email: str) -> str:
    try:
        return validate_email(email.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError(f"Invalid email address: {exc}") from exc


def is_valid_email(email: str) -> bool:
    try:
        normalize_email(email)
        return True
    except ValueError:
        return False


def normalize_phone(phone: str, default_country_code: str = "+91") -> str:
    """Normalise to E.164. Ten-digit numbers are assumed to be Indian mobiles."""
    cleaned = _PHONE_CLEAN.sub("", phone or "")
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        if len(cleaned) == 10:
            cleaned = default_country_code + cleaned
        elif len(cleaned) == 12 and cleaned.startswith("91"):
            cleaned = "+" + cleaned
        else:
            cleaned = "+" + cleaned
    if not _E164.match(cleaned):
        raise ValueError("Phone number must be a valid international number, e.g. +919876543210")
    return cleaned


def to_object_id(value: str, field: str = "id") -> ObjectId:
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError) as exc:
        raise ValueError(f"Invalid {field}") from exc


def maybe_object_id(value: Optional[str]) -> Optional[ObjectId]:
    if not value:
        return None
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return None
