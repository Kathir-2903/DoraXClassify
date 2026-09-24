import json
import time

import httpx
import pytest
import respx

from app.config.settings import settings
from app.middleware.error_handler import AppError
from app.services.classify_service import (
    ClassifyError,
    ClassifyService,
    Participant,
    ScheduledMeetingInput,
    build_create_payload,
    build_meeting_link,
    normalized_auth_token,
    extract_host_join_url,
    extract_recording_urls,
    extract_student_join_url,
    format_classify_time,
    mock_create_response,
    normalize_attendance_payload,
    normalize_created_meeting,
    parse_classify_time,
    validate_create_payload,
)

NOW = int(time.time())


def _input(**overrides):
    base = dict(
        label="Sales Discussion - Rahul",
        start_unix=NOW + 3600,
        end_unix=NOW + 3600 + 1800,
        lead=Participant("Rahul Kumar", "rahul@example.com"),
        host=Participant("Sales Person", "sales@classify.demo"),
        min_duration=1,
    )
    base.update(overrides)
    return ScheduledMeetingInput(**base)


def test_payload_matches_documented_contract():
    """Guest mode is on by default, so this is the shape actually sent in
    production: meetingType "open", empty batch_data, guestConfig present."""
    payload = build_create_payload(_input())
    assert set(payload) == {
        "label", "start_time", "end_time", "thumbnail", "minDuration", "batch_data", "studentNotes", "enable_chat",
        "authToken", "subject", "message", "footer", "product", "created_by", "meetingType", "hosts",
        "autoRecordingStart", "recording_autoStart", "isEndTimeGiven", "studentHMSRole", "timezone", "org_id",
        "repeat", "repeatSchedule", "isPollEnabled", "isQuizEnabled", "guestConfig",
    }
    assert payload["autoRecordingStart"] == "on"
    assert payload["repeat"] == {"type": "noRepeat"}
    assert payload["repeatSchedule"] == {"type": "noRepeat"}
    assert payload["isPollEnabled"] is False and payload["isQuizEnabled"] is False
    assert payload["meetingType"] == "open"
    assert payload["batch_data"] == []
    assert payload["guestConfig"]["IsGuestParticipantAllowed"] is True
    assert payload["product"] == "guvi"
    assert payload["created_by"] == "classify"
    assert payload["isEndTimeGiven"] == "on"
    assert payload["timezone"] == "Asia/Kolkata"
    assert payload["authToken"] == "auth:test-auth-token"  # documented `auth:` prefix normalisation
    assert payload["org_id"] == "org-test"
    assert isinstance(payload["start_time"], int) and isinstance(payload["end_time"], int)
    validate_create_payload(payload, NOW)


def test_payload_without_guest_mode_uses_scheduled_batch_data(monkeypatch):
    """With guest mode off, the classic pre-registered shape still works."""
    monkeypatch.setattr(settings, "classify_guest_mode_enabled", False)
    payload = build_create_payload(_input())
    assert "guestConfig" not in payload
    assert payload["meetingType"] == "scheduled"
    assert payload["batch_data"] == [{"name": "Rahul Kumar", "email": "rahul@example.com"}]
    validate_create_payload(payload, NOW)


@pytest.mark.parametrize("overrides,message", [
    ({"label": "abc"}, "Meet Label should have at least 4 letters"),
    ({"start_unix": NOW - 10, "end_unix": NOW + 600}, "Start time should be greater than current time"),
    ({"start_unix": NOW + 30, "end_unix": NOW + 600}, "Start time should be greater than current time"),
    ({"end_unix": NOW + 3600}, "End time should be greater than Start time"),
    ({"end_unix": NOW + 3600 + 30}, "Meet Duration should be at least 1 minute"),
    ({"end_unix": NOW + 3600 + 9 * 3600}, "Meet Duration should not be more than 8 hours"),
    ({"min_duration": 0}, "Empty/Wrong MinDuration"),
    ({"min_duration": 31}, "MinDuration must be less than Class duration"),
    ({"host": Participant("Same", "rahul@example.com")}, "Host email found in student list"),
    ({"host": Participant("Bad", "not-an-email")}, "Empty/Wrong Hosts"),
    ({"lead": Participant("Rahul", "bad email@example.com")}, "Empty/Wrong Batch data"),
    ({"timezone": "Mars/Olympus"}, "No such timezone"),
])
def test_prevalidation_mirrors_documented_rules(overrides, message, monkeypatch):
    # These mirror the classic (non-guest) "scheduled" + batch_data rules, so
    # they need a populated batch_data to be meaningful.
    monkeypatch.setattr(settings, "classify_guest_mode_enabled", False)
    with pytest.raises(ClassifyError) as exc:
        validate_create_payload(build_create_payload(_input(**overrides)), NOW)
    assert exc.value.classify_message == message
    assert exc.value.reason  # always a friendly reason


