import json
import time

import httpx
import pytest
import respx

from app.config.settings import settings
from app.database.mongodb import Collections
from app.services.recording_service import download_recording, parse_s3_url
from app.utils.security import compute_signature
from app.workers import meeting_processor

SECRET = "test-webhook-secret"


def attendance_payload(unique_id, email, present=True, recordings=None, minutes=25):
    now = int(time.time())
    return {
        "sessionDetails": {"uniqueId": unique_id, "label": "Sales Discussion", "startTime": now - minutes * 60, "endTime": now,
                           "totalPresent": 1 if present else 0, "totalAbsent": 0 if present else 1, "totalStudents": 1,
                           "minimumAttendaceTime": 1, "classNotes": "",
                           "recordings": recordings if recordings is not None else ["mock://recordings/demo.mp4"]},
        "attendanceDetails": [{"email": email, "attendedTime": minutes - 1 if present else 0,
                               "attendanceStatus": "present" if present else "absent", "notes": ""}],
    }


@pytest.fixture
async def meeting(sales_client, schedule_body):
    resp = await sales_client.post("/api/meetings/schedule", json=schedule_body)
    assert resp.status_code == 201
    return resp.json()


async def _post(client, payload, headers):
    return await client.post("/api/webhooks/classify", content=json.dumps(payload),
                             headers={"Content-Type": "application/json", **headers})


async def test_webhook_rejects_invalid_credentials(anon_client, meeting):
    payload = attendance_payload(meeting["classify"]["unique_id"], "rahul@example.com")
    assert (await _post(anon_client, payload, {})).status_code == 401
    assert (await _post(anon_client, payload, {"api-key": "wrong"})).status_code == 401
    assert (await _post(anon_client, payload, {"X-Classify-Signature": "sha256=deadbeef"})).status_code == 401


async def test_webhook_accepts_api_key_or_hmac_and_is_idempotent(anon_client, meeting, db):
    payload = attendance_payload(meeting["classify"]["unique_id"], "rahul@example.com")
    raw = json.dumps(payload).encode()
    r1 = await anon_client.post("/api/webhooks/classify", content=raw,
                                headers={"Content-Type": "application/json", "X-Classify-Signature": "sha256=" + compute_signature(raw, SECRET)})
    assert r1.status_code == 200 and r1.json()["duplicate"] is False
    r2 = await _post(anon_client, payload, {"api-key": SECRET})
    assert r2.status_code == 200 and r2.json()["duplicate"] is True
    assert await db[Collections.WEBHOOK_EVENTS].count_documents({}) == 1
    event = await db[Collections.WEBHOOK_EVENTS].find_one({})
    assert event["processing_status"] == "processed"
    assert event["payload"] == payload  # stored verbatim
    assert str(event["meeting_id"]) == meeting["id"]


async def test_full_pipeline_to_ai_analysis(anon_client, sales_client, meeting, db):
    await _post(anon_client, attendance_payload(meeting["classify"]["unique_id"], "rahul@example.com"), {"api-key": SECRET})
    m = (await sales_client.get(f"/api/meetings/{meeting['id']}")).json()
    assert m["status"]["lead_joined"] and m["status"]["meeting_completed"]
    assert m["status"]["overall"] == "RECORDING_PROCESSING"
    assert m["polling"]["active"] is True

    await meeting_processor.drain()
    m = (await sales_client.get(f"/api/meetings/{meeting['id']}")).json()
    assert m["status"]["recording_available"] and m["status"]["transcript_available"] and m["status"]["analysis_completed"]
    assert m["status"]["overall"] in ("ANALYSIS_COMPLETED", "FOLLOW_UP_REQUIRED")
    assert m["polling"]["active"] is False
    result = m["analysis_result"]["result"]
    assert result["summary"] and len(result["pitch_coverage"]) == 12
    assert m["analysis_result"]["prompt_version"] == "1.0" and m["analysis_result"]["model"]
    assert m["call_quality"]["total_duration_seconds"]["value"] == 25 * 60
    assert m["call_quality"]["questions"]["ai_generated"] is True
    labels = [t["label"] for t in m["timeline"]]
    for expected in ("Meeting Scheduled", "Lead Joined", "Meeting Completed", "Recording Available",
                     "Transcript Generated", "AI Analysis Complete"):
        assert expected in labels
    # Source recording URL is never exposed to the browser.
    assert "mock://recordings" not in json.dumps(m)
    lead = (await sales_client.get(f"/api/leads/{meeting['lead_id']}/analytics")).json()
    assert lead["summary"]["completed_meetings"] == 1
    assert any(e["event"] == "analysis_ready" for e in lead["journey"])

    # Re-analysis uses the stored transcript and keeps history.
    resp = await sales_client.post(f"/api/meetings/{meeting['id']}/reanalyze", json={"reason": "prompt update"})
    assert resp.status_code == 200
    versions = await db[Collections.MEETING_ANALYTICS].find({}).to_list(length=None)
    assert len(versions) == 2 and sum(1 for v in versions if v["is_current"]) == 1


