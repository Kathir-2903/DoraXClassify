"""Classify meeting-infrastructure integration (final API docs).

Two documented endpoints are used:

1. POST {CLASSIFY_API_URL}/createMS — create a scheduled meeting.
   Auth: API key in a request header (`CLASSIFY_API_KEY_HEADER`, default
   `Authorization-Key`) + `authToken`/`product` in the body (admin session).
   Body: label, start_time, end_time, thumbnail, minDuration, batch_data[],
   studentNotes, enable_chat, authToken, subject, message, footer, product,
   created_by, meetingType, hosts[], autoRecordingStart, isEndTimeGiven,
   studentHMSRole, timezone, org_id, repeat.type, isPollEnabled, isQuizEnabled.
   Response: {Access, Status, Message, Details{UniqueId, …}} — keys arrive in
   PascalCase, and some errors (poll/quiz) are sent with HTTP 200, so success is
   decided from the body (`Access` + `Status`), never the HTTP code.

2. POST {CLASSIFY_API_URL}/send-attendance-details — SendAttendanceDetails.
   Body: {for: "meet", uniqueId, product, creator_email}. Always HTTP 200; the
   real status is the body `Status`. Returns SessionDetailsToSend (times as
   "January 02, 2006 3:04 PM", totals, AssetDetails[{type, url}]) and
   AttendanceDetails[{Name, Email, AttendanceStatus "P", Attendedtime (min),
   Role host|student}]. Responds "409 Class in progress" until the session ends.

`/createInstantMeet` is intentionally NOT used. Go's JSON decoder matches field
names case-insensitively, and responses use PascalCase, so every read here is
case-insensitive (`ci_get`).

The join link is Classify's own meeting dashboard, built from the createMS
`uniqueId`: `https://classify.zenclass.in/meet-dashboard-new?session={uniqueId}`
(`build_meeting_link`). One link serves both host and lead. Where a response
field is genuinely undocumented we only use values actually present and keep
raw payloads — nothing is invented.
"""
import base64
import binascii
import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

import httpx

from app.config.settings import settings
from app.middleware.error_handler import AppError
from app.utils.datetime_utils import get_zone, is_valid_timezone, parse_datetime, to_unix, utcnow
from app.utils.validators import is_valid_email

logger = logging.getLogger(__name__)

# Documented accepted values. "student" is additionally accepted because it is
# the value returned in the documented createMS success response.
ALLOWED_HMS_ROLES = {
    "allow-audio-only", "no-permissions", "allow-screenshare-only", "allow-video-only", "allow-video-audio",
    "allow-ss-audio", "allow-video-screenshare", "allow-audio-video-ss", "student",
}
ALLOWED_PRODUCTS = {"guvi", "hackerkid"}
ALLOWED_CREATED_BY = {"classify", "zen"}
ON_OFF = {"on", "off"}
# The docs say "at least 2 minutes"; product requirement is to allow 1-minute
# meetings and let Classify itself be the final word if it disagrees.
MIN_MEETING_SECONDS = 60
MAX_MEETING_SECONDS = 8 * 60 * 60
START_LEAD_SECONDS = 60  # "Start time should be 1 minute ahead of the current time"
CLASSIFY_TIME_FORMAT = "%B %d, %Y %I:%M %p"  # Go layout "January 02, 2006 3:04 PM"


# --------------------------------------------------------------------------
# Case-insensitive access (Classify responses are PascalCase)
# --------------------------------------------------------------------------
def ci_get(obj: Any, *names: str, default: Any = None) -> Any:
    """Return the first matching key, ignoring case (and `_` in names)."""
    if not isinstance(obj, dict):
        return default
    lowered = {str(k).lower(): v for k, v in obj.items()}
    for name in names:
        n = name.lower()
        if n in lowered:
            return lowered[n]
        n2 = n.replace("_", "")
        for k, v in lowered.items():
            if k.replace("_", "") == n2:
                return v
    return default


def _norm(message: str) -> str:
    return re.sub(r"\s+", " ", (message or "").strip().lower())