def test_auth_token_gets_documented_prefix_normalised(monkeypatch):
    monkeypatch.setattr(settings, "classify_auth_token", "deadbeef")
    assert normalized_auth_token() == "auth:deadbeef"
    # Already-prefixed tokens (and empty ones, in mock mode) pass through unchanged.
    monkeypatch.setattr(settings, "classify_auth_token", "auth:deadbeef")
    assert normalized_auth_token() == "auth:deadbeef"
    monkeypatch.setattr(settings, "classify_auth_token", "")
    assert normalized_auth_token() == ""


def test_invalid_config_values_rejected(monkeypatch):
    monkeypatch.setattr(settings, "classify_student_hms_role", "superuser")
    with pytest.raises(ClassifyError, match="Unable to schedule"):
        validate_create_payload(build_create_payload(_input()), NOW)
    monkeypatch.setattr(settings, "classify_student_hms_role", "allow-video-audio")
    monkeypatch.setattr(settings, "classify_created_by", "someone")
    with pytest.raises(ClassifyError):
        validate_create_payload(build_create_payload(_input()), NOW)


def test_guest_mode_on_by_default():
    # On by default: leads have no Classify account, so meetings must be
    # guest-joinable. Requires meetingType "open" + empty batch_data — a
    # "scheduled" meeting with batch_data rejects guestConfig outright
    # ("Guest access cannot be enabled for a private meeting").
    assert settings.classify_guest_mode_enabled is True
    payload = build_create_payload(_input())
    assert payload["guestConfig"]["IsGuestParticipantAllowed"] is True
    assert payload["meetingType"] == "open"
    assert payload["batch_data"] == []
    validate_create_payload(payload, NOW)  # does not raise


def test_guest_mode_payload_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "classify_guest_mode_enabled", True)
    payload = build_create_payload(_input())
    assert payload["guestConfig"]["IsGuestParticipantAllowed"] is True
    validate_create_payload(payload, NOW)  # does not raise

    monkeypatch.setattr(settings, "classify_guest_collect_phone", True)
    payload = build_create_payload(_input())
    assert {"FieldType": "phone_number", "FieldName": "Phone"} in payload["guestConfig"]["GuestInformationCollectionFields"]


@pytest.mark.parametrize("bad_field,message", [
    ({"FieldType": "url", "FieldName": "Website"}, "Invalid field type: url"),
    ({"FieldType": "text", "FieldName": "X"}, "Invalid field name: X"),
    ({"FieldType": "single_dropdown", "FieldName": "Source", "Options": ["Only one"]},
     "Dropdown field 'Source' must have at least 2 options."),
])
def test_guest_field_validation_matches_documented_rules(bad_field, message, monkeypatch):
    monkeypatch.setattr(settings, "classify_guest_mode_enabled", True)
    payload = build_create_payload(_input())
    payload["guestConfig"]["GuestInformationCollectionFields"] = [bad_field]
    with pytest.raises(ClassifyError) as exc:
        validate_create_payload(payload, NOW)
    assert exc.value.classify_message == message
    assert "guest" in exc.value.reason.lower()


SUCCESS = {
    "Message": "Meet Created successfully", "Status": "200 OK", "Access": True,
    "Details": {"label": "Sales Discussion - Rahul", "start_time": NOW + 3600, "end_time": NOW + 5400, "minDuration": 1,
                "batch_data": [{"name": "Rahul Kumar", "email": "rahul@example.com"}],
                "UniqueId": "663ff539-2da4-422d-8500-96d76b29c9b5", "MeetProvider": "100ms", "hosts": [{"name": "Sales Person", "email": "sales@classify.demo"}],
                "thumbnail": "Default", "totalpresent": 0, "authToken": "echoed-secret", "studentCode": "", "roomId": "",
                "hostCode": "", "chats": [], "recordings": [], "transcripts": [], "totaltime": 1800, "product": "guvi",
                "meetingType": "scheduled", "created_by": "classify", "calendar_details": {"calendar_id": "", "event_id": ""},
                "created_at": NOW, "recording_autoStart": "on", "roomStatusData": {"sessionEnded": ""},
                "timezone": "Asia/Kolkata", "studentHMSRole": "student"}}


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setattr(settings, "classify_mock_mode", False)


