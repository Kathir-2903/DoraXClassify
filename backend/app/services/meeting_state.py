"""Lifecycle transitions, timeline events and flag derivation for meetings."""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.constants.analysis_status import StageStatus
from app.constants.meeting_status import Flag, MeetingState, can_transition
from app.database.mongodb import Collections, get_db
from app.utils.datetime_utils import utcnow

logger = logging.getLogger(__name__)


def timeline_event(key: str, label: str, level: str = "success", source: str = "system",
                   details: Optional[str] = None, at: Optional[datetime] = None, ai: bool = False) -> Dict[str, Any]:
    return {"key": key, "label": label, "level": level, "source": source, "details": details,
            "at": at or utcnow(), "ai_generated": ai}


async def add_timeline(meeting_id: ObjectId, *events: Dict[str, Any], extra_set: Optional[Dict[str, Any]] = None) -> None:
    update: Dict[str, Any] = {"$push": {"timeline": {"$each": list(events)}}, "$set": {"updated_at": utcnow()}}
    if extra_set:
        update["$set"].update(extra_set)
    await get_db()[Collections.MEETINGS].update_one({"_id": meeting_id}, update)


async def transition(meeting_id: ObjectId, target: MeetingState, extra_set: Optional[Dict[str, Any]] = None,
                     event: Optional[Dict[str, Any]] = None) -> bool:
    """Move a meeting to `target` if the state machine allows it.

    Uses a conditional update on the current state so concurrent workers
    cannot race each other into an invalid state."""
    db = get_db()
    meeting = await db[Collections.MEETINGS].find_one({"_id": meeting_id}, {"status.overall": 1})
    if not meeting:
        return False
    current = meeting["status"]["overall"]
    if not can_transition(current, target.value):
        logger.info("meeting.transition_rejected", extra={"meeting_id": str(meeting_id), "from": current, "to": target.value})
        if extra_set or event:
            update: Dict[str, Any] = {"$set": {"updated_at": utcnow(), **(extra_set or {})}}
            if event:
                update["$push"] = {"timeline": event}
            await db[Collections.MEETINGS].update_one({"_id": meeting_id}, update)
        return False
    update = {"$set": {"status.overall": target.value, "updated_at": utcnow(), **(extra_set or {})}}
    if event:
        update["$push"] = {"timeline": event}
    result = await db[Collections.MEETINGS].update_one({"_id": meeting_id, "status.overall": current}, update)
    if result.modified_count:
        logger.info("meeting.transition", extra={"meeting_id": str(meeting_id), "from": current, "to": target.value})
    return bool(result.modified_count)


