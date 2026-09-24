"""MongoDB `webhook_events` document shape."""
from typing import Any, Dict, Optional

from app.utils.datetime_utils import utcnow


def new_webhook_event(event_id: str, payload: Dict[str, Any], source: str, unique_id: Optional[str], headers: Dict[str, str]) -> Dict[str, Any]:
    return {
        "event_id": event_id,
        "source": source,
        "classify_unique_id": unique_id,
        "meeting_id": None,
        "received_at": utcnow(),
        "payload": payload,
        "headers": headers,
        "processed": False,
        "processing_status": "pending",
        "attempt_count": 0,
        "processed_at": None,
        "error_message": None,
    }