@respx.mock
async def test_create_meeting_success_sends_documented_request(real_mode):
    route = respx.post("https://apiclassify.zenclass.in/createMS").mock(return_value=httpx.Response(200, json=SUCCESS))
    body = await ClassifyService().create_scheduled_meeting(_input())
    assert body["Details"]["UniqueId"] == SUCCESS["Details"]["UniqueId"]
    assert normalize_created_meeting(body)["unique_id"] == SUCCESS["Details"]["UniqueId"]
    assert normalize_created_meeting(body)["meet_provider"] == "100ms"
    request = route.calls.last.request
    assert request.headers["Authorization-Key"] == "test-partner-key"
    sent = json.loads(request.content)
    assert sent["meetingType"] == "open" and sent["authToken"] == "auth:test-auth-token"  # guest mode is on by default
    assert sent["autoRecordingStart"] == "on"


@respx.mock
@pytest.mark.parametrize("status,body,code,http", [
    (400, {"access": False, "status": "400 Bad Request", "message": "Start time should be greater than current time"},
     "classify_validation_error", 400),
    (401, {"access": False, "status": "401 Unauthorized", "message": "Unauthorized Key"}, "classify_auth_error", 502),
    (401, {"access": False, "status": "401 unauthorized", "message": "Session Invalid"}, "classify_auth_error", 502),
    (409, {"access": True, "status": "409 Conflict", "message": "Cannot create meet"}, "classify_conflict", 409),
    # Errors reported in the body with HTTP 200 are still errors.
    (200, {"access": False, "status": "400 Bad Request", "message": "Empty/Wrong Hosts"}, "classify_validation_error", 400),
    # Final createMS docs: poll/quiz errors come via RespondWithSuccess (HTTP 200, Access may be true).
    (200, {"Access": True, "Status": "409 Conflict", "Message": "Invalid poll ID or poll ID not found"}, "classify_conflict", 409),
    (409, {"Access": False, "Status": "409 Conflict", "Message": "Cannot schedule all jobs for meeting"}, "classify_conflict", 409),
    (500, {"Access": False, "Status": "500 Internal Server Error", "Message": "Error enqueuing job"}, "classify_unavailable", 502),
    (400, {"Access": False, "Status": "400 Bad Request", "Message": "Invalid field type: color"}, "classify_validation_error", 400),
])
async def test_create_meeting_error_mapping(real_mode, status, body, code, http):
    respx.post("https://apiclassify.zenclass.in/createMS").mock(return_value=httpx.Response(status, json=body))
    with pytest.raises(ClassifyError) as exc:
        await ClassifyService().create_scheduled_meeting(_input())
    assert exc.value.code == code
    assert exc.value.status_code == http
    assert "test-partner-key" not in json.dumps(exc.value.details)


@respx.mock
async def test_create_meeting_409_after_creation_is_accepted_with_warning(real_mode):
    body = {**SUCCESS, "Status": "409 Conflict",
            "Message": "Cannot  schedule send attendace details for sending details to zen webhook"}
    respx.post("https://apiclassify.zenclass.in/createMS").mock(return_value=httpx.Response(409, json=body))
    result = await ClassifyService().create_scheduled_meeting(_input())
    assert result["_warning"] == "attendance_webhook_not_registered"


@respx.mock
async def test_create_meeting_network_failure(real_mode):
    respx.post("https://apiclassify.zenclass.in/createMS").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(AppError) as exc:
        await ClassifyService().create_scheduled_meeting(_input())
    assert exc.value.code == "classify_unavailable"


