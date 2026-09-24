from datetime import timedelta

import httpx
import pytest
import respx

from app.config.settings import settings
from app.database.mongodb import Collections
from app.services import attendance_service
from app.utils.datetime_utils import utcnow
from app.utils.validators import to_object_id
from app.workers import meeting_processor

URL = "https://apiclassify.zenclass.in/send-attendance-details"


@pytest.fixture
async def ended_meeting(sales_client, schedule_body, db):
    m = (await sales_client.post("/api/meetings/schedule", json=schedule_body)).json()
    oid = to_object_id(m["id"])
    now = utcnow()
    await db[Collections.MEETINGS].update_one(
        {"_id": oid},
        {"$set": {"schedule.start_time": now - timedelta(minutes=50), "schedule.end_time": now - timedelta(minutes=20),
                  # Scheduling itself always runs in mock mode in tests; flip this flag to
                  # represent "this meeting really exists on Classify" for attendance-sync
                  # tests below, which patch classify_mock_mode=False just for the pull.
                  # (A meeting actually created in mock mode is never queried for real —
                  # see attendance_service._due_query and the sync-attendance route guard.)
                  "classify.is_mock": False}},
    )
    m["classify"]["is_mock"] = False
    return m


def documented_response(unique_id, lead_email, present=True):
    return {
        "Access": True, "Status": "200 OK", "Message": "Details sent successfully",
        "SessionDetailsToSend": {
            "Label": "Sales Discussion", "StartTime": "March 14, 2026 10:00 AM", "EndTime": "March 14, 2026 10:28 AM",
            "TotalPresent": 1 if present else 0, "TotalAbsent": 0 if present else 1, "TotalStudents": 1,
            "MinimumAttendanceTime": 1, "UniqueId": unique_id, "Zen_Product_Type": "", "ClassNotes": "", "Product": "guvi",
            "AssetDetails": [{"type": "recording", "url": "mock://recordings/r.mp4"}] if present else [],
        },
        "AttendanceDetails": [
            {"Name": "Rahul", "Email": lead_email, "AttendanceStatus": "P" if present else "A",
             "Attendedtime": 27 if present else 0, "Notes": "", "Role": "student", "AttendanceInfo": {}},
            {"Name": "Sales Person", "Email": "sales@classify.demo", "AttendanceStatus": "P", "Attendedtime": 28,
             "Notes": "", "Role": "host", "AttendanceInfo": {}},
        ],
    }


def host_only_response(unique_id, host_email="sales@classify.demo"):
    """Shape actually observed live for a guest/open meeting: the guest who
    joined is not listed at all, even though they genuinely attended —
    Classify's SendAttendanceDetails only tracks pre-registered (batch_data)
    students, and guests aren't pre-registered."""
    return {
        "Access": True, "Status": "200 OK", "Message": "Details sent successfully",
        "SessionDetailsToSend": {
            "Label": "Sales Discussion", "StartTime": "March 14, 2026 10:00 AM", "EndTime": "March 14, 2026 10:02 AM",
            "TotalPresent": 0, "TotalAbsent": 0, "TotalStudents": 0,
            "MinimumAttendanceTime": 1, "UniqueId": unique_id, "Zen_Product_Type": "", "ClassNotes": "", "Product": "guvi",
            "AssetDetails": [{"type": "recording", "url": "https://classifyprod.s3.ap-south-1.amazonaws.com/r.mp4"}],
        },
        "AttendanceDetails": [
            {"Name": "Sales Person", "Email": host_email, "AttendanceStatus": "P", "Attendedtime": 2,
             "Notes": "", "Role": "host", "AttendanceInfo": {}},
        ],
    }


@respx.mock
async def test_guest_meeting_without_lead_in_attendance_is_not_marked_no_show(ended_meeting, real_attendance, sales_client):
    assert ended_meeting["classify"]["meeting_type"] == "open"  # guest mode default
    respx.post(URL).mock(return_value=httpx.Response(200, json=host_only_response(ended_meeting["classify"]["unique_id"])))
    assert await attendance_service.sync_due_meetings() == 1
    m = (await sales_client.get(f"/api/meetings/{ended_meeting['id']}")).json()
    assert m["status"]["no_show"] is False
    assert m["status"]["meeting_completed"] is True
    assert m["processing"]["recording"]["status"] == "pending"


@respx.mock
async def test_manual_resync_corrects_a_wrong_no_show_verdict(ended_meeting, real_attendance, sales_client, db):
    # Simulate the earlier (buggy) verdict: marked no-show and everything skipped.
    await db[Collections.MEETINGS].update_one(
        {"_id": to_object_id(ended_meeting["id"])},
        {"$set": {"status.no_show": True, "status.overall": "NO_SHOW",
                  "processing.recording.status": "skipped", "processing.transcript.status": "skipped",
                  "processing.analysis.status": "skipped"}},
    )
    body = host_only_response(ended_meeting["classify"]["unique_id"])
    respx.post(URL).mock(return_value=httpx.Response(200, json=body))
    resp = await sales_client.post(f"/api/meetings/{ended_meeting['id']}/sync-attendance")
    assert resp.status_code == 200, resp.text
    m = resp.json()
    assert m["status"]["no_show"] is False
    assert m["status"]["meeting_completed"] is True
    assert m["processing"]["recording"]["status"] == "pending"
    assert m["processing"]["transcript"]["status"] == "pending"
    assert m["processing"]["analysis"]["status"] == "pending"