# Documented Classify messages → user-facing reason + hint.
FRIENDLY_ERRORS = {
    "empty/missing request body": ("The meeting request was empty.", "Please try again."),
    "unauthorized key": ("The Classify integration key was rejected.", "Ask an administrator to verify CLASSIFY_API_KEY."),
    "session invalid": ("The Classify organisation token is invalid or expired.", "Ask an administrator to refresh CLASSIFY_AUTH_TOKEN."),
    "empty/wrong meet label": ("The meeting title is missing.", "Add a meeting title."),
    "meet label should have at least 4 letters": ("The meeting title is too short.", "Use at least 4 characters."),
    "empty/wrong enable chat value": ("Chat configuration is invalid.", "Ask an administrator to check CLASSIFY_ENABLE_CHAT (on/off)."),
    "empty/wrong meetingtype value": ("The meeting type is invalid.", "Only scheduled meetings are supported."),
    "empty/wrong start time": ("The meeting start time is missing.", "Please select a date and time."),
    "empty/wrong end time": ("The meeting end time is missing.", "Please select a duration."),
    "start time should be greater than current time": ("Meeting start time must be in the future.", "Please select another time."),
    "end time should be greater than start time": ("The meeting must end after it starts.", "Please choose a longer duration."),
    "meet duration should be at least 2 minutes": ("Meetings must be at least 2 minutes long.", "Please choose a longer duration."),
    "meet duration should be at least 1 minute": ("Meetings must be at least 1 minute long.", "Please choose a longer duration."),
    "empty/wrong minduration": ("Minimum attendance must be at least 1 minute.", "Set minimum attendance to 1 minute or more."),
    "minduration must be less than class duration": ("Minimum attendance cannot exceed the meeting duration.", "Reduce minimum attendance or extend the meeting."),
    "meet duration should not be more than 8 hours": ("Meetings cannot be longer than 8 hours.", "Please choose a shorter duration."),
    "wrong createdbyvalue": ("The meeting creator setting is invalid.", "Ask an administrator to check CLASSIFY_CREATED_BY."),
    "empty/wrong batch data": ("The lead's name or email is not accepted by Classify.", "Check the lead's name and email address."),
    "batch data cannot be empty unless it's an open meet": ("A lead must be invited to the meeting.", "Select a lead with a valid email."),
    "duplicate student email id's found in batch data": ("The lead email appears more than once.", "Check the lead's email."),
    "empty/wrong thumbnail": ("The meeting thumbnail is invalid.", "Ask an administrator to check CLASSIFY_THUMBNAIL."),
    "empty/wrong hosts": ("The sales person's email is not valid for Classify.", "Update your profile email and retry."),
    "duplicate host email id's found": ("The host list contains duplicates.", "Please try again."),
    "host email found in student list": ("The lead's email is the same as the sales person's email.", "Use a different lead email."),
    "empty/wrong subjectmail": ("The invitation subject is empty.", "Ask an administrator to set CLASSIFY_EMAIL_SUBJECT."),
    "empty/wrong messagemail": ("The invitation message is empty.", "Ask an administrator to set CLASSIFY_EMAIL_MESSAGE."),
    "empty/wrong footermail": ("The invitation footer is empty.", "Ask an administrator to set CLASSIFY_EMAIL_FOOTER."),
    "empty/wrong product": ("The Classify product setting is invalid.", "Ask an administrator to check CLASSIFY_PRODUCT."),
    "empty/wrong autorecordingstart value": ("The recording setting is invalid.", "Ask an administrator to check CLASSIFY_RECORDING_AUTOSTART (on/off)."),
    "cannot create meet": ("Classify could not create the meeting right now.", "Please try again in a few minutes."),
    "invalid studenthmsrole": ("The attendee permission role is invalid.", "Ask an administrator to check CLASSIFY_STUDENT_HMS_ROLE."),
    "no such timezone": ("The selected timezone is not supported.", "Choose a different timezone."),
    "isendtime given should not be empty/invalid": ("The end-time setting is invalid.", "Ask an administrator to check CLASSIFY_IS_END_TIME_GIVEN."),
    # Final createMS docs
    "no poll ids provided": ("Polls were enabled without any poll template.", "Disable polls or choose a poll template."),
    "invalid poll id or poll id not found": ("A poll template was not found for this organisation.", "Check the poll templates configured in Classify."),
    "no quiz ids provided": ("Quizzes were enabled without any quiz template.", "Disable quizzes or choose a quiz template."),
    "invalid quiz id or quiz id not found": ("A quiz template was not found for this organisation.", "Check the quiz templates configured in Classify."),
    "cannot create recurring meet due to payload/scheduling error": ("Classify could not schedule the recurring meeting.", "Please try again in a few minutes."),
    "cannot schedule all jobs for meeting": ("Classify could not schedule the meeting's background jobs.", "Please try again in a few minutes."),
    "error processing request": ("Classify had an internal error while syncing participants.", "Please try again in a few minutes."),
    "error enqueuing job": ("Classify had an internal error while syncing participants.", "Please try again in a few minutes."),
}

WEBHOOK_REGISTRATION_WARNING = "cannot schedule send attendace details"


class ClassifyError(AppError):
    def __init__(self, classify_message: str, http_status: int = 400, status_text: str = ""):
        key = _norm(classify_message)
        reason, hint = FRIENDLY_ERRORS.get(key, (classify_message or "Classify rejected the request.", "Please try again."))
        if key.startswith(("invalid field type", "invalid field name", "dropdown field")):
            reason, hint = f"Guest information form is invalid: {classify_message}.", "Check the guest form configuration."
        status_code, code = 400, "classify_validation_error"
        if "401" in status_text or http_status == 401:
            status_code, code = 502, "classify_auth_error"
        elif "409" in status_text or http_status == 409:
            status_code, code = 409, "classify_conflict"
        elif "500" in status_text or http_status >= 500:
            status_code, code = 502, "classify_unavailable"
        super().__init__(
            "Unable to schedule meeting.", status_code=status_code, code=code, reason=reason, hint=hint,
            details={"classify_message": classify_message, "classify_status": status_text or str(http_status)},
        )
        self.classify_message = classify_message


@dataclass
class Participant:
    name: str
    email: str


@dataclass
class ScheduledMeetingInput:
    label: str
    start_unix: int
    end_unix: int
    lead: Participant
    host: Participant
    min_duration: int = 1
    student_notes: str = ""
    timezone: str = "Asia/Kolkata"
    extra_hosts: List[Participant] = field(default_factory=list)


