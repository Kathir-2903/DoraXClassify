"""Classify webhook ingestion (fast, idempotent) and attendance application
(asynchronous). Heavy work — download, transcription, AI — happens in the
processing worker, never inside the HTTP request."""
import hashlib
import json
import logging
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from pymongo.errors import DuplicateKeyError

from app.config.settings import settings
from app.constants.analysis_status import LeadStatus, StageStatus
from app.constants.meeting_status import MeetingState
from app.database.mongodb import Collections, get_db
from app.models.lead import journey_event
from app.models.webhook import new_webhook_event
from app.services import lead_service
from app.services.classify_service import mock_attendance_response, normalize_attendance_payload
from app.services.meeting_state import refresh_flags, timeline_event, transition
from app.utils.datetime_utils import utcnow

logger = logging.getLogger(__name__)

SAFE_HEADERS = ("content-type", "user-agent", "x-event-id", "x-classify-event-id", "x-request-id")


def derive_event_id(payload: Dict[str, Any], raw_body: bytes, headers: Dict[str, str]) -> str:
    for key in ("x-classify-event-id", "x-event-id"):
        if headers.get(key):
            return headers[key][:200]
    for key in ("event_id", "eventId", "id"):
        if isinstance(payload.get(key), (str, int)) and str(payload.get(key)):
            return str(payload[key])[:200]
    # Content hash: identical redeliveries dedupe; a genuinely new payload for
    # the same meeting (e.g. recordings arriving later) is a new event.
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(canonical or raw_body).hexdigest()


async def ingest(payload: Dict[str, Any], raw_body: bytes, headers: Dict[str, str], source: str = "classify") -> Tuple[str, bool]:
    """Store the event. Returns (event_id, is_duplicate)."""
    event_id = derive_event_id(payload, raw_body, headers)
    normalized = normalize_attendance_payload(payload)
    safe_headers = {k: v for k, v in headers.items() if k in SAFE_HEADERS}
    doc = new_webhook_event(event_id, payload, source, normalized.get("unique_id"), safe_headers)
    try:
        await get_db()[Collections.WEBHOOK_EVENTS].insert_one(doc)
    except DuplicateKeyError:
        logger.info("webhook.duplicate", extra={"event_id": event_id})
        return event_id, True
    logger.info("webhook.received", extra={"event_id": event_id, "classify_unique_id": normalized.get("unique_id")})
    return event_id, False


async def reprocess_event(event_id: str) -> Optional[str]:
    """Force a stored event to be applied again, ignoring its prior
    processing_status. Used for a manual "Sync attendance" re-check, where
    Classify's response is often byte-identical to an earlier call (so the
    normal content-hash dedup would otherwise silently ignore it) but the
    application logic that interprets it may have changed — e.g. a no-show
    verdict that's now known to be wrong for a guest who wasn't listed."""
    await get_db()[Collections.WEBHOOK_EVENTS].update_one(
        {"event_id": event_id}, {"$set": {"processing_status": "pending"}})
    return await process_event(event_id)


async def process_event(event_id: str) -> Optional[str]:
    """Apply a stored event to its meeting. Safe to call repeatedly."""
    db = get_db()
    now = utcnow()
    event = await db[Collections.WEBHOOK_EVENTS].find_one_and_update(
        {"event_id": event_id, "processing_status": {"$in": ["pending", "failed"]}},
        {"$set": {"processing_status": "processing", "last_attempt_at": now}, "$inc": {"attempt_count": 1}},
    )
    if not event:
        return None  # already processed or being processed
    try:
        meeting_id = await apply_attendance(event)
        status = "processed" if meeting_id else "unmatched"
        await db[Collections.WEBHOOK_EVENTS].update_one(
            {"_id": event["_id"]},
            {"$set": {"processing_status": status, "processed": bool(meeting_id), "processed_at": utcnow(),
                      "meeting_id": meeting_id,
                      "error_message": None if meeting_id else "No meeting matches this Classify uniqueId"}},
        )
        return status
    except Exception as exc:
        logger.exception("webhook.processing_failed", extra={"event_id": event_id})
        attempts = int(event.get("attempt_count") or 0) + 1
        await db[Collections.WEBHOOK_EVENTS].update_one(
            {"_id": event["_id"]},
            {"$set": {"processing_status": "failed", "error_message": f"{type(exc).__name__}: {str(exc)[:300]}",
                      "next_retry_at": utcnow() + timedelta(seconds=settings.retry_backoff_seconds) if attempts < settings.max_retry_attempts else None}},
        )
        if event.get("meeting_id"):
            await db[Collections.MEETINGS].update_one({"_id": event["meeting_id"]}, {"$set": {"webhook_error": str(exc)[:300]}})
        return "failed"