def compute_flags(meeting: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None) -> List[str]:
    """Derive the flag set from stored facts only."""
    st = meeting.get("status", {})
    proc = meeting.get("processing", {})
    notif = meeting.get("notifications", {})
    flags: List[Flag] = []

    if st.get("meeting_created"):
        flags.append(Flag.MEETING_SCHEDULED)
    if st.get("invitation_sent"):
        flags.append(Flag.INVITATION_SENT)
    if notif.get("email", {}).get("status") in ("sent", "delivered"):
        flags.append(Flag.EMAIL_SENT)
    elif notif.get("email", {}).get("status") == "failed":
        flags.append(Flag.EMAIL_FAILED)
    if st.get("lead_joined"):
        flags.append(Flag.LEAD_JOINED)
    if st.get("sales_person_joined"):
        flags.append(Flag.SALES_PERSON_JOINED)
    if st.get("meeting_started"):
        flags.append(Flag.MEETING_STARTED)
    if st.get("meeting_completed"):
        flags.append(Flag.MEETING_COMPLETED)
    if st.get("meeting_data_pending"):
        flags.append(Flag.MEETING_DATA_PENDING)
    if st.get("no_show"):
        flags.append(Flag.NO_SHOW)
    if meeting.get("webhook_received_at"):
        flags.append(Flag.WEBHOOK_RECEIVED)
    if meeting.get("webhook_error"):
        flags.append(Flag.WEBHOOK_PROCESSING_FAILED)
    if (meeting.get("attendance_sync") or {}).get("status") == "failed" and not st.get("meeting_completed") and not st.get("no_show"):
        flags.append(Flag.ATTENDANCE_SYNC_FAILED)

    rec = proc.get("recording", {}).get("status")
    tr = proc.get("transcript", {}).get("status")
    an = proc.get("analysis", {}).get("status")
    if st.get("recording_available"):
        flags.append(Flag.RECORDING_AVAILABLE)
    elif rec == StageStatus.UNAVAILABLE.value:
        flags.append(Flag.RECORDING_MISSING)
    if rec == StageStatus.PROCESSING.value:
        flags.append(Flag.RECORDING_PROCESSING)
    if rec == StageStatus.FAILED.value:
        flags.append(Flag.RECORDING_FAILED)
    if st.get("transcript_available"):
        flags.append(Flag.TRANSCRIPT_AVAILABLE)
    if tr == StageStatus.PROCESSING.value:
        flags.append(Flag.TRANSCRIPT_PROCESSING)
    if tr == StageStatus.FAILED.value:
        flags.append(Flag.TRANSCRIPT_FAILED)
    if an == StageStatus.PROCESSING.value:
        flags.append(Flag.AI_ANALYSIS_PROCESSING)
    if an == StageStatus.FAILED.value:
        flags.append(Flag.AI_ANALYSIS_FAILED)
    if st.get("analysis_completed"):
        flags.append(Flag.ANALYSIS_COMPLETE)
    elif st.get("meeting_completed") and not st.get("no_show") and an in (StageStatus.PENDING.value, StageStatus.PROCESSING.value):
        flags.append(Flag.ANALYSIS_PENDING)

    if analysis:
        result = analysis.get("result", {})
        coverage = result.get("pitch_coverage") or []
        if coverage:
            covered = sum(1 for c in coverage if c.get("covered"))
            flags.append(Flag.PITCH_COMPLETED if covered >= max(1, round(len(coverage) * 0.75)) else Flag.PITCH_INCOMPLETE)
        pricing = (result.get("pricing_discussion") or {}).get("discussed")
        flags.append(Flag.PRICING_DISCUSSED if pricing else Flag.PRICING_NOT_DISCUSSED)
        objections = result.get("lead_objections") or []
        flags.append(Flag.OBJECTION_RAISED if objections else Flag.NO_OBJECTION_DETECTED)
        follow = (result.get("follow_up") or {}).get("required")
        flags.append(Flag.FOLLOW_UP_REQUIRED if follow else Flag.FOLLOW_UP_NOT_REQUIRED)
        interest = result.get("interest_level")
        if interest == "high":
            flags.append(Flag.HIGH_INTEREST_SIGNAL)
        elif interest == "low":
            flags.append(Flag.LOW_INTEREST_SIGNAL)
        if result.get("purchase_intent") in ("high", "medium"):
            flags.append(Flag.PURCHASE_INTENT_SIGNAL)
        categories = {o.get("category") for o in objections}
        if "price" in categories:
            flags.append(Flag.PRICE_CONCERN)
        if "time" in categories:
            flags.append(Flag.TIME_CONCERN)
        if "approval" in categories or "uncertainty" in categories:
            flags.append(Flag.DECISION_PENDING)
        text = " ".join(
            [s.get("signal", "") for s in result.get("positive_signals") or []]
            + [a.get("item", "") for a in result.get("action_items") or []]
        ).lower()
        if any(k in text for k in ("brochure", "more information", "send details", "more details", "syllabus", "curriculum pdf")):
            flags.append(Flag.REQUESTED_MORE_INFORMATION)

    seen, ordered = set(), []
    for f in flags:
        if f.value not in seen:
            seen.add(f.value)
            ordered.append(f.value)
    return ordered


async def refresh_flags(meeting_id: ObjectId) -> List[str]:
    db = get_db()
    meeting = await db[Collections.MEETINGS].find_one({"_id": meeting_id})
    if not meeting:
        return []
    analysis = None
    if meeting.get("analysis", {}).get("current_analysis_id"):
        analysis = await db[Collections.MEETING_ANALYTICS].find_one({"_id": meeting["analysis"]["current_analysis_id"]})
    flags = compute_flags(meeting, analysis)
    processing_active = any(
        meeting.get("processing", {}).get(s, {}).get("status") in (StageStatus.PENDING.value, StageStatus.PROCESSING.value)
        for s in ("recording", "transcript", "analysis")
    ) and meeting["status"].get("meeting_completed") and not meeting["status"].get("no_show")
    await db[Collections.MEETINGS].update_one(
        {"_id": meeting_id}, {"$set": {"flags": flags, "processing.active": bool(processing_active)}}
    )
    return flags