async def test_sync_endpoint_no_longer_blocks_a_no_show_meeting(ended_meeting, sales_client, db):
    await db[Collections.MEETINGS].update_one(
        {"_id": to_object_id(ended_meeting["id"])}, {"$set": {"status.no_show": True}})
    resp = await sales_client.post(f"/api/meetings/{ended_meeting['id']}/sync-attendance")
    assert resp.status_code != 409


async def test_sync_endpoint_blocks_an_already_completed_meeting(ended_meeting, sales_client, db):
    await db[Collections.MEETINGS].update_one(
        {"_id": to_object_id(ended_meeting["id"])}, {"$set": {"status.meeting_completed": True}})
    resp = await sales_client.post(f"/api/meetings/{ended_meeting['id']}/sync-attendance")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "already_completed"


@pytest.fixture
def real_attendance(monkeypatch):
    # Meetings were created in mock mode; switch only the attendance pull to the real (respx-mocked) API.
    monkeypatch.setattr(settings, "classify_mock_mode", False)
    monkeypatch.setattr(settings, "classify_creator_email", "admin@guvi.in")


@respx.mock
async def test_sync_pulls_attendance_and_runs_pipeline(ended_meeting, real_attendance, sales_client, db):
    respx.post(URL).mock(return_value=httpx.Response(
        200, json=documented_response(ended_meeting["classify"]["unique_id"], "rahul@example.com")))
    assert await attendance_service.sync_due_meetings() == 1
    m = (await sales_client.get(f"/api/meetings/{ended_meeting['id']}")).json()
    assert m["attendance_sync"]["status"] == "completed"
    assert m["status"]["lead_joined"] and m["status"]["meeting_completed"]
    assert m["status"]["sales_person_joined"] is True  # host row (Role: host) present
    assert m["attendance"]["duration_seconds"] == 28 * 60
    event = await db[Collections.WEBHOOK_EVENTS].find_one({"source": "classify_attendance_api"})
    assert event["processing_status"] == "processed"

    await meeting_processor.drain()
    m = (await sales_client.get(f"/api/meetings/{ended_meeting['id']}")).json()
    assert m["status"]["analysis_completed"] is True
    # Not requested again once completed.
    assert await attendance_service.sync_due_meetings() == 0


@respx.mock
async def test_sync_accepts_sessionDetails_key_variant(ended_meeting, real_attendance, sales_client):
    """Regression: a real (guest/open meeting) SendAttendanceDetails response
    was observed using `sessionDetails` instead of the documented
    `sessionDetailsToSend` — treating that as a rejection stuck the meeting in
    a retry loop with the misleading error "Details sent successfully"."""
    body = documented_response(ended_meeting["classify"]["unique_id"], "rahul@example.com")
    body["sessionDetails"] = body.pop("SessionDetailsToSend")
    respx.post(URL).mock(return_value=httpx.Response(200, json=body))
    assert await attendance_service.sync_due_meetings() == 1
    m = (await sales_client.get(f"/api/meetings/{ended_meeting['id']}")).json()
    assert m["attendance_sync"]["status"] == "completed"
    assert m["status"]["lead_joined"] is True


@respx.mock
async def test_real_recording_is_transcribed_with_whisper(ended_meeting, real_attendance, sales_client, monkeypatch):
    """When a real recording is downloaded, the transcript stage must use the
    local faster-whisper provider (the default) instead of Gemini or the
    scripted mock fallback — faster-whisper itself isn't exercised here."""
    from app.models.analysis import TranscriptionResult
    from app.services.recording_service import RecordingFile
    from app.workers import meeting_processor

    async def fake_download(meeting_id, url):
        return RecordingFile(path="/tmp/fake-recording.mp4", content_type="video/mp4", size_bytes=1000,
                             duration_seconds=90.0, is_mock=False)

    async def fake_extract_audio(video_path):
        return None  # ffmpeg unavailable in this test; whisper would take the video path itself

    async def fake_whisper_transcribe(media_path):
        assert media_path == "/tmp/fake-recording.mp4"
        return TranscriptionResult(language="en", has_speaker_labels=False, has_timestamps=True, segments=[
            {"speaker": "unknown", "speaker_name": "", "start_seconds": 0.0, "end_seconds": 2.0, "text": "Hello there."},
        ])

    monkeypatch.setattr(meeting_processor, "download_recording", fake_download)
    monkeypatch.setattr(meeting_processor, "extract_audio", fake_extract_audio)
    monkeypatch.setattr(meeting_processor, "whisper_transcribe", fake_whisper_transcribe)

    respx.post(URL).mock(return_value=httpx.Response(
        200, json=documented_response(ended_meeting["classify"]["unique_id"], "rahul@example.com")))
    assert await attendance_service.sync_due_meetings() == 1
    await meeting_processor.drain()

    m = (await sales_client.get(f"/api/meetings/{ended_meeting['id']}")).json()
    assert m["status"]["transcript_available"] is True
    transcript = (await sales_client.get(f"/api/meetings/{ended_meeting['id']}/transcript")).json()
    assert transcript["source"] == "whisper"
    assert transcript["is_mock"] is False
    assert transcript["segments"][0]["text"] == "Hello there."