def _clean_name(name: str) -> str:
    # createMS: "names trimmed"; older docs: "no spacing in name/email" — we
    # remove leading/trailing/repeated whitespace but keep single inner spaces.
    return " ".join((name or "").split())


ALLOWED_GUEST_FIELD_TYPES = {"text", "email", "phone_number", "single_dropdown"}


def build_guest_config() -> Optional[Dict[str, Any]]:
    """Leads are external prospects with no Classify login, so guest join is
    enabled by default. Classify always injects a required "Name" field
    first; we only add the extra fields configured below."""
    if not settings.classify_guest_mode_enabled:
        return None
    fields: List[Dict[str, Any]] = []
    if settings.classify_guest_collect_email:
        fields.append({"FieldType": "email", "FieldName": "Email"})
    if settings.classify_guest_collect_phone:
        fields.append({"FieldType": "phone_number", "FieldName": "Phone"})
    return {"IsGuestParticipantAllowed": True, "GuestInformationCollectionFields": fields}


def normalized_auth_token() -> str:
    """Classify's own documented request examples show `authToken` values with
    an `auth:` prefix (e.g. `"auth:2a85b3a9aa621f..."`, identical in both the
    original and final createMS docs) — it looks like a load-bearing part of
    the token format, not documentation flourish. Admin panels sometimes hand
    out the token without it, so we add it defensively if it's missing."""
    token = settings.classify_auth_token
    if token and not token.startswith("auth:"):
        return f"auth:{token}"
    return token


def build_create_payload(data: ScheduledMeetingInput) -> Dict[str, Any]:
    """Construct the createMS body. Defaults come from settings.

    A guest-enabled meeting must be created with meetingType "open" and empty
    batch_data — a confirmed example from Classify support shows this exact
    shape. A "scheduled" meeting with pre-registered batch_data rejects
    guestConfig outright ("Guest access cannot be enabled for a private
    meeting"), which is what an earlier attempt hit before this was known."""
    hosts = [data.host, *data.extra_hosts]
    recording = settings.classify_recording_autostart
    guest_config = build_guest_config()
    guest_enabled = guest_config is not None
    return {
        "label": data.label.strip(),
        "start_time": int(data.start_unix),
        "end_time": int(data.end_unix),
        "thumbnail": settings.classify_thumbnail,
        "minDuration": int(data.min_duration),
        "batch_data": [] if guest_enabled else [{"name": _clean_name(data.lead.name), "email": data.lead.email.strip().lower()}],
        "studentNotes": data.student_notes or "",
        "enable_chat": settings.classify_enable_chat,
        "authToken": normalized_auth_token(),
        "subject": settings.classify_email_subject,
        "message": settings.classify_email_message,
        "footer": settings.classify_email_footer,
        "product": settings.classify_product,
        "created_by": settings.classify_created_by,
        "meetingType": "open" if guest_enabled else settings.classify_meeting_type,
        "hosts": [{"name": _clean_name(h.name), "email": h.email.strip().lower()} for h in hosts],
        # Final createMS docs name this `autoRecordingStart`; the earlier
        # scheduled-meet docs used `recording_autoStart`. Both carry the same
        # value; Classify ignores the key it does not recognise.
        "autoRecordingStart": recording,
        "recording_autoStart": recording,
        "isEndTimeGiven": settings.classify_is_end_time_given,
        "studentHMSRole": settings.classify_student_hms_role,
        "timezone": data.timezone or settings.classify_timezone,
        "org_id": settings.classify_org_id,
        # The guest-mode example names this `repeatSchedule` instead of
        # `repeat` — sent under both keys, same as autoRecordingStart above.
        "repeat": {"type": "noRepeat"},  # one-off meeting
        "repeatSchedule": {"type": "noRepeat"},
        "isPollEnabled": False,
        "isQuizEnabled": False,
        **({"guestConfig": guest_config} if guest_config else {}),
    }


def _is_base64(value: str) -> bool:
    try:
        payload = value.split(",", 1)[1] if value.startswith("data:") else value
        base64.b64decode(payload, validate=True)
        return len(payload) > 16
    except (binascii.Error, ValueError, IndexError):
        return False


