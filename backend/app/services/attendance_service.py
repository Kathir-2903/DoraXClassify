"""Pulls attendance + recordings from Classify's SendAttendanceDetails API.

After a meeting's scheduled end (+ CLASSIFY_ATTENDANCE_SYNC_DELAY_MINUTES) the
worker requests its attendance. Classify answers "409 Class in progress" until
the session has really ended, so we retry every CLASSIFY_ATTENDANCE_RETRY_MINUTES
up to CLASSIFY_ATTENDANCE_MAX_ATTEMPTS. A successful response is stored in
`webhook_events` (source `classify_attendance_api`) and applied through exactly
the same code path as an inbound Classify webhook, so both delivery routes are
idempotent with each other."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.database.mongodb import Collections, get_db
from app.services import webhook_service
from app.services.classify_service import classify_service
from app.services.meeting_state import refresh_flags, timeline_event
from app.utils.datetime_utils import utcnow

logger = logging.getLogger(__name__)

SOURCE = "classify_attendance_api"
LEASE_MINUTES = 5


def new_sync_state() -> Dict[str, Any]:
    return {"status": "pending", "attempt_count": 0, "last_attempt_at": None, "next_attempt_at": None,
            "last_message": None, "completed_at": None}


def _due_query(now) -> Dict[str, Any]:
    return {
        "status.meeting_created": True,
        "status.meeting_completed": {"$ne": True},
        "status.no_show": {"$ne": True},
        "classify.unique_id": {"$ne": None},
        # A meeting created while CLASSIFY_MOCK_MODE was on has a fake uniqueId
        # that only ever existed locally — never ask the real Classify API
        # about it, even if mock mode is later switched off.
        "classify.is_mock": {"$ne": True},
        "schedule.end_time": {"$lte": now - timedelta(minutes=settings.classify_attendance_sync_delay_minutes)},
        "attendance_sync.status": {"$nin": ["completed", "failed"]},
        "$or": [{"attendance_sync.next_attempt_at": None}, {"attendance_sync.next_attempt_at": {"$lte": now}}],
    }


async def sync_meeting(meeting: Dict[str, Any], triggered_by: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Request attendance for one meeting and record the outcome. Never raises."""
    db = get_db()
    mid = meeting["_id"]
    now = utcnow()
    state = meeting.get("attendance_sync") or new_sync_state()
    attempts = int(state.get("attempt_count") or 0) + 1
    result = await classify_service.request_attendance(meeting)
    sets: Dict[str, Any] = {"attendance_sync.attempt_count": attempts, "attendance_sync.last_attempt_at": now,
                            "attendance_sync.last_message": result.message, "attendance_sync.last_status": result.status_text}
    events = []

    if result.outcome == "ok":
        event_id, duplicate = await webhook_service.ingest(result.body, b"", {}, source=SOURCE)
        if duplicate and triggered_by:
            # A manual re-check must actually re-run the logic rather than be
            # silently dropped as an idempotent redelivery — Classify's
            # response for an already-ended meeting is often byte-identical
            # to the first call, which is exactly what a user re-syncing a
            # (possibly wrong) no-show verdict is trying to correct.
            applied = await webhook_service.reprocess_event(event_id)
        else:
            applied = "duplicate" if duplicate else await webhook_service.process_event(event_id)
        sets.update({"attendance_sync.status": "completed", "attendance_sync.completed_at": now,
                     "attendance_sync.next_attempt_at": None, "attendance_sync.event_id": event_id})
        logger.info("attendance.synced", extra={"meeting_id": str(mid), "result": applied})
    elif result.outcome == "in_progress":
        if attempts >= settings.classify_attendance_max_attempts and not triggered_by:
            sets.update({"attendance_sync.status": "failed", "attendance_sync.next_attempt_at": None})
            events.append(timeline_event("attendance_sync_failed", "Classify still reports the class in progress", "warning",
                                         "classify", details=result.message))
        else:
            sets.update({"attendance_sync.status": "waiting",
                         "attendance_sync.next_attempt_at": now + timedelta(minutes=settings.classify_attendance_retry_minutes)})
    else:
        final = not result.retryable or (attempts >= settings.classify_attendance_max_attempts and not triggered_by)
        if final:
            sets.update({"attendance_sync.status": "failed", "attendance_sync.next_attempt_at": None})
            events.append(timeline_event("attendance_sync_failed", "Attendance sync with Classify failed", "warning",
                                         "classify", details=result.message))
        else:
            sets.update({"attendance_sync.status": "retrying",
                         "attendance_sync.next_attempt_at": now + timedelta(minutes=settings.classify_attendance_retry_minutes)})
        logger.warning("attendance.sync_error", extra={"meeting_id": str(mid), "attempt": attempts, "final": final,
                                                       "error": result.message})

    update: Dict[str, Any] = {"$set": sets}
    if events:
        update["$push"] = {"timeline": {"$each": events}}
    await db[Collections.MEETINGS].update_one({"_id": mid}, update)
    await refresh_flags(mid)
    return {"outcome": result.outcome, "message": result.message, "status": result.status_text, "attempts": attempts}


async def sync_due_meetings(limit: int = 10) -> int:
    """Worker hook: claim due meetings (with a short lease) and sync them."""
    db = get_db()
    count = 0
    for _ in range(limit):
        now = utcnow()
        meeting = await db[Collections.MEETINGS].find_one_and_update(
            _due_query(now),
            {"$set": {"attendance_sync.next_attempt_at": now + timedelta(minutes=LEASE_MINUTES),
                      "attendance_sync.status": "requesting"}},
            sort=[("schedule.end_time", 1)],
        )
        if not meeting:
            break
        await sync_meeting(meeting)
        count += 1
    return count