@respx.mock
async def test_class_in_progress_is_retried_later(ended_meeting, real_attendance, db):
    respx.post(URL).mock(return_value=httpx.Response(200, json={
        "access": True, "status": "409 Conflict", "message": "Class in progress. Please check back after the class ends.",
        "sessionDetailsToSend": None, "attendanceDetails": []}))
    assert await attendance_service.sync_due_meetings() == 1
    doc = await db[Collections.MEETINGS].find_one({"_id": to_object_id(ended_meeting["id"])})
    assert doc["attendance_sync"]["status"] == "waiting"
    assert doc["attendance_sync"]["next_attempt_at"] > utcnow()
    assert doc["status"]["meeting_completed"] is False and doc["status"]["no_show"] is False
    assert await attendance_service.sync_due_meetings() == 0  # not due again yet


@respx.mock
async def test_non_retryable_error_stops_and_flags(ended_meeting, real_attendance, sales_client):
    respx.post(URL).mock(return_value=httpx.Response(200, json={
        "access": False, "status": "401 Unauthorized", "message": "Not an Admin",
        "sessionDetailsToSend": None, "attendanceDetails": []}))
    await attendance_service.sync_due_meetings()
    m = (await sales_client.get(f"/api/meetings/{ended_meeting['id']}")).json()
    assert m["attendance_sync"]["status"] == "failed"
    assert "ATTENDANCE_SYNC_FAILED" in m["flags"]
    assert any(s["label"] == "Attendance sync failed" for s in m["journey"])


@respx.mock
async def test_manual_sync_endpoint_marks_no_show(ended_meeting, real_attendance, sales_client):
    respx.post(URL).mock(return_value=httpx.Response(
        200, json=documented_response(ended_meeting["classify"]["unique_id"], "rahul@example.com", present=False)))
    resp = await sales_client.post(f"/api/meetings/{ended_meeting['id']}/sync-attendance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sync_result"]["outcome"] == "ok"
    assert body["status"]["overall"] == "NO_SHOW"


async def test_mock_mode_sync_waits_until_meeting_ends(sales_client, schedule_body, db):
    m = (await sales_client.post("/api/meetings/schedule", json=schedule_body)).json()
    resp = await sales_client.post(f"/api/meetings/{m['id']}/sync-attendance")
    assert resp.json()["sync_result"]["outcome"] == "in_progress"


async def test_simulation_uses_documented_attendance_shape(sales_client, schedule_body, db):
    m = (await sales_client.post("/api/meetings/schedule", json=schedule_body)).json()
    resp = await sales_client.post(f"/api/meetings/{m['id']}/simulate", json={"outcome": "completed", "duration_minutes": 20})
    assert resp.json()["status"]["meeting_completed"] is True
    event = await db[Collections.WEBHOOK_EVENTS].find_one({"source": "simulation"})
    assert "SessionDetailsToSend" in event["payload"] and "AttendanceDetails" in event["payload"]


async def test_mock_created_meetings_are_never_queried_against_a_real_classify(sales_client, schedule_body, db, monkeypatch):
    """Regression: once CLASSIFY_MOCK_MODE is switched off in production, any
    meeting that was created while it was still on (a fake uniqueId) must
    never be looked up against the real Classify API — neither by the
    background worker nor by a manual "Sync attendance" click."""
    m = (await sales_client.post("/api/meetings/schedule", json=schedule_body)).json()
    oid = to_object_id(m["id"])
    now = utcnow()
    await db[Collections.MEETINGS].update_one(
        {"_id": oid}, {"$set": {"schedule.start_time": now - timedelta(minutes=50), "schedule.end_time": now - timedelta(minutes=20)}},
    )
    assert (await db[Collections.MEETINGS].find_one({"_id": oid}))["classify"]["is_mock"] is True

    monkeypatch.setattr(settings, "classify_mock_mode", False)
    monkeypatch.setattr(settings, "classify_creator_email", "admin@guvi.in")
    with respx.mock:
        route = respx.post(URL)  # no mock registered → any call raises inside respx
        assert await attendance_service.sync_due_meetings() == 0
        assert route.call_count == 0

        resp = await sales_client.post(f"/api/meetings/{m['id']}/sync-attendance")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "mock_meeting"
        assert route.call_count == 0