def validate_create_payload(payload: Dict[str, Any], now_unix: Optional[int] = None) -> None:
    """Mirror Classify's documented validation so users get instant, specific
    feedback before a network round-trip. Raises ClassifyError with the same
    message Classify itself would return."""
    now_unix = now_unix if now_unix is not None else to_unix(utcnow())

    def fail(msg: str) -> None:
        raise ClassifyError(msg, 400, "400 Bad Request (pre-validation)")

    label = (payload.get("label") or "").strip()
    if not label:
        fail("Empty/Wrong Meet label")
    if len(label) < 4:
        fail("Meet Label should have at least 4 letters")
    if payload.get("enable_chat") not in ON_OFF:
        fail("Empty/Wrong Enable Chat value")
    if payload.get("meetingType") not in ("scheduled", "open"):
        fail("Empty/Wrong meetingType value")

    start, end = payload.get("start_time"), payload.get("end_time")
    if not isinstance(start, int) or start <= 0:
        fail("Empty/Wrong Start time")
    if not isinstance(end, int) or end <= 0:
        fail("Empty/Wrong End time")
    if start < now_unix + START_LEAD_SECONDS:
        fail("Start time should be greater than current time")
    if end <= start:
        fail("End time should be greater than Start time")
    duration = end - start
    if duration < MIN_MEETING_SECONDS:
        fail("Meet Duration should be at least 1 minute")
    if duration > MAX_MEETING_SECONDS:
        fail("Meet Duration should not be more than 8 hours")

    min_duration = payload.get("minDuration")
    if not isinstance(min_duration, (int, float)) or min_duration <= 0:
        fail("Empty/Wrong MinDuration")
    if min_duration * 60 > duration:
        fail("MinDuration must be less than Class duration")

    if payload.get("created_by") not in ALLOWED_CREATED_BY:
        fail("Wrong CreatedByValue")

    batch = payload.get("batch_data") or []
    if not batch and payload.get("meetingType") != "open":
        fail("Batch data cannot be empty unless it's an open meet")
    student_emails = []
    for entry in batch:
        name, email = (entry or {}).get("name", ""), (entry or {}).get("email", "")
        if not name or not email or name != name.strip() or " " in email or not is_valid_email(email):
            fail("Empty/Wrong Batch data")
        student_emails.append(email.lower())
    if len(set(student_emails)) != len(student_emails):
        fail("Duplicate Student Email Id's found in Batch Data")

    thumbnail = payload.get("thumbnail") or ""
    if thumbnail != "Default" and not _is_base64(thumbnail):
        fail("Empty/Wrong Thumbnail")

    hosts = payload.get("hosts") or []
    if not hosts:
        fail("Empty/Wrong Hosts")
    host_emails = []
    for host in hosts:
        email = (host or {}).get("email", "")
        if not email or not is_valid_email(email):
            fail("Empty/Wrong Hosts")
        host_emails.append(email.lower())
    if len(set(host_emails)) != len(host_emails):
        fail("Duplicate Host Email Id's found")
    if set(host_emails) & set(student_emails):
        fail("Host email found in student list")

    for key, msg in (("subject", "Empty/Wrong SubjectMail"), ("message", "Empty/Wrong MessageMail"), ("footer", "Empty/Wrong FooterMail")):
        if not (payload.get(key) or "").strip():
            fail(msg)
    if payload.get("product") not in ALLOWED_PRODUCTS:
        fail("Empty/Wrong Product")
    if payload.get("autoRecordingStart") not in ON_OFF:
        fail("Empty/Wrong AutoRecordingStart value")
    if payload.get("isEndTimeGiven") not in ON_OFF:
        fail("IsEndTime given should not be empty/Invalid")
    if payload.get("studentHMSRole") not in ALLOWED_HMS_ROLES:
        fail("Invalid StudentHMSRole")
    tz = payload.get("timezone") or ""
    if tz and not is_valid_timezone(tz):
        fail("No such timezone")
    if payload.get("isPollEnabled") and not payload.get("selectedPollTemplateIds"):
        fail("No poll IDs provided")
    if payload.get("isQuizEnabled") and not payload.get("selectedQuizTemplateIds"):
        fail("No quiz IDs provided")

    guest_config = payload.get("guestConfig")
    if guest_config and guest_config.get("IsGuestParticipantAllowed"):
        for gfield in guest_config.get("GuestInformationCollectionFields") or []:
            ftype = gfield.get("FieldType")
            fname = (gfield.get("FieldName") or "").strip()
            if ftype not in ALLOWED_GUEST_FIELD_TYPES:
                fail(f"Invalid field type: {ftype}")
            if len(fname) < 2:
                fail(f"Invalid field name: {fname}")
            if ftype == "single_dropdown" and len(gfield.get("Options") or []) < 2:
                fail(f"Dropdown field '{fname}' must have at least 2 options.")


def _status_ok(body: Dict[str, Any]) -> bool:
    access = ci_get(body, "access")
    access_ok = access is True or str(access).lower() == "true"
    return access_ok and str(ci_get(body, "status", default="")).startswith("200")


def _details(response: Dict[str, Any]) -> Dict[str, Any]:
    details = ci_get(response, "details", "data") or {}
    return details if isinstance(details, dict) else {}


@dataclass
class AttendanceResult:
    """Outcome of one SendAttendanceDetails call."""
    outcome: str  # "ok" | "in_progress" | "error"
    message: str
    status_text: str = ""
    body: Optional[Dict[str, Any]] = None
    retryable: bool = True


# SendAttendanceDetails messages → (friendly text, retryable)
ATTENDANCE_ERRORS = {
    "invalid request body": ("Classify rejected the attendance request body.", False),
    "empty/missing for": ("Attendance request is missing `for`.", False),
    "empty/missing unique id": ("Attendance request is missing the meeting uniqueId.", False),
    "empty/missing product": ("Attendance request is missing the product.", False),
    "wrong product": ("CLASSIFY_PRODUCT must be guvi or hackerkid.", False),
    "not an admin": ("CLASSIFY_CREATOR_EMAIL is not a Classify admin account.", False),
    "for should either be meet or class": ("Attendance `for` must be meet or class.", False),
    "no such live streams": ("Classify has no live stream with this uniqueId.", False),
    "no such meetings": ("Classify has no meeting with this uniqueId.", False),
    "no such timezone": ("Classify could not load its timezone (server issue).", True),
    "cant marshal the data to send to webhook": ("Classify could not serialise the attendance data.", True),
    "failed to send data to webhook": ("Classify could not forward the attendance data.", True),
}
CLASS_IN_PROGRESS = "class in progress"