def test_join_url_uses_documented_meeting_dashboard_link():
    unique_id = SUCCESS["Details"]["UniqueId"]
    expected = f"https://classify.zenclass.in/meet-dashboard-new?session={unique_id}"
    assert build_meeting_link(unique_id) == expected
    # Same link for host and lead — Classify resolves the role from the signed-in session.
    assert extract_student_join_url(SUCCESS) == expected
    assert extract_host_join_url(SUCCESS) == expected
    assert normalize_created_meeting(SUCCESS)["student_join_url"] == expected
    assert normalize_created_meeting(SUCCESS)["host_join_url"] == expected


def test_join_url_prefers_a_direct_url_and_admin_override(monkeypatch):
    direct = {**SUCCESS, "Details": {**SUCCESS["Details"], "JoinUrl": "https://classify.example/j/1"}}
    assert extract_student_join_url(direct) == "https://classify.example/j/1"

    monkeypatch.setattr(settings, "classify_student_join_url_template", "https://white-label.example/{student_code}")
    with_code = {**SUCCESS, "Details": {**SUCCESS["Details"], "StudentCode": "abc123"}}
    assert extract_student_join_url(with_code) == "https://white-label.example/abc123"
    # Missing placeholder value → falls back to the documented link, never a broken URL.
    monkeypatch.setattr(settings, "classify_student_join_url_template", "https://white-label.example/{room_id}")
    no_room = {**SUCCESS, "Details": {**SUCCESS["Details"], "RoomId": ""}}
    assert extract_student_join_url(no_room) == f"https://classify.zenclass.in/meet-dashboard-new?session={SUCCESS['Details']['UniqueId']}"


def test_join_url_mock_mode_uses_demo_room():
    mock_response = mock_create_response(build_create_payload(_input()))
    unique_id = mock_response["Details"]["UniqueId"]
    lead_url = extract_student_join_url(mock_response)
    host_url = extract_host_join_url(mock_response)
    assert lead_url == f"{settings.frontend_url}/demo/meeting/{unique_id}?as=lead"
    assert host_url == f"{settings.frontend_url}/demo/meeting/{unique_id}?as=host"


def test_attendance_webhook_normalisation():
    payload = {
        "sessionDetails": {"uniqueId": "u-1", "label": "x", "startTime": NOW - 1800, "endTime": NOW, "totalPresent": 1,
                           "totalAbsent": 0, "totalStudents": 1, "minimumAttendaceTime": 1,
                           "recordings": [{"url": "https://bucket.s3.ap-south-1.amazonaws.com/rec/u-1.mp4"}, "not a url"]},
        "attendanceDetails": [{"email": "Rahul@Example.com", "attendedTime": 25, "attendanceStatus": "present"}],
    }
    data = normalize_attendance_payload(payload)
    assert data["unique_id"] == "u-1"
    assert data["duration_seconds"] == 1800
    assert data["attendees"][0]["email"] == "rahul@example.com"
    assert data["attendees"][0]["present"] is True
    assert data["attendees"][0]["attended_seconds"] == 25 * 60
    assert extract_recording_urls(payload) == ["https://bucket.s3.ap-south-1.amazonaws.com/rec/u-1.mp4"]


# --------------------------------------------------------------------------
# SendAttendanceDetails (final docs)
# --------------------------------------------------------------------------
ATTENDANCE_OK = {
    "Access": True, "Status": "200 OK", "Message": "Details sent successfully",
    "SessionDetailsToSend": {
        "Label": "Sales Discussion - Rahul", "StartTime": "March 14, 2026 10:00 AM", "EndTime": "March 14, 2026 10:32 AM",
        "TotalPresent": 1, "TotalAbsent": 0, "TotalStudents": 1, "MinimumAttendanceTime": 1,
        "UniqueId": "8f2c1e2a-6c41-4a9b-9c2f-1a2b3c4d5e6f", "Zen_Product_Type": "", "ClassNotes": "", "Product": "guvi",
        "AssetDetails": [{"type": "recording", "url": "https://bucket.s3.ap-south-1.amazonaws.com/rec/x.mp4"},
                         {"type": "chat", "url": "https://bucket.s3.ap-south-1.amazonaws.com/chat/x.json"},
                         {"type": "transcript", "url": "https://bucket.s3.ap-south-1.amazonaws.com/tr/x.vtt"}],
    },
    "AttendanceDetails": [
        {"Name": "Rahul Kumar", "Email": "Rahul@Example.com", "AttendanceStatus": "P", "Attendedtime": 30, "Notes": "",
         "Role": "student", "AttendanceInfo": {}},
        {"Name": "Sales Person", "Email": "sales@classify.demo", "AttendanceStatus": "P", "Attendedtime": 32, "Notes": "",
         "Role": "host", "AttendanceInfo": {}},
    ],
}


