from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.dependencies.auth import CurrentUser, get_current_user, require_admin
from app.schemas.lead import LeadCreate, LeadUpdate
from app.services import lead_service, meeting_service, report_service
from app.services.audit_service import log_activity
from app.utils.datetime_utils import utcnow
from app.utils.serialization import serialize

router = APIRouter(prefix="/api/leads", tags=["Leads"])


def _filters(q, sales_person_id, meeting_status, lead_status, interest, intent, follow_up, lead_source, date_from, date_to):
    return {"q": q, "sales_person_id": sales_person_id, "meeting_status": meeting_status, "lead_status": lead_status,
            "interest": interest, "intent": intent, "follow_up": follow_up, "lead_source": lead_source,
            "date_from": date_from, "date_to": date_to}


@router.post("", status_code=201, summary="Create a lead (admin only)",
             responses={409: {"description": "Duplicate email or phone"}, 422: {"description": "Validation error"}})
async def create_lead(body: LeadCreate, user: CurrentUser = Depends(require_admin)):
    return serialize(await lead_service.create_lead(user, body.model_dump()))


@router.get("", summary="List leads (search, filter, sort, paginate)")
async def list_leads(
    user: CurrentUser = Depends(get_current_user),
    q: Optional[str] = Query(None, description="Name, email, phone or company"),
    sales_person_id: Optional[str] = None,
    meeting_status: Optional[str] = None,
    lead_status: Optional[str] = None,
    interest: Optional[str] = Query(None, pattern="^(high|medium|low|unknown)$"),
    intent: Optional[str] = Query(None, pattern="^(high|medium|low|unknown)$"),
    follow_up: Optional[str] = Query(None, pattern="^(true|false)$"),
    lead_source: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort: Optional[str] = Query("last_activity"),
    order: Optional[str] = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    params = _filters(q, sales_person_id, meeting_status, lead_status, interest, intent, follow_up, lead_source, date_from, date_to)
    params.update({"sort": sort, "order": order, "page": page, "page_size": page_size})
    return serialize(await lead_service.list_leads(user, params))


@router.get("/export.csv", summary="Export leads as CSV (respects filters)")
async def export_leads(
    user: CurrentUser = Depends(get_current_user),
    q: Optional[str] = None, sales_person_id: Optional[str] = None, meeting_status: Optional[str] = None,
    lead_status: Optional[str] = None, interest: Optional[str] = None, intent: Optional[str] = None,
    follow_up: Optional[str] = None, lead_source: Optional[str] = None, date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    params = _filters(q, sales_person_id, meeting_status, lead_status, interest, intent, follow_up, lead_source, date_from, date_to)
    await log_activity(user, "export.leads", "lead", None, {"filters": {k: v for k, v in params.items() if v}})

    async def rows():
        async for lead in lead_service.iter_leads_for_export(user, params):
            yield report_service.lead_row(lead)

    filename = f"classify-leads-{utcnow():%Y%m%d-%H%M}.csv"
    return StreamingResponse(report_service.csv_stream(report_service.LEAD_HEADER, rows()), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{lead_id}", summary="Get a lead")
async def get_lead(lead_id: str, user: CurrentUser = Depends(get_current_user)):
    lead = await lead_service.get_lead_for_user(user, lead_id)
    return serialize(await lead_service.decorate_lead(lead))


@router.put("/{lead_id}", summary="Update a lead (admin only)")
async def update_lead(lead_id: str, body: LeadUpdate, user: CurrentUser = Depends(require_admin)):
    return serialize(await lead_service.update_lead(user, lead_id, body.model_dump(exclude_unset=True)))


@router.delete("/{lead_id}", status_code=204, summary="Delete a lead without meeting history (admin only)")
async def delete_lead(lead_id: str, user: CurrentUser = Depends(require_admin)):
    await lead_service.delete_lead(user, lead_id)


@router.get("/{lead_id}/analytics", summary="Lead analytics, history and journey")
async def lead_analytics(lead_id: str, user: CurrentUser = Depends(get_current_user)):
    return serialize(await lead_service.lead_analytics(user, lead_id))


@router.get("/{lead_id}/meetings", summary="Meetings for a lead")
async def lead_meetings(lead_id: str, user: CurrentUser = Depends(get_current_user),
                        page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    await lead_service.get_lead_for_user(user, lead_id)
    return serialize(await meeting_service.list_meetings(user, {"lead_id": lead_id, "page": page, "page_size": page_size}))
