"""Meeting scheduling, retrieval and presentation helpers.

route → meeting_service → classify_service → Classify API"""
import hashlib
import logging
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from app.config.settings import settings
from app.constants.analysis_status import FollowUpStatus, LeadStatus, StageStatus
from app.constants.meeting_status import AI_DERIVED_FLAGS, FLAG_CATEGORY, STATE_LABELS, Flag, MeetingState
from app.database.mongodb import Collections, get_db
from app.dependencies.auth import CurrentUser, ensure_owner, scope_filter
from app.middleware.error_handler import AppError, NotFoundError
from app.models.lead import journey_event
from app.models.meeting import new_meeting_document
from app.schemas.meeting import ScheduleMeetingRequest
from app.services import lead_service, notification_service
from app.services.audit_service import log_activity
from app.services.classify_service import (
    Participant,
    ScheduledMeetingInput,
    build_create_payload,
    classify_service,
    normalize_created_meeting,
    validate_create_payload,
)
from app.services.meeting_state import refresh_flags, timeline_event, transition
from app.utils.datetime_utils import is_valid_timezone, local_to_utc, parse_datetime, to_unix, utcnow
from app.utils.security import redact
from app.utils.validators import maybe_object_id, to_object_id

logger = logging.getLogger(__name__)


def _default_idempotency_key(user_id: str, lead_id: str, start_unix: int, duration: int) -> str:
    raw = f"{user_id}:{lead_id}:{start_unix}:{duration}"
    return "auto-" + hashlib.sha256(raw.encode()).hexdigest()[:40]


