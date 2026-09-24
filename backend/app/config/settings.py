"""Application settings.

Every credential and integration toggle is read from the environment (or a
local `.env` file). Nothing secret is hard-coded and nothing in this module is
ever serialised to the frontend — see `public_integration_status()` for the
safe subset exposed on the Settings page.
"""
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -----------------------------------------------------
    app_env: str = "development"
    app_name: str = "Dora X Classify"
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"
    cors_origins: str = ""  # comma separated; FRONTEND_URL is always allowed
    default_timezone: str = "Asia/Kolkata"
    seed_demo_data: bool = False

    # --- Auth ------------------------------------------------------------
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
    media_token_expire_minutes: int = 15
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    # Created on first start when the users collection is empty.
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_name: str = "Administrator"

    # --- MongoDB ---------------------------------------------------------
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_database: str = "dora_x_classify"

    # --- Classify (final docs: POST /createMS and SendAttendanceDetails) -----
    classify_api_url: str = "https://apiclassify.zenclass.in"
    classify_create_meeting_path: str = "/createMS"
    classify_attendance_path: str = "/send-attendance-details"
    classify_api_key_header: str = "Authorization-Key"  # "API key checked against a request header"
    classify_api_key: str = ""
    classify_auth_token: str = ""  # body `authToken`
    classify_org_id: str = ""  # body `org_id`
    classify_product: str = "guvi"
    classify_created_by: str = "classify"
    classify_meeting_type: str = "scheduled"
    classify_recording_autostart: str = "on"  # body `autoRecordingStart` (Classify default: off)
    classify_is_end_time_given: str = "on"
    # "student" appears in the createMS docs' example *response* but is not in
    # their documented list of accepted *request* values, and a real createMS
    # call rejected it ("Invalid StudentHMSRole"); `allow-video-audio` is both
    # documented and confirmed working, and fits a sales video call.
    classify_student_hms_role: str = "allow-video-audio"
    classify_enable_chat: str = "on"
    # Leads are external prospects with no Classify account, so meetings use
    # guestConfig.IsGuestParticipantAllowed = true so they can join by filling
    # a short guest form instead of signing in. This requires meetingType
    # "open" with empty batch_data (build_create_payload handles this) — a
    # "scheduled" meeting with pre-registered batch_data rejects guestConfig
    # outright ("Guest access cannot be enabled for a private meeting"),
    # which an earlier attempt hit before Classify's own example clarified
    # the correct shape.
    classify_guest_mode_enabled: bool = True
    classify_guest_collect_email: bool = True
    classify_guest_collect_phone: bool = False
    classify_timezone: str = "Asia/Kolkata"
    classify_thumbnail: str = "Default"
    classify_default_min_duration: int = 1
    classify_default_duration_minutes: int = 30
    classify_email_subject: str = "Your Dora X Classify Sales Meeting"
    classify_email_message: str = "Please join the scheduled meeting using the meeting link."
    classify_email_footer: str = "Dora X Classify"
    # A live createMS call was observed to take longer than the original 20s
    # default and time out client-side (even though it may have succeeded on
    # Classify's side — timeouts are inherently ambiguous with no idempotency
    # key on their end, so we widen the window rather than auto-retry).
    # Kept under the frontend's 60s request timeout for /api/meetings/schedule.
    classify_timeout_seconds: float = 45.0
    # The meeting join link: Classify's own meeting dashboard, keyed by the
    # createMS `uniqueId` as the `session` query param. One link serves both
    # the host and the lead — Classify resolves the role from the signed-in
    # session on classify.zenclass.in.
    classify_meeting_link_base: str = "https://classify.zenclass.in/meet-dashboard-new"
    classify_meeting_link_param: str = "session"
    # Optional override templates (e.g. a white-label domain). Placeholders:
    # {unique_id} {student_code} {host_code} {room_id}. Leave empty to use the
    # documented meeting-dashboard link above.
    classify_student_join_url_template: str = ""
    classify_host_join_url_template: str = ""
    # SendAttendanceDetails documents `Attendedtime` as minutes.
    classify_attendance_time_unit: str = "minutes"
    # SendAttendanceDetails pull: `creator_email` must be a Classify admin account.
    classify_creator_email: str = ""
    classify_attendance_for: str = "meet"
    classify_attendance_sync_delay_minutes: int = 5  # first pull after the scheduled end
    classify_attendance_retry_minutes: int = 10  # retry while "Class in progress" / transient errors
    classify_attendance_max_attempts: int = 12
    classify_mock_mode: bool = True

    # --- Webhooks --------------------------------------------------------
    # Accepted either as the `api-key` header (the documented Classify
    # pattern) or as an HMAC-SHA256 signature in `X-Classify-Signature`.
    webhook_secret: str = ""

    # --- Gemini ----------------------------------------------------------
    gemini_api_key: str = ""
    # gemini-2.5-flash returns 404 "no longer available to new users" on
    # newly-created API keys. gemini-3.6-flash worked but was observed
    # failing our real (long system prompt + strict JSON schema) analysis
    # request with 503 "high demand" repeatedly — confirmed not a payload
    # problem, since the same request succeeds reliably on the flash-lite
    # tier. "-latest" tracks whichever flash-lite Google currently serves,
    # so this shouldn't go stale the way a pinned version number did before.
    gemini_model: str = "gemini-flash-lite-latest"
    gemini_transcription_model: str = ""  # defaults to gemini_model
    gemini_timeout_seconds: float = 300.0
    gemini_mock_mode: bool = True

    # --- Transcription -----------------------------------------------------
    # "whisper" runs a local faster-whisper model over the downloaded
    # recording — free, real, no API key. "gemini" uploads the recording to
    # Gemini's Files API instead (subject to GEMINI_MOCK_MODE).
    transcription_provider: str = "whisper"  # whisper | gemini
    whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # --- Email -----------------------------------------------------------
    email_provider: str = "mock"  # mock | smtp | sendgrid
    email_api_key: str = ""
    email_from: str = "Dora X Classify <no-reply@classify.demo>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_mock_mode: bool = True

    # --- Recording storage ---------------------------------------------------
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "ap-south-1"
    s3_bucket: str = ""
    recording_storage_dir: str = "./storage/recordings"
    recording_max_bytes: int = 2 * 1024 * 1024 * 1024
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    # --- Workers -------------------------------------------------------------
    worker_enabled: bool = True
    worker_poll_seconds: float = 5.0
    max_retry_attempts: int = 3
    retry_backoff_seconds: int = 60
    stage_timeout_minutes: int = 45
    no_show_grace_minutes: int = 30

    @field_validator("classify_api_url", "frontend_url", "backend_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def allowed_origins(self) -> List[str]:
        origins = {self.frontend_url}
        origins.update(o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip())
        return sorted(origins)

    @property
    def transcription_model(self) -> str:
        return self.gemini_transcription_model or self.gemini_model

    def public_integration_status(self) -> dict:
        """Non-secret integration summary for the Settings page."""
        return {
            "environment": self.app_env,
            "timezone": self.default_timezone,
            "classify": {
                "mock_mode": self.classify_mock_mode,
                "configured": bool(self.classify_api_key and self.classify_auth_token),
                "attendance_configured": bool(self.classify_creator_email),
                "api_url": self.classify_api_url,
                "create_path": self.classify_create_meeting_path,
                "attendance_path": self.classify_attendance_path,
                "product": self.classify_product,
                "meeting_type": self.classify_meeting_type,
                "created_by": self.classify_created_by,
                "recording_autostart": self.classify_recording_autostart,
                "guest_mode_enabled": self.classify_guest_mode_enabled,
                "timezone": self.classify_timezone,
                "default_min_duration": self.classify_default_min_duration,
                "meeting_link_base": self.classify_meeting_link_base,
                "join_url_template_configured": bool(self.classify_student_join_url_template),
            },
            "gemini": {
                "mock_mode": self.gemini_mock_mode,
                "configured": bool(self.gemini_api_key),
                "model": self.gemini_model,
            },
            "transcription": {
                "provider": self.transcription_provider,
                "whisper_model": self.whisper_model_size,
            },
            "email": {
                "mock_mode": self.email_mock_mode,
                "provider": self.email_provider,
                "configured": self.email_mock_mode or bool(self.email_api_key or self.smtp_host),
            },
            "recordings": {
                "s3_configured": bool(self.s3_access_key and self.s3_secret_key),
                "region": self.s3_region,
            },
            "webhook": {
                "secret_configured": bool(self.webhook_secret),
                "endpoint": f"{self.backend_url}/api/webhooks/classify",
            },
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()


def reload_settings(**overrides) -> Settings:
    """Used by tests to rebuild settings with overrides."""
    global settings
    get_settings.cache_clear()
    new = Settings(**overrides)
    settings.__dict__.update(new.__dict__)
    return settings

