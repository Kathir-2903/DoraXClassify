"""Audit trail: who did what to which resource."""
import logging
from typing import Any, Dict, Optional

from app.database.mongodb import Collections, get_db
from app.utils.datetime_utils import utcnow
from app.utils.security import redact
from app.utils.validators import maybe_object_id

logger = logging.getLogger(__name__)


async def log_activity(
    user: Optional[Dict[str, Any]],
    action: str,
    resource: str,
    resource_id: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Never raises: auditing must not break the user's action."""
    try:
        await get_db()[Collections.ACTIVITY_LOGS].insert_one(
            {
                "user_id": user.get("_id") if user else None,
                "user_name": user.get("name") if user else "system",
                "action": action,
                "resource": resource,
                "resource_id": maybe_object_id(resource_id) or resource_id,
                "timestamp": utcnow(),
                "metadata": redact(metadata or {}),
            }
        )
    except Exception:
        logger.exception("audit.write_failed", extra={"action": action, "resource": resource})
