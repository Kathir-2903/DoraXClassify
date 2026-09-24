"""Dora X Classify — Sales Intelligence API."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.database import mongodb
from app.database.mongodb import Collections
from app.middleware.error_handler import register_error_handlers
from app.routes import (
    admin,
    auth,
    dashboard,
    leads,
    meetings,
    notifications,
    search,
    settings_routes,
    webhooks,
)
from app.utils.logging_config import configure_logging
from app.workers.meeting_processor import processor

logger = logging.getLogger("app")


async def _bootstrap() -> None:
    db = mongodb.get_db()
    if settings.seed_demo_data and await db[Collections.USERS].count_documents({}) == 0:
        from app.seed import seed_demo_data

        await seed_demo_data(db)
    elif settings.bootstrap_admin_email and settings.bootstrap_admin_password and await db[Collections.USERS].count_documents({}) == 0:
        from app.models.user import new_user_document
        from app.utils.validators import normalize_email

        await db[Collections.USERS].insert_one(new_user_document(
            settings.bootstrap_admin_name, normalize_email(settings.bootstrap_admin_email),
            settings.bootstrap_admin_password, "admin"))
        logger.info("bootstrap.admin_created")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    if settings.is_production and settings.jwt_secret == "change-me-in-production":
        raise RuntimeError("JWT_SECRET must be set in production")
    await mongodb.connect()
    await _bootstrap()
    if settings.worker_enabled:
        processor.start()
    logger.info("app.started", extra={"environment": settings.app_env, "classify_mock": settings.classify_mock_mode,
                                      "gemini_mock": settings.gemini_mock_mode})
    yield
    await processor.stop()
    await mongodb.disconnect()


TAGS = [
    {"name": "Auth & Users", "description": "JWT authentication. Use **Authorize** with the token from `/api/auth/login`."},
    {"name": "Leads", "description": "Lead management and per-lead intelligence."},
    {"name": "Meetings", "description": "Classify scheduled meetings (`POST /createMS`), attendance sync (SendAttendanceDetails), invitations, transcripts, AI analysis."},
    {"name": "Webhooks", "description": "Inbound Classify callbacks. Authenticated by shared secret, not JWT."},
    {"name": "Dashboard"}, {"name": "Admin"}, {"name": "Settings"},
    {"name": "Search"}, {"name": "Notifications"},
]

app = FastAPI(
    title="Dora X Classify API",
    version="1.0.0",
    description=(
        "Meeting → Intelligence. Schedules Classify meetings, sends invitations, pulls attendance and recordings from Classify, "
        "processes recordings into transcripts and Gemini-powered sales intelligence.\n\n"
        "Errors use the envelope `{\"error\": {\"code\", \"message\", \"reason\", \"hint\"}}`."
    ),
    openapi_tags=TAGS,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    expose_headers=["Content-Disposition"],
)
register_error_handlers(app)

for module in (auth, leads, meetings, dashboard, webhooks, admin, settings_routes, search, notifications):
    app.include_router(module.router)


@app.get("/api/health", tags=["Settings"], summary="Liveness / readiness")
async def health():
    try:
        await mongodb.get_db().command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "worker": processor._task is not None}
