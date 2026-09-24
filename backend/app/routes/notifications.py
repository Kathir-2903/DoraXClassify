from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.database.mongodb import Collections, get_db
from app.dependencies.auth import CurrentUser, get_current_user, scope_filter
from app.utils.serialization import serialize
from app.utils.validators import maybe_object_id

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("", summary="Invitation email delivery records")
async def list_notifications(user: CurrentUser = Depends(get_current_user), meeting_id: Optional[str] = None,
                             status: Optional[str] = Query(None, pattern="^(pending|sent|delivered|failed|skipped)$"),
                             page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    q = scope_filter(user)
    if meeting_id:
        q["meeting_id"] = maybe_object_id(meeting_id)
    if status:
        q["status"] = status
    db = get_db()
    total = await db[Collections.NOTIFICATIONS].count_documents(q)
    items = await db[Collections.NOTIFICATIONS].find(q).sort("updated_at", -1).skip((page - 1) * page_size).limit(page_size).to_list(length=page_size)
    return serialize({"items": items, "total": total, "page": page, "page_size": page_size})