def test_documented_attendance_shape_normalises():
    data = normalize_attendance_payload(ATTENDANCE_OK)
    assert data["unique_id"] == "8f2c1e2a-6c41-4a9b-9c2f-1a2b3c4d5e6f"
    assert data["duration_seconds"] == 32 * 60
    # "March 14, 2026 10:00 AM" is IST → 04:30 UTC
    assert data["started_at"].strftime("%Y-%m-%d %H:%M") == "2026-03-14 04:30"
    lead = data["attendees"][0]
    assert lead["email"] == "rahul@example.com" and lead["present"] is True and lead["attended_seconds"] == 1800
    assert data["attendees"][1]["role"] == "host"
    assert data["recording_urls"] == ["https://bucket.s3.ap-south-1.amazonaws.com/rec/x.mp4"]
    assert "https://bucket.s3.ap-south-1.amazonaws.com/tr/x.vtt" in data["transcripts"]
    assert data["chat_urls"] == ["https://bucket.s3.ap-south-1.amazonaws.com/chat/x.json"]


def test_classify_time_roundtrip():
    dt = parse_classify_time("March 14, 2026 9:05 AM")
    assert format_classify_time(dt) == "March 14, 2026 9:05 AM"
    assert parse_classify_time(1790000000).year == 2026


def _meeting(**overrides):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    m = {"_id": "m1", "classify": {"unique_id": "8f2c1e2a", "is_mock": False},
         "schedule": {"start_time": now - timedelta(hours=1), "end_time": now - timedelta(minutes=30), "duration_minutes": 30,
                      "min_duration": 1},
         "lead_snapshot": {"name": "Rahul", "email": "rahul@example.com"},
         "sales_person_snapshot": {"name": "Sales", "email": "sales@classify.demo"}, "label": "Sales Discussion"}
    m.update(overrides)
    return m


@respx.mock
async def test_request_attendance_sends_documented_body(real_mode, monkeypatch):
    monkeypatch.setattr(settings, "classify_creator_email", "admin@guvi.in")
    route = respx.post("https://apiclassify.zenclass.in/send-attendance-details").mock(
        return_value=httpx.Response(200, json=ATTENDANCE_OK))
    result = await ClassifyService().request_attendance(_meeting())
    assert result.outcome == "ok"
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"for": "meet", "uniqueId": "8f2c1e2a", "product": "guvi", "creator_email": "admin@guvi.in"}
    assert route.calls.last.request.headers["Authorization-Key"] == "test-partner-key"


@respx.mock
@pytest.mark.parametrize("body,outcome,retryable", [
    ({"access": True, "status": "409 Conflict", "message": "Class in progress. Please check back after the class ends.",
      "sessionDetailsToSend": None, "attendanceDetails": []}, "in_progress", True),
    ({"access": False, "status": "401 Unauthorized", "message": "Not an Admin", "sessionDetailsToSend": None,
      "attendanceDetails": []}, "error", False),
    ({"access": True, "status": "409 Conflict", "message": "No such meetings", "sessionDetailsToSend": None,
      "attendanceDetails": []}, "error", False),
    ({"access": True, "status": "500 Internal Server Error", "message": "Failed to send data to webhook",
      "sessionDetailsToSend": None, "attendanceDetails": []}, "error", True),
])
async def test_request_attendance_errors_are_read_from_body(real_mode, monkeypatch, body, outcome, retryable):
    monkeypatch.setattr(settings, "classify_creator_email", "admin@guvi.in")
    # Documented: every error still returns HTTP 200.
    respx.post("https://apiclassify.zenclass.in/send-attendance-details").mock(return_value=httpx.Response(200, json=body))
    result = await ClassifyService().request_attendance(_meeting())
    assert result.outcome == outcome and result.retryable is retryable


async def test_request_attendance_requires_creator_email(real_mode, monkeypatch):
    monkeypatch.setattr(settings, "classify_creator_email", "")
    result = await ClassifyService().request_attendance(_meeting())
    assert result.outcome == "error" and result.retryable is False and "CLASSIFY_CREATOR_EMAIL" in result.message