async def apply_attendance(event: Dict[str, Any]):
    db = get_db()
    data = normalize_attendance_payload(event["payload"])
    unique_id = data.get("unique_id")
    if not unique_id:
        return None
    meeting = await db[Collections.MEETINGS].find_one({"classify.unique_id": unique_id})
    if not meeting:
        logger.warning("webhook.unmatched", extra={"classify_unique_id": unique_id})
        return None
    mid = meeting["_id"]
    await db[Collections.WEBHOOK_EVENTS].update_one({"_id": event["_id"]}, {"$set": {"meeting_id": mid}})
    now = utcnow()
    lead_email = (meeting["lead_snapshot"].get("email") or "").lower()
    host_email = (meeting["sales_person_snapshot"].get("email") or "").lower()
    lead_att = next((a for a in data["attendees"] if a["email"] == lead_email), None)
    host_att = next((a for a in data["attendees"] if a["email"] == host_email), None) \
        or next((a for a in data["attendees"] if a.get("role") == "host"), None)

    # Store recording sources privately (never on the meeting document).
    if data["recording_urls"] or data["transcripts"] or data["chat_urls"]:
        update: Dict[str, Any] = {"$setOnInsert": {"created_at": now, "status": "pending"}, "$set": {"updated_at": now}}
        if data["recording_urls"]:
            update["$addToSet"] = {"source_urls": {"$each": data["recording_urls"]}}
        if data["transcripts"]:
            update["$push"] = {"classify_transcripts": {"$each": data["transcripts"]}}
        if data["chat_urls"]:
            update.setdefault("$addToSet", {})["chat_urls"] = {"$each": data["chat_urls"]}
        await db[Collections.MEETING_RECORDINGS].update_one({"meeting_id": mid}, update, upsert=True)

    # Decide attendance only from what Classify actually reported. Guest
    # (meetingType "open") participants are not pre-registered, and Classify's
    # SendAttendanceDetails has been observed to omit them from
    # attendanceDetails entirely even when they genuinely joined (confirmed
    # live: only the host was listed for a meeting the guest did attend) — so
    # "lead missing from the list" can't be trusted as "lead absent" here.
    # Leaving lead_joined unresolved lets the meeting proceed to processing
    # instead of a false no-show; the transcript itself is the honest signal.
    guest_meeting = (meeting.get("classify") or {}).get("meeting_type") == "open"
    lead_joined: Optional[bool] = None
    if lead_att is not None and lead_att["present"] is not None:
        lead_joined = lead_att["present"]
    elif not guest_meeting and data["has_attendance"] and lead_att is None and data["attendees"]:
        lead_joined = False  # attendance list provided and the lead is not on it
    elif not guest_meeting and data["has_attendance"] and data["total_present"] == 0:
        lead_joined = False

    attendance = {
        "received_at": now,
        "actual_start": data["started_at"],
        "actual_end": data["ended_at"],
        "duration_seconds": data["duration_seconds"],
        "total_present": data["total_present"],
        "total_absent": data["total_absent"],
        "total_students": data["total_students"],
        "minimum_attendance_time": data["minimum_attendance_time"],
        "lead": lead_att,
        "host": host_att,
        "attendees_count": len(data["attendees"]),
        "lead_joined": lead_joined,
        "source": "classify_webhook",
    }
    sets: Dict[str, Any] = {"attendance": attendance, "webhook_received_at": now, "webhook_error": None,
                            "status.meeting_data_pending": False, "updated_at": now}
    events = [timeline_event("webhook_received", "Attendance received from Classify", "info", "classify")]
    already_completed = meeting["status"].get("meeting_completed")

    if lead_joined is False:
        sets.update({"status.no_show": True, "status.lead_joined": False,
                     "processing.recording.status": StageStatus.SKIPPED.value,
                     "processing.transcript.status": StageStatus.SKIPPED.value,
                     "processing.analysis.status": StageStatus.SKIPPED.value})
        events.append(timeline_event("no_show", "Lead did not join", "error", "classify",
                                     details="Classify attendance shows the lead did not attend."))
        await db[Collections.MEETINGS].update_one({"_id": mid}, {"$set": sets, "$push": {"timeline": {"$each": events}}})
        await transition(mid, MeetingState.NO_SHOW)
        await lead_service.add_journey(meeting["lead_id"], journey_event("no_show", "Lead did not join", "classify", mid))
        await lead_service.set_lead_status(meeting["lead_id"], LeadStatus.NO_SHOW)
    else:
        if meeting["status"].get("no_show"):
            # Correcting an earlier no-show verdict (a manual re-sync, e.g.
            # after learning Classify's attendance API missed a guest).
            sets["status.no_show"] = False
            events.append(timeline_event("no_show_corrected", "No-show verdict corrected", "info", "classify",
                                         details="Attendance re-checked; proceeding to process the meeting."))
        started_at = data["started_at"]
        if lead_joined:
            sets["status.lead_joined"] = True
            joined_at = (lead_att or {}).get("joined_at") or started_at
            if not meeting["status"].get("lead_joined"):
                events.append(timeline_event("lead_joined", "Lead Joined", "success", "classify", at=joined_at,
                                             details=_attended_note(lead_att)))
        if host_att and host_att.get("present"):
            sets["status.sales_person_joined"] = True
            if not meeting["status"].get("sales_person_joined"):
                events.append(timeline_event("sales_person_joined", "Sales Person Joined", "success", "classify",
                                             at=host_att.get("joined_at") or started_at))
        if started_at or lead_joined:
            sets["status.meeting_started"] = True
            if not meeting["status"].get("meeting_started"):
                events.append(timeline_event("meeting_started", "Meeting Started", "info", "classify", at=started_at))
        completed = bool(data["ended_at"] or data["has_attendance"] or data["recording_urls"])
        if completed and not already_completed:
            sets["status.meeting_completed"] = True
            events.append(timeline_event("meeting_completed", "Meeting Completed", "success", "classify",
                                         at=data["ended_at"] or now,
                                         details=f"Duration {int(data['duration_seconds'] // 60)} min" if data["duration_seconds"] else None))
        recording_stage = meeting.get("processing", {}).get("recording", {}).get("status")
        requeue = (completed and recording_stage in (StageStatus.PENDING.value, StageStatus.UNAVAILABLE.value, StageStatus.SKIPPED.value)) \
            or (bool(data["recording_urls"]) and recording_stage == StageStatus.FAILED.value)
        if requeue:
            # (Re)queue the pipeline — new recording URLs revive a missing/failed recording stage.
            sets.update({"processing.recording.status": StageStatus.PENDING.value, "processing.recording.next_retry_at": None,
                         "processing.recording.attempt_count": 0, "processing.active": True})
            # SKIPPED covers a corrected no-show verdict, whose transcript and
            # analysis stages were skipped along with the recording.
            if recording_stage in (StageStatus.UNAVAILABLE.value, StageStatus.FAILED.value, StageStatus.SKIPPED.value):
                sets.update({"processing.transcript.status": StageStatus.PENDING.value, "processing.transcript.attempt_count": 0,
                             "processing.analysis.status": StageStatus.PENDING.value, "processing.analysis.attempt_count": 0})
        await db[Collections.MEETINGS].update_one({"_id": mid}, {"$set": sets, "$push": {"timeline": {"$each": events}}})
        if lead_joined:
            await transition(mid, MeetingState.LEAD_JOINED)
        if sets.get("status.meeting_started"):
            await transition(mid, MeetingState.IN_PROGRESS)
        if sets.get("status.meeting_completed") or already_completed:
            await transition(mid, MeetingState.MEETING_COMPLETED)
            if sets.get("processing.recording.status") == StageStatus.PENDING.value:
                await transition(mid, MeetingState.RECORDING_PROCESSING)
        if not already_completed and completed:
            await lead_service.add_journey(
                meeting["lead_id"],
                journey_event("meeting_completed", "Meeting Completed", "classify", mid, at=data["ended_at"] or now,
                              details=f"{int(data['duration_seconds'] // 60)} min" if data["duration_seconds"] else None),
            )
            if lead_joined:
                await lead_service.set_lead_status(meeting["lead_id"], LeadStatus.ENGAGED)

    await refresh_flags(mid)
    await lead_service.refresh_lead_intelligence(meeting["lead_id"])
    logger.info("webhook.applied", extra={"meeting_id": str(mid), "classify_unique_id": unique_id, "lead_joined": lead_joined})
    return mid


def _attended_note(att: Optional[Dict[str, Any]]) -> Optional[str]:
    if not att or att.get("attended_seconds") is None:
        return None
    return f"Attended {int(att['attended_seconds'] // 60)} min (Classify)"


async def retry_failed_events(limit: int = 10) -> int:
    db = get_db()
    events = await db[Collections.WEBHOOK_EVENTS].find(
        {"processing_status": "failed", "next_retry_at": {"$ne": None, "$lte": utcnow()},
         "attempt_count": {"$lt": settings.max_retry_attempts}}, {"event_id": 1}
    ).limit(limit).to_list(length=limit)
    for e in events:
        await process_event(e["event_id"])
    return len(events)


def build_simulated_payload(meeting: Dict[str, Any], outcome: str, duration_minutes: int) -> Dict[str, Any]:
    """Demo-only: a SendAttendanceDetails response (documented shape) for a meeting that just ended."""
    payload = mock_attendance_response(meeting, outcome=outcome, duration_minutes=duration_minutes, end=utcnow())
    payload["_simulated"] = True
    return payload