class ClassifyService:
    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._client = client

    def _headers(self) -> Dict[str, str]:
        return {settings.classify_api_key_header: settings.classify_api_key, "Content-Type": "application/json"}

    async def _post(self, path: str, payload: Dict[str, Any]) -> httpx.Response:
        url = f"{settings.classify_api_url}{path}"
        if self._client is not None:
            return await self._client.post(url, json=payload, headers=self._headers(), timeout=settings.classify_timeout_seconds)
        async with httpx.AsyncClient(timeout=settings.classify_timeout_seconds) as client:
            return await client.post(url, json=payload, headers=self._headers())

    # ------------------------------------------------------------------
    # createMS
    # ------------------------------------------------------------------
    async def create_scheduled_meeting(self, data: ScheduledMeetingInput) -> Dict[str, Any]:
        """Validate, call createMS, and return the full Classify response body.

        Raises ClassifyError with a user-friendly reason on any documented
        failure. The returned dict is stored as `raw_classify_response`."""
        payload = build_create_payload(data)
        validate_create_payload(payload)

        if settings.classify_mock_mode:
            body = mock_create_response(payload)
            logger.info("classify.create_ms.mock", extra={"classify_unique_id": extract_unique_id(body)})
            return body

        if not settings.classify_api_key or not settings.classify_auth_token:
            raise AppError(
                "Unable to schedule meeting.", status_code=503, code="classify_not_configured",
                reason="The Classify integration is not configured.",
                hint="Ask an administrator to set CLASSIFY_API_KEY and CLASSIFY_AUTH_TOKEN, or enable CLASSIFY_MOCK_MODE.",
            )

        started = time.monotonic()
        try:
            response = await self._post(settings.classify_create_meeting_path, payload)
        except httpx.TimeoutException:
            logger.warning("classify.create_ms.timeout", extra={"waited_seconds": round(time.monotonic() - started, 1),
                                                                "configured_timeout": settings.classify_timeout_seconds})
            raise AppError("Unable to schedule meeting.", status_code=504, code="classify_timeout",
                           reason="Classify did not respond in time.", hint="Please try again in a moment.")
        except httpx.HTTPError as exc:
            logger.warning("classify.create_ms.network_error", extra={"error": type(exc).__name__,
                                                                      "waited_seconds": round(time.monotonic() - started, 1)})
            raise AppError("Unable to schedule meeting.", status_code=502, code="classify_unavailable",
                           reason="Could not reach Classify.", hint="Please try again in a moment.")

        try:
            body = response.json()
        except ValueError:
            # "A Mongo error here aborts the request and returns the raw error (not a formatted response)."
            logger.warning("classify.create_ms.non_json", extra={"status": response.status_code})
            raise ClassifyError("Cannot create meet", response.status_code or 502, str(response.status_code))
        if not isinstance(body, dict):
            raise ClassifyError("Cannot create meet", response.status_code, str(response.status_code))

        message = str(ci_get(body, "message", default=""))
        status_text = str(ci_get(body, "status", default=""))
        details = _details(body)

        if _status_ok(body) and details:
            logger.info("classify.create_ms.success", extra={"classify_unique_id": extract_unique_id(body),
                                                              "waited_seconds": round(time.monotonic() - started, 1)})
            return body

        # Meeting created, but attendance-webhook registration failed (older docs).
        if WEBHOOK_REGISTRATION_WARNING in _norm(message) and extract_unique_id(body):
            logger.warning("classify.create_ms.webhook_registration_failed", extra={"classify_unique_id": extract_unique_id(body)})
            body["_warning"] = "attendance_webhook_not_registered"
            return body

        logger.warning("classify.create_ms.rejected", extra={"status": status_text or response.status_code, "classify_message": message})
        raise ClassifyError(message, response.status_code, status_text)

    # ------------------------------------------------------------------
    # SendAttendanceDetails
    # ------------------------------------------------------------------
    async def request_attendance(self, meeting: Dict[str, Any]) -> AttendanceResult:
        """Pull attendance + assets for a finished meeting. Never raises."""
        unique_id = (meeting.get("classify") or {}).get("unique_id")
        if not unique_id:
            return AttendanceResult("error", "Meeting has no Classify uniqueId", retryable=False)

        if settings.classify_mock_mode:
            if utcnow() < meeting["schedule"]["end_time"]:
                return AttendanceResult("in_progress", "Class in progress. Please check back after the class ends.", "409 Conflict")
            body = mock_attendance_response(meeting)
            return AttendanceResult("ok", "Details sent successfully", "200 OK", body)

        if not settings.classify_api_key:
            return AttendanceResult("error", "CLASSIFY_API_KEY is not configured", retryable=False)
        if not settings.classify_creator_email:
            return AttendanceResult("error", "CLASSIFY_CREATOR_EMAIL (a Classify admin email) is not configured", retryable=False)

        payload = {
            "for": settings.classify_attendance_for,
            "uniqueId": unique_id,
            "product": settings.classify_product,
            "creator_email": settings.classify_creator_email,
        }
        try:
            response = await self._post(settings.classify_attendance_path, payload)
            body = response.json()
        except httpx.HTTPError as exc:
            return AttendanceResult("error", f"Could not reach Classify ({type(exc).__name__})")
        except ValueError:
            return AttendanceResult("error", f"Unexpected response from Classify (HTTP {response.status_code})")
        if not isinstance(body, dict):
            return AttendanceResult("error", "Unexpected response from Classify")

        message = str(ci_get(body, "message", default=""))
        status_text = str(ci_get(body, "status", default=""))
        key = _norm(message)
        # Classify has been observed sending both `sessionDetailsToSend` (the
        # documented key) and `sessionDetails` (a live response for at least
        # guest/open meetings) for the same successful outcome.
        if status_text.startswith("200") and ci_get(body, "sessionDetailsToSend", "sessionDetails") is not None:
            logger.info("classify.attendance.success", extra={"classify_unique_id": unique_id})
            return AttendanceResult("ok", message, status_text, body)
        if CLASS_IN_PROGRESS in key:
            return AttendanceResult("in_progress", message, status_text, body)
        friendly, retryable = ATTENDANCE_ERRORS.get(key, (message or "Classify returned an error", True))
        logger.warning("classify.attendance.rejected", extra={"classify_unique_id": unique_id, "status": status_text,
                                                              "classify_message": message})
        return AttendanceResult("error", friendly, status_text, body, retryable)


