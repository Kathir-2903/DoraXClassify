"""MongoDB connection management and index creation."""
import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.config.settings import settings

logger = logging.getLogger(__name__)


class Collections:
    USERS = "users"
    LEADS = "leads"
    MEETINGS = "meetings"
    MEETING_RECORDINGS = "meeting_recordings"
    MEETING_TRANSCRIPTS = "meeting_transcripts"
    MEETING_ANALYTICS = "meeting_analytics"
    NOTIFICATIONS = "notifications"
    WEBHOOK_EVENTS = "webhook_events"
    ACTIVITY_LOGS = "activity_logs"
    DASHBOARD_SNAPSHOTS = "dashboard_snapshots"
    FOLLOW_UPS = "follow_ups"
    APP_SETTINGS = "app_settings"


_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


async def connect(client: Optional[AsyncIOMotorClient] = None) -> AsyncIOMotorDatabase:
    """Connect to MongoDB. Tests pass a mongomock-motor client."""
    global _client, _db
    _client = client or AsyncIOMotorClient(settings.mongo_uri, tz_aware=True, uuidRepresentation="standard")
    _db = _client[settings.mongo_database]
    await ensure_indexes(_db)
    logger.info("mongodb.connected", extra={"database": settings.mongo_database})
    return _db


async def disconnect() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialised; call connect() first")
    return _db


INDEXES = {
    Collections.USERS: [
        IndexModel([("email", ASCENDING)], unique=True),
        IndexModel([("role", ASCENDING)]),
    ],
    Collections.LEADS: [
        IndexModel([("email", ASCENDING)], unique=True),
        IndexModel([("phone", ASCENDING)]),
        IndexModel([("sales_person_id", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
        IndexModel([("last_activity_at", DESCENDING)]),
        IndexModel([("lead_status", ASCENDING)]),
        IndexModel([("name", "text"), ("email", "text"), ("company", "text")], name="lead_text"),
    ],
    Collections.MEETINGS: [
        IndexModel([("lead_id", ASCENDING), ("schedule.start_time", DESCENDING)]),
        IndexModel([("sales_person_id", ASCENDING)]),
        IndexModel([("classify.unique_id", ASCENDING)], sparse=True),
        IndexModel([("schedule.start_time", DESCENDING)]),
        IndexModel([("status.overall", ASCENDING)]),
        IndexModel([("idempotency_key", ASCENDING)], unique=True, sparse=True),
        IndexModel([("processing.recording.status", ASCENDING)]),
        IndexModel([("processing.transcript.status", ASCENDING)]),
        IndexModel([("processing.analysis.status", ASCENDING)]),
    ],
    Collections.MEETING_RECORDINGS: [IndexModel([("meeting_id", ASCENDING)], unique=True)],
    Collections.MEETING_TRANSCRIPTS: [IndexModel([("meeting_id", ASCENDING)], unique=True)],
    Collections.MEETING_ANALYTICS: [
        IndexModel([("meeting_id", ASCENDING), ("created_at", DESCENDING)]),
        IndexModel([("meeting_id", ASCENDING), ("is_current", ASCENDING)]),
        IndexModel([("lead_id", ASCENDING)]),
    ],
    Collections.NOTIFICATIONS: [
        IndexModel([("meeting_id", ASCENDING), ("channel", ASCENDING)]),
        IndexModel([("status", ASCENDING), ("next_retry_at", ASCENDING)]),
    ],
    Collections.WEBHOOK_EVENTS: [
        IndexModel([("event_id", ASCENDING)], unique=True),
        IndexModel([("meeting_id", ASCENDING)]),
        IndexModel([("received_at", DESCENDING)]),
    ],
    Collections.ACTIVITY_LOGS: [
        IndexModel([("resource", ASCENDING), ("resource_id", ASCENDING)]),
        IndexModel([("user_id", ASCENDING)]),
        IndexModel([("timestamp", DESCENDING)]),
    ],
    Collections.FOLLOW_UPS: [
        IndexModel([("owner_id", ASCENDING), ("status", ASCENDING), ("due_date", ASCENDING)]),
        IndexModel([("lead_id", ASCENDING)]),
        IndexModel([("meeting_id", ASCENDING)]),
    ],
    Collections.DASHBOARD_SNAPSHOTS: [IndexModel([("key", ASCENDING)], unique=True)],
    Collections.APP_SETTINGS: [IndexModel([("key", ASCENDING)], unique=True)],
}


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    for name, indexes in INDEXES.items():
        try:
            await db[name].create_indexes(indexes)
        except Exception as exc:  # mongomock lacks text indexes; never block startup
            logger.warning("mongodb.index_failed", extra={"collection": name, "error": str(exc)})
            for index in indexes:
                try:
                    await db[name].create_indexes([index])
                except Exception:
                    continue
