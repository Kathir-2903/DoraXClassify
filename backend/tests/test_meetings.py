from app.config.settings import settings
from app.database.mongodb import Collections
from tests.conftest import future_slot


async def test_admin_cannot_schedule_meetings(admin_client, schedule_body):
    resp = await admin_client.post("/api/meetings/schedule", json=schedule_body)
    assert resp.status_code == 403


async def test_schedule_meeting_happy_path(sales_client, schedule_body, db):
    resp = await sales_client.post("/api/meetings/schedule", json=schedule_body)
    assert resp.status_code == 201, resp.text
    m = resp.json()
    assert m["status"]["overall"] == "INVITATION_SENT"
    assert m["status"]["meeting_created"] is True
    assert m["notifications"]["email"]["status"] == "sent"
    assert m["classify"]["unique_id"]
    assert m["classify"]["meeting_type"] == "open"  # guest mode is on by default
    assert m["schedule"]["duration_minutes"] == 30 and m["schedule"]["min_duration"] == 1
    assert {"MEETING_SCHEDULED", "EMAIL_SENT", "INVITATION_SENT"} <= set(m["flags"])
    assert [s["key"] for s in m["journey"]][:2] == ["scheduled", "invited"]

    stored = await db[Collections.MEETINGS].find_one({})
    raw = stored["raw_classify_response"]
    assert raw["Details"]["UniqueId"] == m["classify"]["unique_id"]
    assert raw["Details"]["AuthToken"] == "***"  # echoed credential is masked, everything else kept
    assert raw["Details"]["MeetProvider"] == "100ms"
    # 17:00 Asia/Kolkata == 11:30 UTC
    assert stored["schedule"]["start_time"].strftime("%H:%M") == "11:30"
    lead = await db[Collections.LEADS].find_one({})
    assert lead["lead_status"] == "meeting_scheduled"
    audit = await db[Collections.ACTIVITY_LOGS].find_one({"action": "meeting.scheduled"})
    assert audit is not None


async def test_schedule_is_idempotent(sales_client, schedule_body, db):
    headers = {"Idempotency-Key": "double-click-12345"}
    first = await sales_client.post("/api/meetings/schedule", json=schedule_body, headers=headers)
    second = await sales_client.post("/api/meetings/schedule", json=schedule_body, headers=headers)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["idempotent_replay"] is True
    assert await db[Collections.MEETINGS].count_documents({}) == 1
    # Without a header the derived key still prevents double submits.
    third = await sales_client.post("/api/meetings/schedule", json=schedule_body)
    fourth = await sales_client.post("/api/meetings/schedule", json=schedule_body)
    assert third.status_code in (201, 409) and fourth.status_code in (201, 409)
    assert await db[Collections.MEETINGS].count_documents({}) == 1


async def test_schedule_rejects_past_time_with_friendly_error(sales_client, lead, db):
    resp = await sales_client.post("/api/meetings/schedule", json={
        "lead_id": lead["id"], "meeting_date": "2020-01-01", "meeting_time": "10:00", "duration_minutes": 30, "min_duration": 1})
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["message"] == "Unable to schedule meeting."
    assert err["reason"] == "Meeting start time must be in the future."
    assert err["hint"] == "Please select another time."
    assert await db[Collections.MEETINGS].count_documents({}) == 0


async def test_min_duration_distinct_from_meeting_duration(sales_client, lead):
    d, t = future_slot()
    resp = await sales_client.post("/api/meetings/schedule", json={
        "lead_id": lead["id"], "meeting_date": d, "meeting_time": t, "duration_minutes": 5, "min_duration": 10})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_min_duration"
    resp = await sales_client.post("/api/meetings/schedule", json={
        "lead_id": lead["id"], "meeting_date": d, "meeting_time": t, "duration_minutes": 0, "min_duration": 1})
    assert resp.status_code == 422  # below the 1-minute minimum


async def test_one_minute_meeting_is_allowed(sales_client, lead):
    d, t = future_slot()
    resp = await sales_client.post("/api/meetings/schedule", json={
        "lead_id": lead["id"], "meeting_date": d, "meeting_time": t, "duration_minutes": 1, "min_duration": 1})
    assert resp.status_code == 201, resp.text
    assert resp.json()["schedule"]["duration_minutes"] == 1


async def test_other_sales_person_cannot_view_meeting(sales_client, other_client, schedule_body):
    m = (await sales_client.post("/api/meetings/schedule", json=schedule_body)).json()
    assert (await other_client.get(f"/api/meetings/{m['id']}")).status_code == 403


async def test_mock_join_link_and_settings_do_not_leak_secrets(sales_client, schedule_body):
    m = (await sales_client.post("/api/meetings/schedule", json=schedule_body)).json()
    assert m["classify"]["student_join_url"].startswith(settings.frontend_url)
    resp = await sales_client.get("/api/settings")
    body = resp.text
    for secret in ("test-partner-key", "test-auth-token", "test-webhook-secret", "test-secret-key-that-is-at-least-32-bytes"):
        assert secret not in body