async def test_no_show_from_attendance_data(anon_client, sales_client, meeting, db):
    await _post(anon_client, attendance_payload(meeting["classify"]["unique_id"], "rahul@example.com", present=False, recordings=[]),
                {"api-key": SECRET})
    m = (await sales_client.get(f"/api/meetings/{meeting['id']}")).json()
    assert m["status"]["overall"] == "NO_SHOW"
    assert m["status"]["no_show"] is True and m["status"]["meeting_completed"] is False
    assert "NO_SHOW" in m["flags"]
    assert any(s["label"] == "Lead did not join" for s in m["journey"])
    await meeting_processor.drain()
    assert (await db[Collections.MEETING_ANALYTICS].count_documents({})) == 0


async def test_missing_recording_marks_unavailable_without_fabrication(anon_client, sales_client, meeting):
    await _post(anon_client, attendance_payload(meeting["classify"]["unique_id"], "rahul@example.com", recordings=[]),
                {"api-key": SECRET})
    await meeting_processor.drain()
    m = (await sales_client.get(f"/api/meetings/{meeting['id']}")).json()
    assert m["processing"]["recording"]["status"] == "unavailable"
    assert m["processing"]["transcript"]["status"] == "unavailable"
    assert "RECORDING_MISSING" in m["flags"]
    assert m["call_quality"]["lead_talk_seconds"]["available"] is False
    assert m["call_quality"]["lead_talk_seconds"]["note"] == "Transcript unavailable"


@respx.mock
async def test_recording_download_failure_retries_then_fails(anon_client, sales_client, meeting, monkeypatch, db, tmp_path):
    monkeypatch.setattr(settings, "recording_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "retry_backoff_seconds", 0)
    url = "https://cdn.example.com/rec/meeting.mp4"
    respx.get(url).mock(return_value=httpx.Response(503))
    await _post(anon_client, attendance_payload(meeting["classify"]["unique_id"], "rahul@example.com", recordings=[url]),
                {"api-key": SECRET})
    for _ in range(settings.max_retry_attempts + 1):
        await meeting_processor.process_pending_once()
    m = (await sales_client.get(f"/api/meetings/{meeting['id']}")).json()
    stage = m["processing"]["recording"]
    assert stage["status"] == "failed" and stage["attempt_count"] == settings.max_retry_attempts
    assert stage["next_retry_at"] is None
    assert m["status"]["overall"] == "FAILED"
    assert "RECORDING_FAILED" in m["flags"]


@respx.mock
async def test_recording_http_download(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "recording_storage_dir", str(tmp_path))
    respx.get("https://cdn.example.com/rec/a.mp4").mock(
        return_value=httpx.Response(200, content=b"\x00" * 2048, headers={"content-type": "video/mp4"}))
    file = await download_recording("abc", "https://cdn.example.com/rec/a.mp4")
    assert file.size_bytes == 2048 and file.path.endswith("abc.mp4")


def test_s3_url_parsing():
    assert parse_s3_url("s3://bucket/path/to/file.mp4") == ("bucket", "path/to/file.mp4")
    assert parse_s3_url("https://my-bucket.s3.ap-south-1.amazonaws.com/rec/x.mp4") == ("my-bucket", "rec/x.mp4")
    assert parse_s3_url("https://s3.ap-south-1.amazonaws.com/my-bucket/rec/x.mp4") == ("my-bucket", "rec/x.mp4")
    assert parse_s3_url("https://cdn.example.com/x.mp4") is None


async def test_unmatched_webhook_recorded_for_admin(anon_client, admin_client, db):
    await _post(anon_client, attendance_payload("unknown-uuid", "x@example.com"), {"api-key": SECRET})
    events = (await admin_client.get("/api/admin/webhooks")).json()
    assert events["items"][0]["processing_status"] == "unmatched"


async def test_simulation_only_in_mock_mode(sales_client, meeting, monkeypatch):
    monkeypatch.setattr(settings, "classify_mock_mode", False)
    resp = await sales_client.post(f"/api/meetings/{meeting['id']}/simulate", json={"outcome": "completed"})
    assert resp.status_code == 403
