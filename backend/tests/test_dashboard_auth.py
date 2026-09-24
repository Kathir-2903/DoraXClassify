from app.workers import meeting_processor

SECRET = "test-webhook-secret"


async def test_login_success_failure_and_rate_limit(anon_client, users):
    ok = await anon_client.post("/api/auth/login", json={"email": "sales@classify.demo", "password": "Sales@123"})
    assert ok.status_code == 200
    assert ok.json()["user"]["role"] == "sales"
    token = ok.json()["access_token"]
    me = await anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "sales@classify.demo"
    for _ in range(5):
        bad = await anon_client.post("/api/auth/login", json={"email": "sales@classify.demo", "password": "wrong"})
        assert bad.status_code == 401
    locked = await anon_client.post("/api/auth/login", json={"email": "sales@classify.demo", "password": "Sales@123"})
    assert locked.status_code == 429


async def test_admin_routes_require_admin(sales_client, admin_client):
    assert (await sales_client.get("/api/admin/processing")).status_code == 403
    assert (await admin_client.get("/api/admin/processing")).status_code == 200


async def test_dashboard_counts_and_insufficient_insights(sales_client, schedule_body, anon_client, db):
    empty = (await sales_client.get("/api/dashboard/overview")).json()
    assert empty["meetings_scheduled"] == 0 and empty["lead_join_rate"] is None
    m = (await sales_client.post("/api/meetings/schedule", json=schedule_body)).json()
    await anon_client.post("/api/webhooks/classify", headers={"api-key": SECRET}, json={
        "sessionDetails": {"uniqueId": m["classify"]["unique_id"], "startTime": 1790000000, "endTime": 1790001500,
                           "totalPresent": 1, "recordings": ["mock://r.mp4"]},
        "attendanceDetails": [{"email": "rahul@example.com", "attendedTime": 24, "attendanceStatus": "present"}]})
    await meeting_processor.drain()
    ov = (await sales_client.get("/api/dashboard/overview")).json()
    assert ov["meetings_completed"] == 1 and ov["analysis_completed"] == 1
    assert ov["lead_join_rate"] == 100.0
    assert ov["average_meeting_duration_seconds"] == 1500
    insights = (await sales_client.get("/api/dashboard/insights")).json()
    assert insights["top_objection"]["available"] is False  # one meeting is not enough to claim a pattern
    charts = (await sales_client.get("/api/dashboard/meetings")).json()
    assert sum(s["value"] for s in charts["status_breakdown"]) == 1
    report = await sales_client.get(f"/api/meetings/{m['id']}/report.pdf")
    assert report.status_code == 200 and report.content[:4] == b"%PDF"


async def test_health(anon_client):
    resp = await anon_client.get("/api/health")
    assert resp.status_code == 200
