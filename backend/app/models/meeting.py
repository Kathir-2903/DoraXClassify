"""MongoDB `meetings` document shape.

Relationship: Lead ─┬─ Meeting ─┬─ meeting_recordings (1:1, holds the source URL)
                    │           ├─ meeting_transcripts (1:1)
                    │           └─ meeting_analytics (1:N, versioned; one is_current)
The source recording URL lives only in `meeting_recordings` and is never
returned to the browser."""
from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId

from app.constants.analysis_status import NotificationStatus, StageStatus
from app.constants.meeting_status import MeetingState
from app.utils.datetime_utils import utcnow


def new_stage(status: StageStatus = StageStatus.PENDING) -> Dict[str, Any]:
    return {
        "status": status.value,
        "attempt_count": 0,
        "last_attempt_at": None,
        "next_retry_at": None,
        "started_at": None,
        "completed_at": None,
        "error_message": None,
    }


def new_notification_state() -> Dict[str, Any]:
    return {
        "status": NotificationStatus.PENDING.value,
        "sent_at": None,
        "provider": None,
        "provider_message_id": None,
        "error": None,
        "attempt_count": 0,
    }


def new_meeting_document(
    *,
    lead: Dict[str, Any],
    sales_person: Dict[str, Any],
    label: str,
    start_time: datetime,
    end_time: datetime,
    timezone: str,
    min_duration: int,
    idempotency_key: str,
    created_by: ObjectId,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    now = utcnow()
    return {
        "lead_id": lead["_id"],
        "sales_person_id": sales_person["_id"],
        "label": label,
        "notes": notes or "",
        "idempotency_key": idempotency_key,
        "is_demo": False,
        "lead_snapshot": {k: lead.get(k) for k in ("name", "email", "phone", "company", "lead_source", "interested_product")},
        "sales_person_snapshot": {"name": sales_person.get("name"), "email": sales_person.get("email")},
        "classify": {
            "unique_id": None,
            "room_id": None,
            "student_code": None,
            "host_code": None,
            "meeting_type": "scheduled",
            "product": None,
            "student_join_url": None,
            "host_join_url": None,
            "is_mock": False,
            "warning": None,
        },
        "schedule": {
            "start_time": start_time,
            "end_time": end_time,
            "timezone": timezone,
            "duration_minutes": int((end_time - start_time).total_seconds() // 60),
            "min_duration": min_duration,
        },
        "status": {
            "overall": MeetingState.DRAFT.value,
            "meeting_created": False,
            "invitation_sent": False,
            "email_sent": False,
            "lead_joined": False,
            "sales_person_joined": False,
            "meeting_started": False,
            "meeting_completed": False,
            "no_show": False,
            "meeting_data_pending": False,
            "recording_available": False,
            "transcript_available": False,
            "analysis_completed": False,
            "follow_up_required": False,
        },
        "attendance": None,
        "attendance_sync": {"status": "pending", "attempt_count": 0, "last_attempt_at": None, "next_attempt_at": None,
                            "last_message": None, "completed_at": None},
        "processing": {
            "recording": new_stage(),
            "transcript": new_stage(),
            "analysis": new_stage(),
            "active": False,
        },
        "recording": {"status": "pending", "duration_seconds": None, "download_status": "pending", "size_bytes": None},
        "transcript": {"status": "pending", "source": None, "segment_count": 0, "has_speaker_labels": False, "has_timestamps": False},
        "analysis": {"status": "pending", "current_analysis_id": None, "version_count": 0, "snapshot": None},
        "notifications": {"email": new_notification_state()},
        "flags": [],
        "timeline": [],
        "raw_classify_response": None,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
