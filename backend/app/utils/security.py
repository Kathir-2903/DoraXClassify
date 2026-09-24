"""Password hashing, JWT handling, webhook signature checks and log redaction."""
import hashlib
import hmac
import re
from datetime import timedelta
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.config.settings import settings
from app.utils.datetime_utils import utcnow

# bcrypt only uses the first 72 bytes; pre-hash to keep long passphrases intact.
def _prehash(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, role: str, extra: Optional[Dict[str, Any]] = None) -> str:
    now = utcnow()
    payload = {
        "sub": subject,
        "role": role,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_media_token(user_id: str, meeting_id: str) -> str:
    """Short-lived token that authorises streaming one meeting's recording.

    <video> elements cannot send Authorization headers, so the backend issues
    a scoped token instead of ever exposing the underlying S3 URL."""
    now = utcnow()
    payload = {
        "sub": user_id,
        "typ": "media",
        "mid": meeting_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.media_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str = "access") -> Dict[str, Any]:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def compute_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_webhook(body: bytes, api_key_header: Optional[str], signature_header: Optional[str]) -> bool:
    """Accept either the documented shared `api-key` header or an HMAC signature."""
    secret = settings.webhook_secret
    if not secret:
        # Unsigned webhooks are only tolerated outside production.
        return not settings.is_production
    if api_key_header and hmac.compare_digest(api_key_header.strip(), secret):
        return True
    if signature_header:
        provided = signature_header.strip()
        if provided.lower().startswith("sha256="):
            provided = provided[7:]
        return hmac.compare_digest(provided.lower(), compute_signature(body, secret))
    return False


_SENSITIVE_KEYS = re.compile(
    r"(authtoken|auth_token|authorization|api[-_]?key|password|secret|token|access[-_]?key|signature)", re.I
)


def redact(value: Any) -> Any:
    """Recursively mask secrets before anything is logged or returned to clients."""
    if isinstance(value, dict):
        return {k: ("***" if _SENSITIVE_KEYS.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value
