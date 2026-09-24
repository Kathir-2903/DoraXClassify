"""AI analysis stage: transcript → Gemini → validated JSON → MongoDB.

Every run creates a new versioned `meeting_analytics` document; earlier
versions are kept (is_current=False) so meetings can be re-analysed with
newer prompts/models without losing history."""
import logging
from typing import Any, Dict, List, Optional

from app.constants.analysis_status import ANALYSIS_VERSION, DEFAULT_PITCH_CHECKLIST, LeadStatus
from app.constants.meeting_status import MeetingState
from app.database.mongodb import Collections, get_db
from app.models.lead import journey_event
from app.services import followup_service, lead_service
from app.services.gemini_service import GeminiError, gemini_service
from app.services.meeting_state import refresh_flags, timeline_event, transition
from app.utils.datetime_utils import utcnow

logger = logging.getLogger(__name__)

OBJECTION_LABELS = {
    "price": "Pricing",
    "time": "Time commitment",
    "approval": "Needs approval",
    "competition": "Competition",
    "uncertainty": "Uncertainty",
    "relevance": "Relevance",
    "other": "Other",
}


async def get_pitch_checklist() -> List[str]:
    doc = await get_db()[Collections.APP_SETTINGS].find_one({"key": "pitch_checklist"})
    topics = (doc or {}).get("value")
    return topics if isinstance(topics, list) and topics else list(DEFAULT_PITCH_CHECKLIST)


def build_snapshot(result: Dict[str, Any]) -> Dict[str, Any]:
    """Compact, denormalised view used by tables, dashboards and lead roll-ups."""
    objections = result.get("lead_objections") or []
    categories = [o.get("category") for o in objections if o.get("category")]
    coverage = result.get("pitch_coverage") or []
    follow = result.get("follow_up") or {}
    main = None
    if objections:
        main = OBJECTION_LABELS.get(objections[0].get("category"), None) or objections[0].get("objection")
    return {
        "summary": result.get("summary"),
        "interest_level": result.get("interest_level"),
        "purchase_intent": result.get("purchase_intent"),
        "engagement_level": (result.get("engagement") or {}).get("level"),
        "lead_sentiment": result.get("lead_sentiment"),
        "main_objection": main,
        "objection_categories": sorted(set(categories)),
        "objections": [o.get("objection") for o in objections],
        "questions_count": len(result.get("lead_questions") or []),
        "objections_count": len(objections),
        "action_items_count": len(result.get("action_items") or []),
        "pitch_covered": sum(1 for c in coverage if c.get("covered")),
        "pitch_total": len(coverage),
        "topics": result.get("topics_discussed") or [],
        "pricing_discussed": bool((result.get("pricing_discussion") or {}).get("discussed")),
        "follow_up_required": bool(follow.get("required")),
        "follow_up_reason": follow.get("reason"),
        "recommended_next_action": follow.get("recommended_next_action"),
        "meeting_outcome": result.get("meeting_outcome"),
        "confidence": result.get("confidence"),
        "top_question": (result.get("lead_questions") or [{}])[0].get("question") if result.get("lead_questions") else None,
        "interests": result.get("interests") or [],
    }


