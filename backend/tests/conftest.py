import os

# Configure before the app (and its settings singleton) is imported.
os.environ.update({
    "APP_ENV": "test",
    "MONGO_DATABASE": "classify_test",
    "JWT_SECRET": "test-secret-key-that-is-at-least-32-bytes",
    "CLASSIFY_MOCK_MODE": "true",
    "GEMINI_MOCK_MODE": "true",
    "EMAIL_MOCK_MODE": "true",
    "WORKER_ENABLED": "false",
    "WEBHOOK_SECRET": "test-webhook-secret",
    "CLASSIFY_API_KEY": "test-partner-key",
    "CLASSIFY_AUTH_TOKEN": "test-auth-token",
    "CLASSIFY_ORG_ID": "org-test",
    "SEED_DEMO_DATA": "false",
})

from datetime import date, datetime, timedelta  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

from app.database import mongodb  # noqa: E402
from app.database.mongodb import Collections  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import new_user_document  # noqa: E402
from app.routes import auth as auth_routes  # noqa: E402
from app.utils.datetime_utils import get_zone  # noqa: E402
from app.utils.security import create_access_token  # noqa: E402


@pytest.fixture
async def db():
    database = await mongodb.connect(AsyncMongoMockClient(tz_aware=True))
    auth_routes._attempts.clear()
    yield database
    for name in await database.list_collection_names():
        await database[name].delete_many({})
    await mongodb.disconnect()


@pytest.fixture
async def users(db):
    admin = new_user_document("Admin User", "admin@classify.demo", "Admin@123", "admin")
    sales = new_user_document("Sales Person", "sales@classify.demo", "Sales@123", "sales")
    other = new_user_document("Other Sales", "other@classify.demo", "Sales@123", "sales")
    for doc in (admin, sales, other):
        doc["_id"] = (await db[Collections.USERS].insert_one(doc)).inserted_id
    return {"admin": admin, "sales": sales, "other": other}


def _client(user=None) -> httpx.AsyncClient:
    headers = {}
    if user:
        headers["Authorization"] = f"Bearer {create_access_token(str(user['_id']), user['role'])}"
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers)


@pytest.fixture
async def sales_client(users):
    async with _client(users["sales"]) as c:
        yield c


@pytest.fixture
async def admin_client(users):
    async with _client(users["admin"]) as c:
        yield c


@pytest.fixture
async def other_client(users):
    async with _client(users["other"]) as c:
        yield c


@pytest.fixture
async def anon_client(db):
    async with _client() as c:
        yield c


@pytest.fixture
async def lead(admin_client, users):
    resp = await admin_client.post("/api/leads", json={
        "name": "Rahul Kumar", "email": "rahul@example.com", "phone": "+919876543210",
        "company": "Acme", "lead_source": "Website", "interested_product": "Full Stack Development",
        "sales_person_id": str(users["sales"]["_id"]),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def future_slot(days: int = 2, hour: int = 17):
    local = datetime.now(get_zone()) + timedelta(days=days)
    return date(local.year, local.month, local.day).isoformat(), f"{hour:02d}:00"


@pytest.fixture
def schedule_body(lead):
    d, t = future_slot()
    return {"lead_id": lead["id"], "meeting_date": d, "meeting_time": t, "duration_minutes": 30, "min_duration": 1}