classify_service = ClassifyService()


# --------------------------------------------------------------------------
# Mock mode — shaped exactly like the documented responses
# --------------------------------------------------------------------------
def mock_create_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    unique_id = str(uuid.uuid4())
    code = uuid.uuid4().hex
    return {
        "Access": True,
        "Status": "200 OK",
        "Message": "Meet Created successfully",
        "Details": {
            "Label": payload["label"],
            "Start_time": payload["start_time"],
            "End_time": payload["end_time"],
            "MinDuration": payload["minDuration"],
            "Batch_data": payload["batch_data"],
            "UniqueId": unique_id,
            "Hosts": payload["hosts"],
            "Thumbnail": payload["thumbnail"],
            "MeetProvider": "100ms",
            "Totalpresent": 0,
            "AuthToken": "mock-token",
            "Enable_chat": payload["enable_chat"],
            "StudentNotes": payload["studentNotes"],
            "StudentCode": f"std-{code[:10]}",
            "RoomId": f"room-{code[10:22]}",
            "HostCode": f"hst-{code[22:32]}",
            "Recordings": [],
            "Transcripts": [],
            "Product": payload["product"],
            "MeetingType": payload["meetingType"],
            "Created_by": payload["created_by"],
            "Created_at": to_unix(utcnow()),
            "IsEndTimeGiven": payload["isEndTimeGiven"],
            "AutoRecordingStart": payload["autoRecordingStart"],
            "Timezone": payload["timezone"],
            "StudentHMSRole": payload["studentHMSRole"],
            "Repeat": payload["repeat"],
            "_mock": True,
        },
    }


def format_classify_time(dt: datetime) -> str:
    """Go layout "January 02, 2006 3:04 PM" in Asia/Kolkata (hour not zero-padded)."""
    local = dt.astimezone(get_zone(settings.classify_timezone))
    return f"{local:%B %d, %Y} {int(local.strftime('%I'))}:{local:%M %p}"


def mock_attendance_response(meeting: Dict[str, Any], outcome: Optional[str] = None,
                             duration_minutes: Optional[int] = None, end: Optional[datetime] = None) -> Dict[str, Any]:
    """A SendAttendanceDetails success body for a mock meeting.

    Without an explicit outcome, ~85% of meetings complete (deterministic per uniqueId)."""
    unique_id = meeting["classify"]["unique_id"]
    if outcome is None:
        outcome = "completed" if int(hashlib.sha256(unique_id.encode()).hexdigest(), 16) % 100 < 85 else "no_show"
    sched = meeting["schedule"]
    present = outcome == "completed"
    if duration_minutes is None:
        duration_minutes = max(2, int(sched["duration_minutes"]) - 4)
    if end is None:
        start = sched["start_time"] + timedelta(minutes=2)
        end = start + timedelta(minutes=duration_minutes)
    else:
        start = end - timedelta(minutes=duration_minutes)
    lead = meeting["lead_snapshot"]
    host = meeting["sales_person_snapshot"]
    return {
        "Access": True,
        "Status": "200 OK",
        "Message": "Details sent successfully",
        "SessionDetailsToSend": {
            "Label": meeting.get("label"),
            "StartTime": format_classify_time(start),
            "EndTime": format_classify_time(end),
            "TotalPresent": 1 if present else 0,
            "TotalAbsent": 0 if present else 1,
            "TotalStudents": 1,
            "MinimumAttendanceTime": sched.get("min_duration", 1),
            "UniqueId": unique_id,
            "Zen_Product_Type": "",
            "ClassNotes": "",
            "Product": settings.classify_product,
            "AssetDetails": ([{"type": "recording", "url": f"mock://recordings/{unique_id}.mp4"},
                              {"type": "chat", "url": f"mock://chats/{unique_id}.json"}] if present else []),
        },
        "AttendanceDetails": [
            {"Name": lead.get("name"), "Email": lead.get("email"), "AttendanceStatus": "P" if present else "A",
             "Attendedtime": duration_minutes - 1 if present else 0, "Notes": "", "Role": "student", "AttendanceInfo": {}},
            {"Name": host.get("name"), "Email": host.get("email"), "AttendanceStatus": "P",
             "Attendedtime": duration_minutes, "Notes": "", "Role": "host", "AttendanceInfo": {}},
        ],
        "_mock": True,
    }


