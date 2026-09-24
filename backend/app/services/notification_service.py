"""Email invitation delivery with persisted state and retries.

A delivery failure never fails the meeting: the meeting stays scheduled and
the email is marked `failed`, retried by the worker up to
MAX_RETRY_ATTEMPTS, and can be resent manually."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from bson import ObjectId

from app.config.settings import settings
from app.constants.analysis_status import NotificationStatus
from app.constants.meeting_status import MeetingState
from app.database.mongodb import Collections, get_db
from app.services import email_service
from app.services.email_service import InvitationContent
from app.services.meeting_state import refresh_flags, timeline_event, transition
from app.utils.datetime_utils import format_local, humanize_duration, utcnow

logger = logging.getLogger(__name__)

CHANNEL = "email"


def build_invitation(meeting: Dict[str, Any]) -> InvitationContent:
    sched = meeting["schedule"]
    tz = sched.get("timezone") or settings.default_timezone
    lead = meeting["lead_snapshot"]
    return InvitationContent(
        lead_name=lead.get("name") or "there",
        sales_person=meeting["sales_person_snapshot"].get("name") or "our team",
        date_text=format_local(sched["start_time"], "%A, %d %B %Y", tz),
        time_text=f'{format_local(sched["start_time"], "%I:%M %p", tz)} ({tz})',
        duration_text=humanize_duration(sched["duration_minutes"] * 60),
        join_url=meeting["classify"].get("student_join_url"),
        lead_email=lead.get("email") or "",
        label=meeting.get("label") or "Sales Discussion",
    )


async def send_email(meeting_id: ObjectId, triggered_by: Optional[Dict[str, Any]] = None,
                     force: bool = False) -> Dict[str, Any]:
    """Send the email invitation and persist the outcome on the meeting and
    in the `notifications` collection."""
    db = get_db()
    meeting = await db[Collections.MEETINGS].find_one({"_id": meeting_id})
    if not meeting:
        raise ValueError("Meeting not found")
    state = meeting["notifications"][CHANNEL]
    if state.get("status") in (NotificationStatus.SENT.value, NotificationStatus.DELIVERED.value) and not force:
        return state

    now = utcnow()
    attempts = int(state.get("attempt_count") or 0) + 1
    result = await email_service.send_meeting_invitation(build_invitation(meeting))

    if result.success:
        new_state = {
            "status": NotificationStatus.SENT.value,
            "sent_at": now,
            "provider": result.provider,
            "provider_message_id": result.provider_message_id,
            "error": None,
            "attempt_count": attempts,
            "last_attempt_at": now,
            "next_retry_at": None,
        }
        event = timeline_event("email_sent", "Email Sent", "success", source=result.provider)
    else:
        can_retry = result.retryable and attempts < settings.max_retry_attempts
        new_state = {
            "status": NotificationStatus.FAILED.value,
            "sent_at": None,
            "provider": result.provider,
            "provider_message_id": None,
            "error": result.error,
            "attempt_count": attempts,
            "last_attempt_at": now,
            "next_retry_at": now + timedelta(seconds=settings.retry_backoff_seconds * (2 ** (attempts - 1))) if can_retry else None,
        }
        event = timeline_event("email_failed", "Email Delivery Failed", "error", source=result.provider,
                               details=result.error)

    await db[Collections.MEETINGS].update_one(
        {"_id": meeting_id},
        {
            "$set": {
                "notifications.email": new_state,
                "status.email_sent": result.success or meeting["status"].get("email_sent", False),
                "updated_at": now,
            },
            "$push": {"timeline": event},
        },
    )
    await db[Collections.NOTIFICATIONS].update_one(
        {"meeting_id": meeting_id, "channel": CHANNEL},
        {
            "$set": {**new_state, "lead_id": meeting["lead_id"], "sales_person_id": meeting["sales_person_id"], "updated_at": now},
            "$setOnInsert": {"created_at": now},
            "$push": {"history": {"at": now, "success": result.success, "error": result.error,
                                  "provider_message_id": result.provider_message_id,
                                  "triggered_by": (triggered_by or {}).get("_id")}},
        },
        upsert=True,
    )

    if result.success:
        await _mark_invitation_sent(meeting_id)
    await refresh_flags(meeting_id)
    return new_state


async def _mark_invitation_sent(meeting_id: ObjectId) -> None:
    db = get_db()
    meeting = await db[Collections.MEETINGS].find_one({"_id": meeting_id}, {"status": 1})
    if meeting and not meeting["status"].get("invitation_sent"):
        await transition(
            meeting_id,
            MeetingState.INVITATION_SENT,
            extra_set={"status.invitation_sent": True},
            event=timeline_event("invitation_sent", "Lead Invited", "success"),
        )


async def send_invitations(meeting_id: ObjectId, want_email: bool = True,
                           triggered_by: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    db = get_db()
    if not want_email:
        skipped = {"status": NotificationStatus.SKIPPED.value, "error": None, "attempt_count": 0}
        await db[Collections.MEETINGS].update_one({"_id": meeting_id}, {"$set": {"notifications.email": skipped}})
        return {"email": skipped}
    try:
        result = await send_email(meeting_id, triggered_by)
    except Exception as exc:  # delivery must never break scheduling
        logger.exception("notification.unexpected_error", extra={"meeting_id": str(meeting_id), "channel": CHANNEL})
        result = {"status": "failed", "error": type(exc).__name__}
    return {"email": result}


async def retry_due_notifications(limit: int = 20) -> int:
    """Worker hook: resend failed emails whose backoff has elapsed."""
    db = get_db()
    now = utcnow()
    due = await db[Collections.NOTIFICATIONS].find(
        {"status": NotificationStatus.FAILED.value, "next_retry_at": {"$ne": None, "$lte": now},
         "attempt_count": {"$lt": settings.max_retry_attempts}}
    ).limit(limit).to_list(length=limit)
    count = 0
    for n in due:
        # Claim the retry so parallel workers don't double-send.
        claimed = await db[Collections.NOTIFICATIONS].update_one(
            {"_id": n["_id"], "next_retry_at": n["next_retry_at"]}, {"$set": {"next_retry_at": None}}
        )
        if not claimed.modified_count:
            continue
        meeting = await db[Collections.MEETINGS].find_one({"_id": n["meeting_id"]}, {"schedule": 1})
        if not meeting or meeting["schedule"]["end_time"] < now:
            continue  # invitation is pointless after the meeting ended
        await send_email(n["meeting_id"])
        count += 1
    return count
