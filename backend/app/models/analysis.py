"""Strict schema for Gemini sales-conversation analysis.

Gemini output is parsed into `SalesAnalysis`; anything that does not validate
is rejected (and retried) instead of being stored as free-form text. The model
separates what the lead *explicitly said* (`explicit_statements`, `evidence`
quotes) from what the model *infers* (`ai_interpretations`)."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

LevelT = Literal["high", "medium", "low", "unknown"]
SentimentT = Literal["positive", "neutral", "negative", "mixed", "unknown"]
SpeakerT = Literal["lead", "sales", "unknown"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _coerce_level(value):
    if value is None:
        return "unknown"
    v = str(value).strip().lower()
    return v if v in {"high", "medium", "low", "unknown"} else "unknown"


def _coerce_sentiment(value):
    if value is None:
        return "unknown"
    v = str(value).strip().lower()
    return v if v in {"positive", "neutral", "negative", "mixed", "unknown"} else "unknown"


_CATEGORY_SYNONYMS = {
    "pricing": "price", "cost": "price", "budget": "price", "fees": "price",
    "time commitment": "time", "timing": "time", "schedule": "time",
    "parent approval": "approval", "authority": "approval", "decision": "approval",
    "competitor": "competition", "competitors": "competition",
    "uncertain": "uncertainty", "doubt": "uncertainty",
}


def _coerce_speaker(value):
    v = str(value or "unknown").strip().lower()
    if v in {"lead", "prospect", "customer", "student", "client"}:
        return "lead"
    if v in {"sales", "salesperson", "sales person", "sales_rep", "rep", "host", "agent", "counsellor", "counselor"}:
        return "sales"
    return "unknown"


class ExplicitStatement(_Strict):
    speaker: SpeakerT = "lead"
    quote: str = Field(..., min_length=1, description="Verbatim or near-verbatim words from the transcript")
    topic: str = ""
    timestamp: Optional[str] = Field(None, description="Transcript timestamp if available, else null")

    @field_validator("speaker", mode="before")
    @classmethod
    def _spk(cls, v):
        return _coerce_speaker(v)


class Interpretation(_Strict):
    interpretation: str = Field(..., min_length=1)
    basis: str = Field("", description="Transcript evidence the inference is based on")
    confidence: float = Field(0.5, ge=0, le=1)


class Question(_Strict):
    question: str = Field(..., min_length=1)
    answered: Optional[bool] = None
    evidence: str = ""


class Objection(_Strict):
    objection: str = Field(..., min_length=1)
    category: Literal["price", "time", "approval", "competition", "uncertainty", "relevance", "other"] = "other"
    evidence: str = ""
    handled: Optional[bool] = None
    handling_notes: str = ""

    @field_validator("category", mode="before")
    @classmethod
    def _cat(cls, v):
        v = str(v or "other").strip().lower()
        v = _CATEGORY_SYNONYMS.get(v, v)
        return v if v in {"price", "time", "approval", "competition", "uncertainty", "relevance", "other"} else "other"


class Signal(_Strict):
    signal: str = Field(..., min_length=1)
    evidence: str = ""


class PricingDiscussion(_Strict):
    discussed: bool = False
    details: str = ""


class SalesPitch(_Strict):
    pitch_detected: bool = False
    topics_covered: List[str] = Field(default_factory=list)
    missing_topics: List[str] = Field(default_factory=list)


class PitchCoverageItem(_Strict):
    topic: str
    covered: bool = False
    confidence: float = Field(0.5, ge=0, le=1)
    evidence: str = ""


class FollowUp(_Strict):
    required: bool = False
    reason: str = ""
    recommended_next_action: str = ""
    suggested_timing: str = ""
    suggested_follow_up_date: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD) or null")


class ActionItem(_Strict):
    owner: Literal["sales", "lead", "unknown"] = "sales"
    item: str = Field(..., min_length=1)
    due_hint: str = ""

    @field_validator("owner", mode="before")
    @classmethod
    def _owner(cls, v):
        v = str(v or "sales").lower()
        return v if v in {"sales", "lead", "unknown"} else "unknown"


class Engagement(_Strict):
    level: LevelT = "unknown"
    signals: List[Signal] = Field(default_factory=list)
    rationale: str = ""

    @field_validator("level", mode="before")
    @classmethod
    def _lvl(cls, v):
        return _coerce_level(v)


class SalesAnalysis(_Strict):
    summary: str = Field(..., min_length=1)
    conversation_language: str = "unknown"
    lead_intent: str = ""
    interest_level: LevelT = "unknown"
    purchase_intent: LevelT = "unknown"
    lead_sentiment: SentimentT = "unknown"
    sales_sentiment: SentimentT = "unknown"
    engagement: Engagement = Field(default_factory=Engagement)

    topics_discussed: List[str] = Field(default_factory=list)
    lead_questions: List[Question] = Field(default_factory=list)
    lead_objections: List[Objection] = Field(default_factory=list)
    lead_requirements: List[str] = Field(default_factory=list)
    pain_points: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    competitor_mentions: List[str] = Field(default_factory=list)
    pricing_discussion: PricingDiscussion = Field(default_factory=PricingDiscussion)
    product_discussion: List[str] = Field(default_factory=list)

    sales_pitch: SalesPitch = Field(default_factory=SalesPitch)
    pitch_coverage: List[PitchCoverageItem] = Field(default_factory=list)
    objection_handling: str = ""

    follow_up: FollowUp = Field(default_factory=FollowUp)
    action_items: List[ActionItem] = Field(default_factory=list)
    risk_signals: List[Signal] = Field(default_factory=list)
    positive_signals: List[Signal] = Field(default_factory=list)

    explicit_statements: List[ExplicitStatement] = Field(default_factory=list)
    ai_interpretations: List[Interpretation] = Field(default_factory=list)

    meeting_outcome: str = ""
    confidence: float = Field(0.0, ge=0, le=1)

    @field_validator("interest_level", "purchase_intent", mode="before")
    @classmethod
    def _levels(cls, v):
        return _coerce_level(v)

    @field_validator("lead_sentiment", "sales_sentiment", mode="before")
    @classmethod
    def _sentiments(cls, v):
        return _coerce_sentiment(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0.0
        return v / 100 if v > 1 else max(v, 0.0)


class TranscriptSegment(_Strict):
    speaker: SpeakerT = "unknown"
    speaker_name: str = ""
    start_seconds: Optional[float] = Field(None, ge=0)
    end_seconds: Optional[float] = Field(None, ge=0)
    text: str = Field(..., min_length=1)

    @field_validator("speaker", mode="before")
    @classmethod
    def _spk(cls, v):
        return _coerce_speaker(v)


class TranscriptionResult(_Strict):
    language: str = "unknown"
    has_speaker_labels: bool = False
    has_timestamps: bool = False
    segments: List[TranscriptSegment] = Field(default_factory=list)