# --------------------------------------------------------------------------
# Normalisation layer
# --------------------------------------------------------------------------
_STUDENT_URL_KEYS = ("studentJoinUrl", "student_join_url", "studentLink", "student_link", "studentUrl",
                     "joinUrl", "join_url", "joinLink", "join_link", "meetingLink", "meeting_link", "meetingUrl", "meeting_url")
_HOST_URL_KEYS = ("hostJoinUrl", "host_join_url", "hostLink", "host_link", "hostUrl")


def _first_url(obj: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = ci_get(obj, key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def extract_unique_id(response: Dict[str, Any]) -> Optional[str]:
    return ci_get(_details(response), "uniqueId") or None


def extract_room_id(response: Dict[str, Any]) -> Optional[str]:
    return ci_get(_details(response), "roomId") or None


def _format_template(template: str, details: Dict[str, Any]) -> Optional[str]:
    if not template:
        return None
    values = {
        "unique_id": ci_get(details, "uniqueId") or "",
        "student_code": ci_get(details, "studentCode") or "",
        "host_code": ci_get(details, "hostCode") or "",
        "room_id": ci_get(details, "roomId") or "",
        "frontend_url": settings.frontend_url,
    }
    placeholders = set(re.findall(r"{(\w+)}", template))
    if any(not values.get(p) for p in placeholders if p in values):
        return None  # required code missing → do not build a broken link
    try:
        return template.format(**values)
    except (KeyError, IndexError):
        return None


def _mock_template(kind: str) -> str:
    return f"{{frontend_url}}/demo/meeting/{{unique_id}}?as={kind}"


def build_meeting_link(unique_id: str) -> str:
    """The Classify meeting dashboard link, keyed by the createMS `uniqueId`.
    One link serves both the host and the lead."""
    base = settings.classify_meeting_link_base.rstrip("/")
    return f"{base}?{settings.classify_meeting_link_param}={unique_id}"


def _join_url(response: Dict[str, Any], url_keys: Iterable[str], template_setting: str, mock_kind: str) -> Optional[str]:
    details = _details(response)
    # An explicit URL in the response (if Classify ever sends one) always wins.
    direct = _first_url(details, url_keys) or _first_url(response, url_keys)
    if direct:
        return direct
    if details.get("_mock"):
        # Point at our own demo room instead of a real (non-functional) Classify URL.
        return _format_template(_mock_template(mock_kind), details)
    # An admin-configured override (e.g. a white-label domain) takes precedence
    # over the documented link; otherwise build the documented meeting link.
    template = template_setting
    if template:
        formatted = _format_template(template, details)
        if formatted:
            return formatted
    unique_id = extract_unique_id(response)
    return build_meeting_link(unique_id) if unique_id else None


def extract_student_join_url(response: Dict[str, Any]) -> Optional[str]:
    return _join_url(response, _STUDENT_URL_KEYS, settings.classify_student_join_url_template, "lead")


def extract_host_join_url(response: Dict[str, Any]) -> Optional[str]:
    return _join_url(response, _HOST_URL_KEYS, settings.classify_host_join_url_template, "host")


def normalize_created_meeting(response: Dict[str, Any]) -> Dict[str, Any]:
    details = _details(response)
    return {
        "unique_id": extract_unique_id(response),
        "room_id": extract_room_id(response),
        "student_code": ci_get(details, "studentCode") or None,
        "host_code": ci_get(details, "hostCode") or None,
        "meeting_type": ci_get(details, "meetingType") or settings.classify_meeting_type,
        "product": ci_get(details, "product") or settings.classify_product,
        "meet_provider": ci_get(details, "meetProvider") or None,
        "student_join_url": extract_student_join_url(response),
        "host_join_url": extract_host_join_url(response),
        "is_mock": bool(details.get("_mock")),
        "warning": response.get("_warning"),
    }


_MEDIA_EXT = re.compile(r"\.(mp4|webm|mkv|mov|m4a|mp3|wav|ogg|aac|m3u8)(\?|$)", re.I)
_URL_PREFIXES = ("http://", "https://", "s3://", "mock://")


def _collect_urls(value: Any, out: List[str]) -> None:
    if isinstance(value, str):
        v = value.strip()
        if v.startswith(_URL_PREFIXES):
            out.append(v)
    elif isinstance(value, dict):
        for v in value.values():
            _collect_urls(v, out)
    elif isinstance(value, list):
        for v in value:
            _collect_urls(v, out)


def _typed_assets(payload: Any, kind: str) -> List[str]:
    """URLs from documented AssetDetails entries: {"type": "recording", "url": "..."}."""
    found: List[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            t, url = ci_get(obj, "type"), ci_get(obj, "url")
            if isinstance(t, str) and kind in t.lower() and isinstance(url, str) and url.strip().startswith(_URL_PREFIXES):
                found.append(url.strip())
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    return found


def extract_recording_urls(payload: Dict[str, Any]) -> List[str]:
    """Recording URLs: AssetDetails[type=recording] (final docs) plus any URL under
    a recording-named key (older webhook shape). Media-looking URLs first."""
    candidates: List[str] = _typed_assets(payload, "recording")

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if "recording" in str(key).lower() and not isinstance(value, bool):
                    _collect_urls(value, candidates)
                elif isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    seen, ordered = set(), []
    for url in sorted(candidates, key=lambda u: 0 if (_MEDIA_EXT.search(u) or u.startswith(("s3://", "mock://"))) else 1):
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def extract_transcript_entries(payload: Dict[str, Any]) -> List[Any]:
    """Transcript material: AssetDetails[type=transcript] URLs plus anything
    under a transcript-named key."""
    found: List[Any] = list(_typed_assets(payload, "transcript"))

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if "transcript" in str(key).lower() and value not in (None, "", [], {}) and not isinstance(value, bool):
                    found.append(value)
                elif isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    return found


def parse_classify_time(value: Any) -> Optional[datetime]:
    """Unix seconds/ms, ISO-8601, or the documented "January 02, 2006 3:04 PM" (IST)."""
    if value in (None, ""):
        return None
    if isinstance(value, str) and not value.strip().isdigit():
        text = value.strip()
        try:
            local = datetime.strptime(text, CLASSIFY_TIME_FORMAT)
            return local.replace(tzinfo=get_zone(settings.classify_timezone)).astimezone(utcnow().tzinfo)
        except ValueError:
            pass
    return parse_datetime(value)


def _attended_seconds(raw: Any) -> Optional[float]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    unit = settings.classify_attendance_time_unit.lower()
    return value * 60 if unit.startswith("min") else value


def _is_present(entry: Dict[str, Any]) -> Optional[bool]:
    status = str(ci_get(entry, "attendanceStatus", default="")).strip().lower()
    if status in {"p", "present", "attended", "true", "yes", "joined"}:
        return True
    if status in {"a", "absent", "false", "no", "not joined"}:
        return False
    seconds = _attended_seconds(ci_get(entry, "attendedTime"))
    if seconds is not None:
        return seconds > 0
    return None


def normalize_attendance_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise SendAttendanceDetails responses and attendance webhooks.

    Final docs: {Access, Status, Message, SessionDetailsToSend{Label, StartTime,
    EndTime, TotalPresent, TotalAbsent, TotalStudents, MinimumAttendanceTime,
    UniqueId, ClassNotes, Product, AssetDetails[]}, AttendanceDetails[{Name,
    Email, AttendanceStatus, Attendedtime, Notes, Role, AttendanceInfo}]}.
    The older webhook shape (`sessionDetails`) is accepted too."""
    session = ci_get(payload, "sessionDetailsToSend", "sessionDetails") or {}
    if not isinstance(session, dict):
        session = {}
    attendance = ci_get(payload, "attendanceDetails") or []
    if not isinstance(attendance, list):
        attendance = []

    unique_id = ci_get(session, "uniqueId", "meetingId") or ci_get(payload, "uniqueId", "meetingId")
    started = parse_classify_time(ci_get(session, "startTime"))
    ended = parse_classify_time(ci_get(session, "endTime"))
    attendees = []
    for entry in attendance:
        if not isinstance(entry, dict):
            continue
        raw_time = ci_get(entry, "attendedTime")
        attendees.append({
            "name": ci_get(entry, "name"),
            "email": str(ci_get(entry, "email", default="")).strip().lower(),
            "role": str(ci_get(entry, "role", default="") or "").lower() or None,
            "attended_time_raw": raw_time,
            "attended_seconds": _attended_seconds(raw_time),
            "attendance_status": ci_get(entry, "attendanceStatus"),
            "present": _is_present(entry),
            "notes": ci_get(entry, "notes"),
            "joined_at": parse_classify_time(ci_get(entry, "joinedAt", "joinTime")),
            "left_at": parse_classify_time(ci_get(entry, "leftAt", "leaveTime")),
        })

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    total_present = _int(ci_get(session, "totalPresent"))
    return {
        "unique_id": unique_id,
        "label": ci_get(session, "label"),
        "started_at": started,
        "ended_at": ended,
        "duration_seconds": (ended - started).total_seconds() if started and ended and ended > started else None,
        "total_present": total_present,
        "total_absent": _int(ci_get(session, "totalAbsent")),
        "total_students": _int(ci_get(session, "totalStudents")),
        "minimum_attendance_time": ci_get(session, "minimumAttendanceTime", "minimumAttendaceTime"),
        "class_notes": ci_get(session, "classNotes"),
        "attendees": attendees,
        "recording_urls": extract_recording_urls(payload),
        "transcripts": extract_transcript_entries(payload),
        "chat_urls": _typed_assets(payload, "chat"),
        "has_attendance": bool(attendance) or total_present is not None,
    }


# Backwards-compatible name used by the webhook module.
normalize_attendance_webhook = normalize_attendance_payload
