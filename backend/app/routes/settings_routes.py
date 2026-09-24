from fastapi import APIRouter, Depends

from app.config.settings import settings
from app.constants.analysis_status import DEFAULT_PITCH_CHECKLIST
from app.database.mongodb import Collections, get_db
from app.dependencies.auth import CurrentUser, get_current_user
from app.schemas.lead import LEAD_SOURCES
from app.workers.analysis_worker import get_pitch_checklist

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("", summary="Integration status (no secrets), pitch checklist and form options")
async def get_settings(user: CurrentUser = Depends(get_current_user)):
    products = await get_db()[Collections.LEADS].distinct("interested_product")
    return {
        "integrations": settings.public_integration_status(),
        "pitch_checklist": await get_pitch_checklist(),
        "default_pitch_checklist": DEFAULT_PITCH_CHECKLIST,
        "lead_sources": LEAD_SOURCES,
        "products": sorted(p for p in products if p),
        "defaults": {"duration_minutes": settings.classify_default_duration_minutes,
                     "min_duration": settings.classify_default_min_duration, "timezone": settings.classify_timezone},
        "mock_mode": settings.classify_mock_mode,
    }
