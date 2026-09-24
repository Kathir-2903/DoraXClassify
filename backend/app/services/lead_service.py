"""Lead management and per-lead intelligence roll-ups."""
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from app.constants.analysis_status import FollowUpStatus, LeadStatus, Role
from app.constants.meeting_status import STATE_LABELS, MeetingState
from app.database.mongodb import Collections, get_db
from app.dependencies.auth import CurrentUser, ensure_owner, scope_filter
from app.middleware.error_handler import AppError, NotFoundError
from app.models.lead import empty_intelligence, new_lead_document
from app.services.audit_service import log_activity
from app.utils.datetime_utils import parse_datetime, utcnow
from app.utils.validators import maybe_object_id, to_object_id

SORTABLE = {
    "name": "name",
    "email": "email",
    "company": "company",
    "created_at": "created_at",
    "last_activity": "last_activity_at",
    "last_meeting": "intelligence.last_meeting_at",
    "meetings": "intelligence.meetings_count",
    "last_duration": "intelligence.last_duration_seconds",
    "interest": "intelligence.interest_level",
    "intent": "intelligence.purchase_intent",
    "lead_status": "lead_status",
}

MANUAL_STATUSES = {LeadStatus.WON.value, LeadStatus.LOST.value}


async def _sales_person_map(ids: Optional[List[ObjectId]] = None) -> Dict[ObjectId, Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if ids is not None:
        query["_id"] = {"$in": list(set(ids))}
    users = await get_db()[Collections.USERS].find(query, {"name": 1, "email": 1}).to_list(length=None)
    return {u["_id"]: u for u in users}


async def resolve_sales_person(user: CurrentUser, requested_id: Optional[str]) -> Dict[str, Any]:
    """Only admins create/reassign leads, and only to an active sales user —
    a lead can't be left assigned to an admin, since admins can't schedule
    meetings to work it."""
    if not user.is_admin:
        return dict(user)
    oid = maybe_object_id(requested_id)
    sp = await get_db()[Collections.USERS].find_one(
        {"_id": oid, "is_active": True, "role": Role.SALES.value}) if oid else None
    if not sp:
        raise AppError("Select a sales person to assign this lead to", 422, "invalid_sales_person")
    return sp


async def _ensure_unique(email: Optional[str], phone: Optional[str], exclude_id: Optional[ObjectId] = None) -> None:
    db = get_db()
    ors = []
    if email:
        ors.append({"email": email})
    if phone:
        ors.append({"phone": phone})
    if not ors:
        return
    query: Dict[str, Any] = {"$or": ors}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    existing = await db[Collections.LEADS].find_one(query, {"email": 1, "phone": 1, "name": 1})
    if existing:
        field = "email" if email and existing.get("email") == email else "phone"
        raise AppError(
            f"A lead with this {field} already exists",
            409,
            "duplicate_lead",
            reason=f"{existing.get('name')} already uses this {field}.",
            details={"field": field, "existing_lead_id": str(existing["_id"])},
        )


async def create_lead(user: CurrentUser, data: Dict[str, Any]) -> Dict[str, Any]:
    sales_person = await resolve_sales_person(user, data.pop("sales_person_id", None))
    await _ensure_unique(data["email"], data["phone"])
    doc = new_lead_document(data, sales_person["_id"], user["_id"])
    try:
        result = await get_db()[Collections.LEADS].insert_one(doc)
    except DuplicateKeyError:
        raise AppError("A lead with this email already exists", 409, "duplicate_lead")
    doc["_id"] = result.inserted_id
    await log_activity(user, "lead.created", "lead", doc["_id"], {"name": doc["name"]})
    return await decorate_lead(doc)


async def get_lead_for_user(user: CurrentUser, lead_id: str) -> Dict[str, Any]:
    lead = await get_db()[Collections.LEADS].find_one({"_id": to_object_id(lead_id, "lead id")})
    if not lead:
        raise NotFoundError("Lead")
    ensure_owner(user, lead)
    return lead


async def decorate_lead(lead: Dict[str, Any], sp_map: Optional[Dict[ObjectId, Dict[str, Any]]] = None) -> Dict[str, Any]:
    if sp_map is None:
        sp_map = await _sales_person_map([lead["sales_person_id"]])
    sp = sp_map.get(lead.get("sales_person_id")) or {}
    lead = dict(lead)
    lead["sales_person"] = {"id": str(sp["_id"]), "name": sp.get("name"), "email": sp.get("email")} if sp else None
    status = (lead.get("intelligence") or {}).get("last_meeting_status")
    lead["last_meeting_status_label"] = STATE_LABELS.get(MeetingState(status)) if status in MeetingState._value2member_map_ else None
    return lead


async def update_lead(user: CurrentUser, lead_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    lead = await get_lead_for_user(user, lead_id)
    changes = {k: v for k, v in data.items() if v is not None}
    if "sales_person_id" in changes:
        if not user.is_admin:
            changes.pop("sales_person_id")
        else:
            sp = await resolve_sales_person(user, changes["sales_person_id"])
            changes["sales_person_id"] = sp["_id"]
    await _ensure_unique(changes.get("email"), changes.get("phone"), exclude_id=lead["_id"])
    if not changes:
        return await decorate_lead(lead)
    changes["updated_at"] = utcnow()
    changes["last_activity_at"] = changes["updated_at"]
    try:
        await get_db()[Collections.LEADS].update_one({"_id": lead["_id"]}, {"$set": changes})
    except DuplicateKeyError:
        raise AppError("A lead with this email already exists", 409, "duplicate_lead")
    await log_activity(user, "lead.updated", "lead", lead["_id"], {"fields": sorted(k for k in changes if k not in ("updated_at", "last_activity_at"))})
    updated = await get_db()[Collections.LEADS].find_one({"_id": lead["_id"]})
    return await decorate_lead(updated)


async def delete_lead(user: CurrentUser, lead_id: str) -> None:
    lead = await get_lead_for_user(user, lead_id)
    db = get_db()
    if await db[Collections.MEETINGS].count_documents({"lead_id": lead["_id"]}, limit=1):
        raise AppError(
            "This lead has meeting history and cannot be deleted",
            409,
            "lead_has_meetings",
            hint="Mark the lead as Lost instead to keep the sales history.",
        )
    await db[Collections.LEADS].delete_one({"_id": lead["_id"]})
    await db[Collections.FOLLOW_UPS].delete_many({"lead_id": lead["_id"]})
    await log_activity(user, "lead.deleted", "lead", lead["_id"], {"name": lead.get("name")})


def build_lead_query(user: CurrentUser, params: Dict[str, Any]) -> Dict[str, Any]:
    query: Dict[str, Any] = scope_filter(user, requested=params.get("sales_person_id"))
    q = (params.get("q") or "").strip()
    if q:
        pattern = re.compile(re.escape(q), re.IGNORECASE)
        digits = re.sub(r"\D", "", q)
        ors: List[Dict[str, Any]] = [{"name": pattern}, {"email": pattern}, {"company": pattern}]
        if len(digits) >= 4:
            ors.append({"phone": re.compile(re.escape(digits))})
        query["$or"] = ors
    if params.get("lead_status"):
        query["lead_status"] = params["lead_status"]
    if params.get("meeting_status"):
        query["intelligence.last_meeting_status"] = params["meeting_status"]
    if params.get("interest"):
        query["intelligence.interest_level"] = params["interest"]
    if params.get("intent"):
        query["intelligence.purchase_intent"] = params["intent"]
    if params.get("follow_up") in ("true", "false", True, False):
        query["intelligence.follow_up_required"] = params["follow_up"] in ("true", True)
    if params.get("lead_source"):
        query["lead_source"] = params["lead_source"]
    created: Dict[str, Any] = {}
    if params.get("date_from"):
        created["$gte"] = parse_datetime(params["date_from"])
    if params.get("date_to"):
        end = parse_datetime(params["date_to"])
        if end and len(str(params["date_to"])) <= 10:
            end = end + timedelta(days=1)
        created["$lt"] = end
    if created:
        query["created_at"] = {k: v for k, v in created.items() if v is not None}
    return query


async def list_leads(user: CurrentUser, params: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    query = build_lead_query(user, params)
    page = max(int(params.get("page") or 1), 1)
    page_size = min(max(int(params.get("page_size") or 20), 1), 100)
    sort_field = SORTABLE.get(params.get("sort") or "last_activity", "last_activity_at")
    direction = ASCENDING if params.get("order") == "asc" else DESCENDING
    total = await db[Collections.LEADS].count_documents(query)
    cursor = (
        db[Collections.LEADS]
        .find(query, {"journey": 0})
        .sort([(sort_field, direction), ("_id", direction)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    leads = await cursor.to_list(length=page_size)
    sp_map = await _sales_person_map([l["sales_person_id"] for l in leads])
    items = [await decorate_lead(l, sp_map) for l in leads]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def iter_leads_for_export(user: CurrentUser, params: Dict[str, Any]):
    db = get_db()
    query = build_lead_query(user, params)
    sp_map = await _sales_person_map()
    async for lead in db[Collections.LEADS].find(query, {"journey": 0}).sort("created_at", DESCENDING):
        yield await decorate_lead(lead, sp_map)


async def add_journey(lead_id: ObjectId, event: Dict[str, Any], touch: bool = True) -> None:
    update: Dict[str, Any] = {"$push": {"journey": event}}
    if touch:
        update["$set"] = {"last_activity_at": utcnow()}
    await get_db()[Collections.LEADS].update_one({"_id": lead_id}, update)


async def set_lead_status(lead_id: ObjectId, status: LeadStatus) -> None:
    await get_db()[Collections.LEADS].update_one(
        {"_id": lead_id, "lead_status": {"$nin": list(MANUAL_STATUSES)}},
        {"$set": {"lead_status": status.value, "updated_at": utcnow()}},
    )


async def refresh_lead_intelligence(lead_id: ObjectId) -> Dict[str, Any]:
    """Recompute the lead roll-up from stored meetings/analyses only."""
    db = get_db()
    meetings = await db[Collections.MEETINGS].find(
        {"lead_id": lead_id, "status.overall": {"$ne": MeetingState.DRAFT.value}},
        {"schedule": 1, "status": 1, "attendance": 1, "analysis": 1, "processing": 1},
    ).sort("schedule.start_time", DESCENDING).to_list(length=None)

    intel = empty_intelligence()
    intel["meetings_count"] = len(meetings)
    completed = [m for m in meetings if m["status"].get("meeting_completed") and not m["status"].get("no_show")]
    intel["completed_meetings"] = len(completed)
    intel["no_shows"] = sum(1 for m in meetings if m["status"].get("no_show"))
    durations = [m["attendance"]["duration_seconds"] for m in completed if (m.get("attendance") or {}).get("duration_seconds")]
    intel["total_duration_seconds"] = int(sum(durations))
    intel["average_duration_seconds"] = int(sum(durations) / len(durations)) if durations else None

    if meetings:
        latest = meetings[0]
        intel["last_meeting_id"] = latest["_id"]
        intel["last_meeting_at"] = latest["schedule"]["start_time"]
        intel["last_meeting_status"] = latest["status"]["overall"]
        intel["last_duration_seconds"] = (latest.get("attendance") or {}).get("duration_seconds")
        st = latest["status"]
        if st.get("analysis_completed"):
            intel["analysis_status"] = "completed"
        elif st.get("no_show"):
            intel["analysis_status"] = "skipped"
        elif st.get("meeting_completed"):
            intel["analysis_status"] = latest.get("processing", {}).get("analysis", {}).get("status")
        # Upcoming meetings have no analysis status yet (left as None).

    analysed = [m for m in meetings if (m.get("analysis") or {}).get("snapshot")]
    if analysed:
        snap = analysed[0]["analysis"]["snapshot"]
        intel["interest_level"] = snap.get("interest_level")
        intel["purchase_intent"] = snap.get("purchase_intent")
        intel["engagement_level"] = snap.get("engagement_level")
        intel["main_concern"] = snap.get("main_objection")
        intel["next_action"] = snap.get("recommended_next_action")

    follow = await db[Collections.FOLLOW_UPS].find_one(
        {"lead_id": lead_id, "status": {"$in": [FollowUpStatus.PENDING.value, FollowUpStatus.SNOOZED.value]}},
        sort=[("due_date", ASCENDING)],
    )
    intel["follow_up_required"] = bool(follow)
    intel["follow_up_due"] = follow.get("due_date") if follow else None
    if follow and not intel["next_action"]:
        intel["next_action"] = follow.get("recommended_action")
    intel["updated_at"] = utcnow()
    await db[Collections.LEADS].update_one({"_id": lead_id}, {"$set": {"intelligence": intel}})
    return intel


async def lead_analytics(user: CurrentUser, lead_id: str) -> Dict[str, Any]:
    lead = await get_lead_for_user(user, lead_id)
    db = get_db()
    meetings = await db[Collections.MEETINGS].find(
        {"lead_id": lead["_id"], "status.overall": {"$ne": MeetingState.DRAFT.value}},
        {"raw_classify_response": 0, "timeline": 0},
    ).sort("schedule.start_time", ASCENDING).to_list(length=None)

    history = []
    objections_over_time = []
    for idx, m in enumerate(meetings, start=1):
        snap = (m.get("analysis") or {}).get("snapshot") or {}
        history.append(
            {
                "meeting_id": m["_id"],
                "sequence": idx,
                "label": f"Meeting {idx}",
                "start_time": m["schedule"]["start_time"],
                "status": m["status"]["overall"],
                "duration_seconds": (m.get("attendance") or {}).get("duration_seconds"),
                "interest_level": snap.get("interest_level"),
                "purchase_intent": snap.get("purchase_intent"),
                "engagement_level": snap.get("engagement_level"),
                "objection_categories": snap.get("objection_categories") or [],
                "follow_up_required": snap.get("follow_up_required"),
                "analysis_available": bool(snap),
            }
        )
        if snap:
            objections_over_time.append(
                {"meeting_id": m["_id"], "label": f"Meeting {idx}", "start_time": m["schedule"]["start_time"],
                 "objections": snap.get("objections") or []}
            )

    follow_ups = await db[Collections.FOLLOW_UPS].find({"lead_id": lead["_id"]}).sort("created_at", DESCENDING).to_list(length=100)
    completed = [h for h in history if h["duration_seconds"]]
    return {
        "lead_id": lead["_id"],
        "intelligence": lead.get("intelligence") or empty_intelligence(),
        "summary": {
            "total_meetings": len(history),
            "completed_meetings": sum(1 for m in meetings if m["status"].get("meeting_completed") and not m["status"].get("no_show")),
            "no_shows": sum(1 for m in meetings if m["status"].get("no_show")),
            "total_conversation_seconds": int(sum(h["duration_seconds"] for h in completed)) if completed else 0,
            "average_duration_seconds": int(sum(h["duration_seconds"] for h in completed) / len(completed)) if completed else None,
            "first_interaction": history[0]["start_time"] if history else None,
            "latest_interaction": history[-1]["start_time"] if history else None,
            "open_follow_ups": sum(1 for f in follow_ups if f["status"] != FollowUpStatus.COMPLETED.value),
        },
        "history": history,
        "objections_over_time": objections_over_time,
        "follow_up_history": follow_ups,
        "journey": sorted(lead.get("journey") or [], key=lambda e: e.get("at") or utcnow()),
    }


async def list_sales_people(active_only: bool = True) -> List[Dict[str, Any]]:
    """Only sales users schedule meetings, so leads may only be assigned to them."""
    query: Dict[str, Any] = {"role": Role.SALES.value}
    if active_only:
        query["is_active"] = True
    users = await get_db()[Collections.USERS].find(query, {"password_hash": 0}).sort("name", ASCENDING).to_list(length=None)
    return users