async def schedule_meeting(user: CurrentUser, req: ScheduleMeetingRequest, idempotency_key: Optional[str]) -> Dict[str, Any]:
    db = get_db()
    lead = await lead_service.get_lead_for_user(user, req.lead_id)
    sales_person = await db[Collections.USERS].find_one({"_id": lead["sales_person_id"]})
    if not sales_person:
        raise AppError("The lead's assigned sales person no longer exists", 422, "invalid_sales_person")

    # 1–5: validate, convert local Asia/Kolkata time → UTC → unix, check bounds.
    tz = req.timezone or settings.classify_timezone
    if not is_valid_timezone(tz):
        raise AppError("Unable to schedule meeting.", 422, "invalid_timezone", reason="The selected timezone is not supported.")
    if req.min_duration > req.duration_minutes:
        raise AppError(
            "Unable to schedule meeting.", 422, "invalid_min_duration",
            reason="Minimum attendance cannot exceed the meeting duration.",
            hint="Minimum attendance is how long the lead must attend — not the meeting length.",
        )
    start = local_to_utc(req.meeting_date, req.meeting_time, tz)
    end = start + timedelta(minutes=req.duration_minutes)
    label = (req.label or f"Sales Discussion - {lead['name']}").strip()

    meeting_input = ScheduledMeetingInput(
        label=label,
        start_unix=to_unix(start),
        end_unix=to_unix(end),
        lead=Participant(lead["name"], lead["email"]),
        host=Participant(sales_person["name"], sales_person["email"]),
        min_duration=req.min_duration,
        student_notes=req.notes or "",
        timezone=tz,
    )
    # Fail fast with Classify's own rules before creating any record.
    validate_create_payload(build_create_payload(meeting_input))

    key = idempotency_key or req.idempotency_key or _default_idempotency_key(user.id, str(lead["_id"]), meeting_input.start_unix, req.duration_minutes)

    existing = await db[Collections.MEETINGS].find_one({"idempotency_key": key})
    if existing:
        return await _replay(user, existing)

    clash = await db[Collections.MEETINGS].find_one(
        {"lead_id": lead["_id"], "schedule.start_time": start,
         "status.overall": {"$nin": [MeetingState.DRAFT.value, MeetingState.FAILED.value]}}
    )
    if clash:
        raise AppError(
            "Unable to schedule meeting.", 409, "duplicate_meeting",
            reason="A meeting is already scheduled for this lead at this time.",
            details={"meeting_id": str(clash["_id"])},
        )

    doc = new_meeting_document(
        lead=lead, sales_person=sales_person, label=label, start_time=start, end_time=end, timezone=tz,
        min_duration=req.min_duration, idempotency_key=key, created_by=user["_id"], notes=req.notes,
    )
    try:
        result = await db[Collections.MEETINGS].insert_one(doc)
    except DuplicateKeyError:
        existing = await db[Collections.MEETINGS].find_one({"idempotency_key": key})
        return await _replay(user, existing)
    meeting_id = result.inserted_id

    # 6–7: call Classify createMS.
    try:
        response = await classify_service.create_scheduled_meeting(meeting_input)
    except AppError as exc:
        await db[Collections.MEETINGS].delete_one({"_id": meeting_id})
        await log_activity(user, "meeting.schedule_failed", "lead", lead["_id"],
                           {"reason": exc.reason or exc.message, "code": exc.code})
        raise

    # 8: persist the complete response (the echoed authToken is masked).
    normalized = normalize_created_meeting(response)
    now = utcnow()
    events = [timeline_event("meeting_scheduled", "Meeting Scheduled", "success", source="classify")]
    if normalized.get("warning"):
        events.append(timeline_event("attendance_webhook_warning", "Classify attendance callback not registered", "warning",
                                     source="classify", details="Attendance data may need a manual re-sync after the meeting."))
    await db[Collections.MEETINGS].update_one(
        {"_id": meeting_id},
        {
            "$set": {
                "classify": normalized,
                "raw_classify_response": redact(response),
                "status.overall": MeetingState.SCHEDULED.value,
                "status.meeting_created": True,
                "updated_at": now,
            },
            "$push": {"timeline": {"$each": events}},
        },
    )
    await lead_service.add_journey(lead["_id"], journey_event("meeting_scheduled", "Meeting Scheduled", "user", meeting_id,
                                                              details=label))
    await lead_service.set_lead_status(lead["_id"], LeadStatus.MEETING_SCHEDULED)
    await log_activity(user, "meeting.scheduled", "meeting", meeting_id,
                       {"lead_id": str(lead["_id"]), "classify_unique_id": normalized.get("unique_id"),
                        "start_time": start.isoformat()})
    logger.info("meeting.scheduled", extra={"meeting_id": str(meeting_id), "lead_id": str(lead["_id"]),
                                            "sales_person_id": str(sales_person["_id"]),
                                            "classify_unique_id": normalized.get("unique_id")})

    # 9: email invitation. Failures are recorded, never raised.
    await notification_service.send_invitations(meeting_id, req.send_email, triggered_by=user)
    await refresh_flags(meeting_id)
    await lead_service.refresh_lead_intelligence(lead["_id"])

    # 11: return the stored meeting with its statuses.
    return await get_meeting_detail(user, str(meeting_id), audit=False)


async def _replay(user: CurrentUser, existing: Dict[str, Any]) -> Dict[str, Any]:
    ensure_owner(user, existing)
    if existing["status"]["overall"] == MeetingState.DRAFT.value:
        raise AppError("This meeting is already being scheduled", 409, "schedule_in_progress",
                       hint="Please wait a moment and refresh.")
    detail = await get_meeting_detail(user, str(existing["_id"]), audit=False)
    detail["idempotent_replay"] = True
    return detail


# --------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------
def _event_at(meeting: Dict[str, Any], *keys: str):
    for event in reversed(meeting.get("timeline") or []):
        if event.get("key") in keys:
            return event.get("at")
    return None


