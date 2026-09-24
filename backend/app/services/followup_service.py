"""AI-suggested follow-ups, derived from meeting analysis."""
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Optional

from bson import ObjectId

from app.constants.analysis_status import FollowUpStatus
from app.database.mongodb import Collections, get_db
from app.utils.datetime_utils import get_zone, utcnow


def due_from_timing(meeting_end: datetime, suggested_date: Optional[str], timing: str, days: Optional[int] = None) -> datetime:
    """Resolve the AI's suggested timing into a concrete due date (10:00 local)."""
    zone = get_zone()
    base = meeting_end.astimezone(zone).date()
    target: Optional[date] = None
    if suggested_date:
        try:
            target = date.fromisoformat(suggested_date[:10])
        except ValueError:
            target = None
    if target is None:
        if days is None:
            t = (timing or "").lower()
            m = re.search(r"(\d+)\s*(hour|day|week)", t)
            if "today" in t or ("hour" in t and (m is None or int(m.group(1)) < 24)):
                days = 0
            elif m:
                n = int(m.group(1))
                days = n * 7 if m.group(2) == "week" else (max(1, n // 24) if m.group(2) == "hour" else n)
            elif "tomorrow" in t or "24" in t:
                days = 1
            elif "week" in t:
                days = 7
            else:
                days = 1
        target = base + timedelta(days=days)
    return datetime.combine(target, time(10, 0)).replace(tzinfo=zone).astimezone(meeting_end.tzinfo or zone)


async def upsert_ai_follow_up(meeting: Dict[str, Any], follow_up: Dict[str, Any], analysis_id: ObjectId,
                              days: Optional[int] = None) -> Optional[ObjectId]:
    db = get_db()
    existing = await db[Collections.FOLLOW_UPS].find_one(
        {"meeting_id": meeting["_id"], "source": "ai", "status": {"$ne": FollowUpStatus.COMPLETED.value}}
    )
    if not follow_up.get("required"):
        if existing:
            await db[Collections.FOLLOW_UPS].update_one(
                {"_id": existing["_id"]},
                {"$set": {"status": FollowUpStatus.COMPLETED.value, "completed_at": utcnow(),
                          "resolution": "No longer required after re-analysis"}},
            )
        return None
    end = (meeting.get("attendance") or {}).get("actual_end") or meeting["schedule"]["end_time"]
    due = due_from_timing(end, follow_up.get("suggested_follow_up_date"), follow_up.get("suggested_timing", ""), days)
    fields = {
        "reason": follow_up.get("reason") or "Follow-up recommended",
        "recommended_action": follow_up.get("recommended_next_action") or "Follow up with the lead",
        "suggested_timing": follow_up.get("suggested_timing"),
        "analysis_id": analysis_id,
        "updated_at": utcnow(),
    }
    if existing:
        await db[Collections.FOLLOW_UPS].update_one({"_id": existing["_id"]}, {"$set": fields})
        return existing["_id"]
    doc = {
        **fields,
        "lead_id": meeting["lead_id"],
        "meeting_id": meeting["_id"],
        "owner_id": meeting["sales_person_id"],
        "lead_name": meeting["lead_snapshot"].get("name"),
        "meeting_label": meeting.get("label"),
        "due_date": due,
        "status": FollowUpStatus.PENDING.value,
        "source": "ai",
        "ai_generated": True,
        "notes": [],
        "snoozed_until": None,
        "completed_at": None,
        "is_demo": meeting.get("is_demo", False),
        "created_at": utcnow(),
    }
    result = await db[Collections.FOLLOW_UPS].insert_one(doc)
    return result.inserted_id


async def wake_snoozed() -> int:
    result = await get_db()[Collections.FOLLOW_UPS].update_many(
        {"status": FollowUpStatus.SNOOZED.value, "snoozed_until": {"$lte": utcnow()}},
        {"$set": {"status": FollowUpStatus.PENDING.value}},
    )
    return result.modified_count
