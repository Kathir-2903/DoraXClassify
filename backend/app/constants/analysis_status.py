"""Processing-stage statuses shared by recording, transcript and analysis jobs."""
from enum import Enum


class StageStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g. no-show: nothing to process
    UNAVAILABLE = "unavailable"  # source data does not exist (no recording URL)


class Stage(str, Enum):
    RECORDING = "recording"
    TRANSCRIPT = "transcript"
    ANALYSIS = "analysis"


STAGE_ORDER = [Stage.RECORDING, Stage.TRANSCRIPT, Stage.ANALYSIS]


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


class Level(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class FollowUpStatus(str, Enum):
    PENDING = "pending"
    SNOOZED = "snoozed"
    COMPLETED = "completed"


class LeadStatus(str, Enum):
    NEW = "new"
    MEETING_SCHEDULED = "meeting_scheduled"
    ENGAGED = "engaged"
    FOLLOW_UP = "follow_up"
    NO_SHOW = "no_show"
    WON = "won"
    LOST = "lost"


class Role(str, Enum):
    ADMIN = "admin"
    SALES = "sales"


ANALYSIS_VERSION = "1.0"

DEFAULT_PITCH_CHECKLIST = [
    "Introduction",
    "Problem Identification",
    "Need Discovery",
    "Product Explanation",
    "Benefits",
    "Course Details",
    "Pricing",
    "Placement",
    "Differentiators",
    "Objection Handling",
    "Next Steps",
    "Call-to-Action",
]
