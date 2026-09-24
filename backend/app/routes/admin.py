from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.constants.analysis_status import Role, Stage, StageStatus
from app.constants.meeting_status import MeetingState
from app.database.mongodb import Collections, get_db
from app.dependencies.auth import CurrentUser, require_admin
from app.middleware.error_handler import AppError, NotFoundError
from app.services import webhook_service
from app.services.audit_service import log_activity
from app.utils.serialization import serialize
from app.utils.validators import maybe_object_id, to_object_id
from app.workers.meeting_processor import processor, retry_stage

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/overview", summary="Platform-wide counts")
async def overview(admin: CurrentUser = Depends(require_admin)):
    db = get_db()
    return serialize({
        "leads": await db[Collections.LEADS].count_documents({}),
        "sales_people": await db[Collections.USERS].count_documents({"role": Role.SALES.value, "is_active": True}),
        "meetings": await db[Collections.MEETINGS].count_documents({"status.overall": {"$ne": MeetingState.DRAFT.value}}),
        "recordings": await db[Collections.MEETINGS].count_documents({"status.recording_available": True}),
        "transcripts": await db[Collections.MEETING_TRANSCRIPTS].count_documents({}),
        "analyses": await db[Collections.MEETING_ANALYTICS].count_documents({}),
        "webhook_events": await db[Collections.WEBHOOK_EVENTS].count_documents({}),
        "webhook_errors": await db[Collections.WEBHOOK_EVENTS].count_documents({"processing_status": {"$in": ["failed", "unmatched"]}}),
        "failed_processing": await db[Collections.MEETINGS].count_documents(
            {"$or": [{f"processing.{s.value}.status": StageStatus.FAILED.value} for s in Stage]}),
        "notification_failures": await db[Collections.NOTIFICATIONS].count_documents({"status": "failed"}),
    })


