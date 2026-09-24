import re

from fastapi import APIRouter, Depends, Query

from app.constants.meeting_status import STATE_LABELS, MeetingState
from app.database.mongodb import Collections, get_db
from app.dependencies.auth import CurrentUser, get_current_user, scope_filter
from app.utils.serialization import serialize
from app.utils.validators import maybe_object_id

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.get("", summary="Global search across leads and meetings")
async def search(q: str = Query(..., min_length=2, max_length=100), user: CurrentUser = Depends(get_current_user)):
    db = get_db()
    pattern = re.compile(re.escape(q.strip()), re.IGNORECASE)
    digits = re.sub(r"\D", "", q)
    lead_or = [{"name": pattern}, {"email": pattern}, {"company": pattern}]
    if len(digits) >= 4:
        lead_or.append({"phone": re.compile(re.escape(digits))})
    oid = maybe_object_id(q.strip())
    if oid:
        lead_or.append({"_id": oid})
    leads = await db[Collections.LEADS].find({**scope_filter(user), "$or": lead_or},
                                             {"name": 1, "email": 1, "company": 1, "phone": 1}).limit(6).to_list(length=6)

    status_matches = [s.value for s, label in STATE_LABELS.items() if pattern.search(label) or pattern.search(s.value)]
    meeting_or = [{"label": pattern}, {"lead_snapshot.name": pattern}, {"lead_snapshot.email": pattern},
                  {"sales_person_snapshot.name": pattern}, {"classify.unique_id": q.strip()}]
    if status_matches:
        meeting_or.append({"status.overall": {"$in": status_matches}})
    if oid:
        meeting_or.append({"_id": oid})
    meetings = await db[Collections.MEETINGS].find(
        {**scope_filter(user), "status.overall": {"$ne": MeetingState.DRAFT.value}, "$or": meeting_or},
        {"label": 1, "lead_snapshot.name": 1, "schedule.start_time": 1, "status.overall": 1, "sales_person_snapshot.name": 1},
    ).sort("schedule.start_time", -1).limit(6).to_list(length=6)
    for m in meetings:
        m["status_label"] = STATE_LABELS.get(MeetingState(m["status"]["overall"]), m["status"]["overall"])
    return serialize({"leads": leads, "meetings": meetings})