def build_journey(meeting: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The sales-person-facing lifecycle: technical detail stays hidden."""
    st = meeting["status"]
    proc = meeting.get("processing") or {}
    notif = meeting.get("notifications") or {}
    now = utcnow()
    start, end = meeting["schedule"]["start_time"], meeting["schedule"]["end_time"]
    steps: List[Dict[str, Any]] = []

    def add(key, label, state, at=None, note=None):
        steps.append({"key": key, "label": label, "state": state, "at": at, "note": note})

    add("scheduled", "Scheduled", "done" if st.get("meeting_created") else "pending", _event_at(meeting, "meeting_scheduled"))

    email_status = notif.get("email", {}).get("status")
    if st.get("invitation_sent"):
        add("invited", "Lead Invited", "done", _event_at(meeting, "invitation_sent"), "Email failed" if email_status == "failed" else None)
    elif email_status == "failed":
        add("invited", "Invitation Failed", "error", None, "Resend from the meeting page")
    else:
        add("invited", "Lead Invited", "pending")

    if st.get("no_show"):
        add("joined", "Lead did not join", "error", _event_at(meeting, "no_show"))
    elif st.get("lead_joined"):
        add("joined", "Lead Joined", "done", _event_at(meeting, "lead_joined"))
    elif start <= now <= end and not st.get("meeting_completed"):
        add("joined", "Waiting for Lead…", "active", None, "Attendance is confirmed by Classify after the meeting")
    elif st.get("meeting_completed"):
        add("joined", "Lead attendance not reported", "warning")
    else:
        add("joined", "Lead Joined", "pending")

    sync = meeting.get("attendance_sync") or {}
    if st.get("meeting_completed"):
        add("completed", "Meeting Completed", "done", _event_at(meeting, "meeting_completed"))
    elif sync.get("status") == "failed" and now > end:
        add("completed", "Attendance sync failed", "warning", None, sync.get("last_message"))
    elif now > end and sync.get("status") in ("waiting", "retrying", "requesting", "pending") and not st.get("no_show"):
        note = "Classify reports the class in progress" if sync.get("status") == "waiting" else sync.get("last_message")
        add("completed", "Fetching attendance from Classify…", "active", None, note)
    elif st.get("meeting_data_pending"):
        add("completed", "Awaiting meeting data from Classify", "warning")
    elif start <= now <= end:
        add("completed", "Meeting in progress", "active")
    else:
        add("completed", "Meeting Completed", "pending")

    if not st.get("no_show"):
        stage_labels = {
            "recording": ("Recording Available", "Recording Processing…", "Recording unavailable", "recording_available"),
            "transcript": ("Transcript Ready", "Generating Transcript…", "Transcript unavailable", "transcript_ready"),
            "analysis": ("AI Analysis Ready", "Analyzing Conversation…", "AI analysis unavailable", "analysis_completed"),
        }
        for stage, (done_label, active_label, fail_label, event_key) in stage_labels.items():
            status = (proc.get(stage) or {}).get("status")
            if not st.get("meeting_completed"):
                add(stage, done_label, "pending")
            elif status == StageStatus.COMPLETED.value:
                add(stage, done_label, "done", _event_at(meeting, event_key))
            elif status == StageStatus.PROCESSING.value:
                add(stage, active_label, "active")
            elif status in (StageStatus.FAILED.value, StageStatus.UNAVAILABLE.value):
                add(stage, fail_label, "error" if status == StageStatus.FAILED.value else "warning", None,
                    (proc.get(stage) or {}).get("error_message"))
            elif status == StageStatus.SKIPPED.value:
                add(stage, done_label, "skipped")
            else:
                add(stage, active_label if stage == "recording" else done_label, "active" if stage == "recording" else "pending")

        if st.get("analysis_completed"):
            if st.get("follow_up_required"):
                add("follow_up", "Follow-up Required", "warning", _event_at(meeting, "follow_up_required"))
            else:
                add("follow_up", "No follow-up needed", "done")
    return steps


def build_flag_objects(flags: List[str]) -> List[Dict[str, Any]]:
    out = []
    for f in flags or []:
        try:
            category = FLAG_CATEGORY.get(Flag(f), "meeting")
        except ValueError:
            category = "meeting"
        out.append({"key": f, "category": category, "ai_generated": f in AI_DERIVED_FLAGS})
    return out


def present_meeting(meeting: Dict[str, Any], user: CurrentUser, include_raw: bool = False) -> Dict[str, Any]:
    m = dict(meeting)
    if not (include_raw and user.is_admin):
        m.pop("raw_classify_response", None)
    m.pop("idempotency_key", None)
    overall = m["status"]["overall"]
    m["status_label"] = STATE_LABELS.get(MeetingState(overall), overall) if overall in MeetingState._value2member_map_ else overall
    m["flag_details"] = build_flag_objects(m.get("flags") or [])
    # Hosts may join from the dashboard; the lead link is only shown to staff.
    return m


async def get_meeting_for_user(user: CurrentUser, meeting_id: str) -> Dict[str, Any]:
    meeting = await get_db()[Collections.MEETINGS].find_one({"_id": to_object_id(meeting_id, "meeting id")})
    if not meeting:
        raise NotFoundError("Meeting")
    ensure_owner(user, meeting)
    return meeting


async def get_meeting_detail(user: CurrentUser, meeting_id: str, audit: bool = True) -> Dict[str, Any]:
    from app.services.analytics_service import compute_call_quality  # local import avoids a cycle

    db = get_db()
    meeting = await get_meeting_for_user(user, meeting_id)
    lead = await db[Collections.LEADS].find_one({"_id": meeting["lead_id"]}, {"journey": 0})
    analysis = None
    if (meeting.get("analysis") or {}).get("current_analysis_id"):
        analysis = await db[Collections.MEETING_ANALYTICS].find_one({"_id": meeting["analysis"]["current_analysis_id"]})
    transcript = await db[Collections.MEETING_TRANSCRIPTS].find_one({"meeting_id": meeting["_id"]}, {"text": 0})
    versions = await db[Collections.MEETING_ANALYTICS].find(
        {"meeting_id": meeting["_id"]}, {"model": 1, "prompt_version": 1, "analysis_version": 1, "created_at": 1,
                                         "is_current": 1, "trigger": 1, "status": 1}
    ).sort("created_at", DESCENDING).to_list(length=50)
    follow_ups = await db[Collections.FOLLOW_UPS].find({"meeting_id": meeting["_id"]}).sort("created_at", DESCENDING).to_list(length=20)

    detail = present_meeting(meeting, user, include_raw=True)
    detail["lead"] = await lead_service.decorate_lead(lead) if lead else None
    detail["journey"] = build_journey(meeting, analysis)
    detail["analysis_result"] = (
        {
            "id": analysis["_id"],
            "result": analysis["result"],
            "model": analysis.get("model"),
            "prompt_version": analysis.get("prompt_version"),
            "analysis_version": analysis.get("analysis_version"),
            "created_at": analysis.get("created_at"),
            "is_mock": analysis.get("is_mock", False),
        }
        if analysis
        else None
    )
    detail["transcript_meta"] = (
        {k: transcript.get(k) for k in ("source", "language", "has_speaker_labels", "has_timestamps", "created_at", "model", "is_mock")}
        | {"segment_count": len(transcript.get("segments") or [])}
        if transcript
        else None
    )
    detail["call_quality"] = compute_call_quality(meeting, transcript, analysis)
    detail["analysis_versions"] = versions
    detail["follow_ups"] = follow_ups
    detail["polling"] = {"active": _should_poll(meeting), "interval_seconds": 5}
    if audit:
        await log_activity(user, "meeting.viewed", "meeting", meeting["_id"])
    return detail


def _should_poll(meeting: Dict[str, Any]) -> bool:
    st = meeting["status"]
    if st.get("analysis_completed") or st.get("no_show"):
        return False
    if (meeting.get("processing") or {}).get("active"):
        return True
    now = utcnow()
    start, end = meeting["schedule"]["start_time"], meeting["schedule"]["end_time"]
    return start - timedelta(minutes=10) <= now <= end + timedelta(minutes=settings.no_show_grace_minutes)


async def list_meetings(user: CurrentUser, params: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    query = build_meeting_query(user, params)
    page = max(int(params.get("page") or 1), 1)
    page_size = min(max(int(params.get("page_size") or 20), 1), 100)
    direction = ASCENDING if params.get("order") == "asc" else DESCENDING
    total = await db[Collections.MEETINGS].count_documents(query)
    rows = await (
        db[Collections.MEETINGS]
        .find(query, {"raw_classify_response": 0, "timeline": 0})
        .sort([("schedule.start_time", direction), ("_id", direction)])
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list(length=page_size)
    )
    items = [present_meeting(r, user) for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def build_meeting_query(user: CurrentUser, params: Dict[str, Any]) -> Dict[str, Any]:
    query: Dict[str, Any] = {"status.overall": {"$ne": MeetingState.DRAFT.value}}
    query.update(scope_filter(user, requested=params.get("sales_person_id")))
    if params.get("lead_id"):
        query["lead_id"] = to_object_id(params["lead_id"], "lead id")
    if params.get("status"):
        statuses = [s for s in str(params["status"]).split(",") if s]
        query["status.overall"] = {"$in": statuses}
    if params.get("analysis_status"):
        query["processing.analysis.status"] = params["analysis_status"]
    if params.get("follow_up") in ("true", "false"):
        query["status.follow_up_required"] = params["follow_up"] == "true"
    rng: Dict[str, Any] = {}
    if params.get("date_from"):
        rng["$gte"] = parse_datetime(params["date_from"])
    if params.get("date_to"):
        end = parse_datetime(params["date_to"])
        if end and len(str(params["date_to"])) <= 10:
            end += timedelta(days=1)
        rng["$lt"] = end
    if rng:
        query["schedule.start_time"] = {k: v for k, v in rng.items() if v is not None}
    q = (params.get("q") or "").strip()
    if q:
        pattern = re.compile(re.escape(q), re.IGNORECASE)
        ors: List[Dict[str, Any]] = [
            {"label": pattern}, {"lead_snapshot.name": pattern}, {"lead_snapshot.email": pattern},
            {"sales_person_snapshot.name": pattern}, {"classify.unique_id": q},
        ]
        oid = maybe_object_id(q)
        if oid:
            ors.append({"_id": oid})
        query["$or"] = ors
    return query


async def resend_email(user: CurrentUser, meeting_id: str) -> Dict[str, Any]:
    meeting = await get_meeting_for_user(user, meeting_id)
    if not meeting["status"].get("meeting_created"):
        raise AppError("Meeting was not created in Classify", 409, "meeting_not_created")
    if meeting["schedule"]["end_time"] < utcnow():
        raise AppError("This meeting has already ended", 409, "meeting_ended", hint="Schedule a new meeting instead.")
    state = await notification_service.send_email(meeting["_id"], triggered_by=user, force=True)
    await log_activity(user, "meeting.resend_email", "meeting", meeting["_id"], {"status": state.get("status")})
    return state


async def open_follow_up_count(owner_filter: Dict[str, Any]) -> int:
    return await get_db()[Collections.FOLLOW_UPS].count_documents(
        {**owner_filter, "status": {"$in": [FollowUpStatus.PENDING.value, FollowUpStatus.SNOOZED.value]}}
    )


async def lifecycle_sweep() -> int:
    """Time-based transitions that do NOT assert attendance facts:
    SCHEDULED/INVITATION_SENT → WAITING_FOR_LEAD once the start time passes,
    and a MEETING_DATA_PENDING flag if Classify has not reported back well
    after the end time. No-show is only set from Classify attendance data."""
    db = get_db()
    now = utcnow()
    changed = 0
    waiting = db[Collections.MEETINGS].find(
        {"status.overall": {"$in": [MeetingState.SCHEDULED.value, MeetingState.INVITATION_SENT.value]},
         "schedule.start_time": {"$lte": now}, "schedule.end_time": {"$gte": now}},
        {"_id": 1},
    )
    async for m in waiting:
        if await transition(m["_id"], MeetingState.WAITING_FOR_LEAD,
                            event=timeline_event("waiting_for_lead", "Waiting for Lead", "info")):
            changed += 1
            await refresh_flags(m["_id"])

    overdue = db[Collections.MEETINGS].find(
        {"status.meeting_completed": False, "status.no_show": False, "status.meeting_data_pending": {"$ne": True},
         "status.meeting_created": True,
         "schedule.end_time": {"$lte": now - timedelta(minutes=settings.no_show_grace_minutes)}},
        {"_id": 1},
    )
    async for m in overdue:
        await db[Collections.MEETINGS].update_one(
            {"_id": m["_id"]},
            {"$set": {"status.meeting_data_pending": True, "updated_at": now},
             "$push": {"timeline": timeline_event("meeting_data_pending", "Awaiting attendance data from Classify", "warning",
                                                  details="No attendance webhook yet. Attendance is not assumed.")}},
        )
        await refresh_flags(m["_id"])
        changed += 1
    return changed

