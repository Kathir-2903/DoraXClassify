from datetime import date, time
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ScheduleMeetingRequest(BaseModel):
    lead_id: str
    meeting_date: date = Field(..., description="Local date in `timezone`", examples=["2026-09-23"])
    meeting_time: time = Field(..., description="Local wall-clock time in `timezone`", examples=["17:00"])
    duration_minutes: int = Field(30, ge=1, le=480, description="Total meeting length in minutes (max 8 h)")
    min_duration: int = Field(1, ge=1, description="Minimum attendee attendance in minutes (Classify `minDuration`)")
    timezone: str = Field("Asia/Kolkata", examples=["Asia/Kolkata"])
    label: Optional[str] = Field(None, max_length=200, description="Defaults to 'Sales Discussion - <lead name>'")
    notes: Optional[str] = Field(None, max_length=2000, description="Passed to Classify as studentNotes")
    send_email: bool = True
    idempotency_key: Optional[str] = Field(
        None, min_length=8, max_length=128, description="Alternative to the Idempotency-Key header"
    )


class SimulateMeetingRequest(BaseModel):
    """Demo-only: fabricate a Classify attendance webhook for a mock meeting."""
    outcome: Literal["completed", "no_show"] = "completed"
    duration_minutes: int = Field(28, ge=1, le=480)
