"""MongoDB `users` document shape."""
from typing import Any, Dict, Optional

from app.utils.datetime_utils import utcnow
from app.utils.security import hash_password


def new_user_document(name: str, email: str, password: str, role: str, title: Optional[str] = None, is_demo: bool = False) -> Dict[str, Any]:
    now = utcnow()
    return {
        "name": name,
        "email": email.lower(),
        "password_hash": hash_password(password),
        "role": role,
        "title": title,
        "is_active": True,
        "is_demo": is_demo,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }


def public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(user["_id"]),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "sales"),
        "title": user.get("title"),
        "is_active": user.get("is_active", True),
    }