@router.get("/webhooks", summary="Webhook events")
async def webhooks(admin: CurrentUser = Depends(require_admin), status: Optional[str] = None,
                   meeting_id: Optional[str] = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    db = get_db()
    q = {}
    if status:
        q["processing_status"] = status
    if meeting_id:
        q["meeting_id"] = maybe_object_id(meeting_id)
    total = await db[Collections.WEBHOOK_EVENTS].count_documents(q)
    items = await db[Collections.WEBHOOK_EVENTS].find(q).sort("received_at", -1).skip((page - 1) * page_size).limit(page_size).to_list(length=page_size)
    return serialize({"items": items, "total": total, "page": page, "page_size": page_size})


@router.post("/webhooks/{event_id}/reprocess", summary="Reprocess a webhook event")
async def reprocess_webhook(event_id: str, admin: CurrentUser = Depends(require_admin)):
    db = get_db()
    event = await db[Collections.WEBHOOK_EVENTS].find_one({"_id": to_object_id(event_id, "event id")})
    if not event:
        raise NotFoundError("Webhook event")
    await db[Collections.WEBHOOK_EVENTS].update_one({"_id": event["_id"]}, {"$set": {"processing_status": "pending"}})
    status = await webhook_service.process_event(event["event_id"])
    processor.wake()
    await log_activity(admin, "webhook.reprocess", "webhook_event", event["_id"], {"result": status})
    return serialize(await db[Collections.WEBHOOK_EVENTS].find_one({"_id": event["_id"]}))


@router.get("/processing", summary="Processing monitor")
async def processing(admin: CurrentUser = Depends(require_admin),
                     filter: str = Query("attention", pattern="^(attention|failed|processing|all)$"),
                     sales_person_id: Optional[str] = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    db = get_db()
    meetings = db[Collections.MEETINGS]
    cards = {
        "recordings_processing": await meetings.count_documents({"processing.recording.status": StageStatus.PROCESSING.value}),
        "transcripts_processing": await meetings.count_documents({"processing.transcript.status": StageStatus.PROCESSING.value}),
        "analysis_processing": await meetings.count_documents({"processing.analysis.status": StageStatus.PROCESSING.value}),
        "queued": await meetings.count_documents({"processing.active": True}),
        "failed_jobs": await meetings.count_documents({"$or": [{f"processing.{s.value}.status": StageStatus.FAILED.value} for s in Stage]}),
        "webhook_errors": await db[Collections.WEBHOOK_EVENTS].count_documents({"processing_status": {"$in": ["failed", "unmatched"]}}),
    }
    stage_filter = {
        "failed": [StageStatus.FAILED.value],
        "processing": [StageStatus.PROCESSING.value, StageStatus.PENDING.value],
        "attention": [StageStatus.FAILED.value, StageStatus.PROCESSING.value],
    }.get(filter)
    q = {"status.meeting_completed": True, "status.no_show": {"$ne": True}}
    if stage_filter:
        q["$or"] = [{f"processing.{s.value}.status": {"$in": stage_filter}} for s in Stage]
        if filter == "processing":
            q["processing.active"] = True
    if sales_person_id:
        q["sales_person_id"] = maybe_object_id(sales_person_id)
    total = await meetings.count_documents(q)
    rows = await meetings.find(q, {"label": 1, "lead_snapshot": 1, "sales_person_snapshot": 1, "processing": 1, "status": 1,
                                   "lead_id": 1, "updated_at": 1, "is_demo": 1}).sort("updated_at", -1).skip(
        (page - 1) * page_size).limit(page_size).to_list(length=page_size)
    items = []
    for m in rows:
        proc = m.get("processing") or {}
        current = next((s for s in Stage if proc.get(s.value, {}).get("status") in (StageStatus.FAILED.value, StageStatus.PROCESSING.value)),
                       next((s for s in Stage if proc.get(s.value, {}).get("status") == StageStatus.PENDING.value), Stage.ANALYSIS))
        stage = proc.get(current.value, {})
        items.append({
            "meeting_id": m["_id"], "label": m.get("label"), "lead": m["lead_snapshot"].get("name"), "lead_id": m["lead_id"],
            "sales_person": m["sales_person_snapshot"].get("name"), "stage": current.value, "status": stage.get("status"),
            "started_at": stage.get("started_at"), "attempts": stage.get("attempt_count", 0), "last_error": stage.get("error_message"),
            "next_retry_at": stage.get("next_retry_at"),
            "stages": {s.value: proc.get(s.value, {}).get("status") for s in Stage}, "is_demo": m.get("is_demo", False),
        })
    return serialize({"cards": cards, "items": items, "total": total, "page": page, "page_size": page_size})


@router.post("/processing/{meeting_id}/retry", summary="Retry a processing stage")
async def retry(meeting_id: str, stage: Stage = Query(...), admin: CurrentUser = Depends(require_admin)):
    m = await get_db()[Collections.MEETINGS].find_one({"_id": to_object_id(meeting_id, "meeting id")}, {"status": 1})
    if not m:
        raise NotFoundError("Meeting")
    if not m["status"].get("meeting_completed") or m["status"].get("no_show"):
        raise AppError("This meeting has nothing to process", 409, "nothing_to_process")
    await retry_stage(m["_id"], stage)
    await log_activity(admin, "processing.retry", "meeting", m["_id"], {"stage": stage.value})
    return {"queued": True, "stage": stage.value}


@router.get("/activity", summary="Audit log")
async def activity(admin: CurrentUser = Depends(require_admin), user_id: Optional[str] = None,
                   resource: Optional[str] = None, action: Optional[str] = None,
                   page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    db = get_db()
    q = {}
    if user_id:
        q["user_id"] = maybe_object_id(user_id)
    if resource:
        q["resource"] = resource
    if action:
        q["action"] = action
    total = await db[Collections.ACTIVITY_LOGS].count_documents(q)
    items = await db[Collections.ACTIVITY_LOGS].find(q).sort("timestamp", -1).skip((page - 1) * page_size).limit(page_size).to_list(length=page_size)
    return serialize({"items": items, "total": total, "page": page, "page_size": page_size})