def build_metadata(meeting: Dict[str, Any], lead: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    attendance = meeting.get("attendance") or {}
    return {
        "meeting_id": str(meeting["_id"]),
        "label": meeting.get("label"),
        "scheduled_start": meeting["schedule"]["start_time"],
        "scheduled_duration_minutes": meeting["schedule"]["duration_minutes"],
        "actual_duration_seconds": attendance.get("duration_seconds"),
        "timezone": meeting["schedule"].get("timezone"),
        "lead": {
            "name": (lead or meeting["lead_snapshot"]).get("name"),
            "company": (lead or {}).get("company"),
            "interested_product": (lead or {}).get("interested_product"),
            "lead_source": (lead or {}).get("lead_source"),
            "notes": (lead or {}).get("notes"),
        },
        "sales_person": {"name": meeting["sales_person_snapshot"].get("name")},
    }


async def run_analysis(meeting: Dict[str, Any], trigger: str = "pipeline", user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Analyse the stored transcript. Raises on failure (the caller records it)."""
    db = get_db()
    transcript = await db[Collections.MEETING_TRANSCRIPTS].find_one({"meeting_id": meeting["_id"]})
    if not transcript or not transcript.get("text"):
        raise GeminiError("Transcript unavailable", retryable=False)
    lead = await db[Collections.LEADS].find_one({"_id": meeting["lead_id"]})
    checklist = await get_pitch_checklist()
    output = await gemini_service.analyze(
        transcript["text"], build_metadata(meeting, lead), checklist,
        mock_seed=transcript.get("mock_scenario") or str(meeting["_id"]),
    )
    result = output.analysis.model_dump()
    now = utcnow()

    await db[Collections.MEETING_ANALYTICS].update_many({"meeting_id": meeting["_id"], "is_current": True},
                                                        {"$set": {"is_current": False}})
    doc = {
        "meeting_id": meeting["_id"],
        "lead_id": meeting["lead_id"],
        "sales_person_id": meeting["sales_person_id"],
        "result": result,
        "model": output.model,
        "prompt_version": output.prompt_version,
        "analysis_version": ANALYSIS_VERSION,
        "checklist": checklist,
        "transcript_source": transcript.get("source"),
        "trigger": trigger,
        "triggered_by": (user or {}).get("_id"),
        "is_current": True,
        "is_mock": output.is_mock,
        "status": "completed",
        "raw_response": (output.raw_text or "")[:50000] or None,
        "created_at": now,
    }
    inserted = await db[Collections.MEETING_ANALYTICS].insert_one(doc)
    doc["_id"] = inserted.inserted_id
    snapshot = build_snapshot(result)
    follow_required = snapshot["follow_up_required"]
    version_count = await db[Collections.MEETING_ANALYTICS].count_documents({"meeting_id": meeting["_id"]})

    events = [timeline_event("analysis_completed", "AI Analysis Complete", "success", "gemini", ai=True,
                             details=f"Model {output.model} · prompt v{output.prompt_version}")]
    if follow_required:
        events.append(timeline_event("follow_up_required", "Follow-up Required", "warning", "gemini", ai=True,
                                     details=snapshot.get("recommended_next_action")))
    await db[Collections.MEETINGS].update_one(
        {"_id": meeting["_id"]},
        {
            "$set": {
                "analysis": {"status": "completed", "current_analysis_id": doc["_id"], "version_count": version_count,
                             "model": output.model, "prompt_version": output.prompt_version,
                             "analysis_version": ANALYSIS_VERSION, "completed_at": now, "snapshot": snapshot,
                             "is_mock": output.is_mock},
                "status.analysis_completed": True,
                "status.follow_up_required": follow_required,
                "updated_at": now,
            },
            "$push": {"timeline": {"$each": events}},
        },
    )
    await transition(meeting["_id"], MeetingState.ANALYSIS_COMPLETED)
    if follow_required:
        await transition(meeting["_id"], MeetingState.FOLLOW_UP_REQUIRED)

    await followup_service.upsert_ai_follow_up(meeting, result.get("follow_up") or {}, doc["_id"], output.follow_up_days)

    journey = [journey_event("analysis_ready", "AI Analysis Ready", "ai", meeting["_id"])]
    if snapshot.get("interest_level") and snapshot["interest_level"] != "unknown":
        journey.append(journey_event("interest_detected", f"Interest Detected: {snapshot['interest_level'].title()}", "ai", meeting["_id"]))
    if snapshot.get("main_objection"):
        journey.append(journey_event("objection", f"Objection: {snapshot['main_objection']}", "ai", meeting["_id"]))
    if follow_required:
        journey.append(journey_event("follow_up_suggested", "Follow-up Suggested", "ai", meeting["_id"],
                                     details=snapshot.get("recommended_next_action")))
    for event in journey:
        await lead_service.add_journey(meeting["lead_id"], event)
    await lead_service.set_lead_status(meeting["lead_id"], LeadStatus.FOLLOW_UP if follow_required else LeadStatus.ENGAGED)
    await refresh_flags(meeting["_id"])
    await lead_service.refresh_lead_intelligence(meeting["lead_id"])
    logger.info("analysis.completed", extra={"meeting_id": str(meeting["_id"]), "lead_id": str(meeting["lead_id"]),
                                             "model": output.model, "trigger": trigger})
    return doc
