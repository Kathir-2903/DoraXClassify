"""MongoDB `leads` document shape.

`intelligence` is a denormalised roll-up of the lead's meetings, refreshed
after every analysis. Values are only set when supported by stored meeting
data; otherwise they stay null and the UI shows "Not available"."""
from typing import Any, Dict, Optional

from bson import ObjectId

from app.constants.analysis_status import LeadStatus
from app.utils.datetime_utils import utcnow


def empty_intelligence() -> Dict[str, Any]:
    return {
        "meetings_count": 0,
        "completed_meetings": 0,
        "no_shows": 0,
        "total_duration_seconds": 0,
        "average_duration_seconds": None,
        "last_meeting_id": None,
        "last_meeting_at": None,
        "last_meeting_status": None,
        "last_duration_seconds": None,
        "interest_level": None,
        "purchase_intent": None,
        "engagement_level": None,
        "main_concern": None,
        "next_action": None,
        "follow_up_required": False,
        "follow_up_due": None,
        "analysis_status": None,
        "updated_at": None,
    }


def new_lead_document(data: Dict[str, Any], sales_person_id: ObjectId, created_by: ObjectId, is_demo: bool = False) -> Dict[str, Any]:
    now = utcnow()
    return {
        "name": data["name"],
        "email": data["email"],
        "phone": data["phone"],
        "company": data.get("company") or None,
        "lead_source": data.get("lead_source") or None,
        "interested_product": data.get("interested_product") or None,
        "notes": data.get("notes") or None,
        "sales_person_id": sales_person_id,
        "lead_status": LeadStatus.NEW.value,
        "intelligence": empty_intelligence(),
        "journey": [
            {"event": "lead_created", "label": "Lead Created", "at": now, "source": "user"},
        ],
        "is_demo": is_demo,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
        "last_activity_at": now,
    }


def journey_event(event: str, label: str, source: str, meeting_id: Optional[ObjectId] = None, details: Optional[str] = None, at=None) -> Dict[str, Any]:
    return {
        "event": event,
        "label": label,
        "at": at or utcnow(),
        "source": source,
        "meeting_id": meeting_id,
        "details": details,
    }
