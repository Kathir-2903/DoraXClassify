from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import CurrentUser, get_current_user
from app.services import analytics_service
from app.utils.serialization import serialize

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/overview", summary="KPI cards")
async def overview(user: CurrentUser = Depends(get_current_user), sales_person_id: Optional[str] = None):
    return serialize(await analytics_service.overview(user, {"sales_person_id": sales_person_id}))


@router.get("/meetings", summary="Meetings over time, status breakdown, duration distribution")
async def meetings(user: CurrentUser = Depends(get_current_user), sales_person_id: Optional[str] = None,
                   days: int = Query(30, ge=7, le=365)):
    return serialize(await analytics_service.meeting_charts(user, {"sales_person_id": sales_person_id, "days": days}))


@router.get("/engagement", summary="AI-derived engagement / interest / intent distribution")
async def engagement(user: CurrentUser = Depends(get_current_user), sales_person_id: Optional[str] = None):
    return serialize(await analytics_service.engagement_breakdown(user, {"sales_person_id": sales_person_id}))


@router.get("/followups", summary="Follow-up pipeline")
async def followups(user: CurrentUser = Depends(get_current_user), sales_person_id: Optional[str] = None):
    return serialize(await analytics_service.follow_up_pipeline(user, {"sales_person_id": sales_person_id}))


@router.get("/insights", summary="AI insight cards (only when enough data exists)")
async def insights(user: CurrentUser = Depends(get_current_user), sales_person_id: Optional[str] = None):
    return serialize(await analytics_service.ai_insights(user, {"sales_person_id": sales_person_id}))
