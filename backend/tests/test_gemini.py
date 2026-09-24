import json

import pytest
from pydantic import ValidationError

from app.config.settings import settings
from app.constants.analysis_status import DEFAULT_PITCH_CHECKLIST
from app.services import mock_data
from app.services.gemini_service import GeminiError, GeminiService, parse_json_text, validate_analysis
from app.services.transcript_service import parse_caption_text


def test_validate_analysis_coerces_and_aligns_checklist():
    raw = {
        "summary": "Lead discussed pricing.",
        "interest_level": "HIGH",
        "purchase_intent": "maybe",
        "confidence": 87,
        "lead_objections": [{"objection": "Too expensive", "category": "Pricing"}],
        "pitch_coverage": [{"topic": "pricing", "covered": True, "confidence": 0.9, "evidence": "q"}],
    }
    a = validate_analysis(raw, DEFAULT_PITCH_CHECKLIST)
    assert a.interest_level == "high"
    assert a.purchase_intent == "unknown"  # unsupported value never passes through
    assert a.confidence == 0.87
    assert a.lead_objections[0].category == "price"
    assert [c.topic for c in a.pitch_coverage] == DEFAULT_PITCH_CHECKLIST
    pricing = next(c for c in a.pitch_coverage if c.topic == "Pricing")
    assert pricing.covered is True
    intro = next(c for c in a.pitch_coverage if c.topic == "Introduction")
    assert intro.covered is False and intro.evidence == "Not evaluated by the model"


def test_validate_analysis_rejects_missing_summary():
    with pytest.raises(ValidationError):
        validate_analysis({"interest_level": "high"}, DEFAULT_PITCH_CHECKLIST)


def test_parse_json_text_handles_fences_and_noise():
    assert parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_text('Here you go: {"a": 2} thanks') == {"a": 2}
    with pytest.raises(ValueError):
        parse_json_text("no json here")


def test_mock_scenarios_are_schema_valid():
    for key in mock_data.SCENARIO_KEYS:
        raw = mock_data.mock_analysis(key, "Rahul Kumar", "Arjun", "Data Science")
        raw.pop("_follow_up_days")
        a = validate_analysis(raw, DEFAULT_PITCH_CHECKLIST)
        assert a.summary and a.explicit_statements is not None
        t = mock_data.mock_transcript(key, "Rahul Kumar", "Arjun", "Data Science", target_seconds=1800)
        assert t["segments"][-1]["end_seconds"] <= 1800


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    async def generate_content(self, **kwargs):
        self.calls += 1
        return _FakeResponse(self.texts.pop(0))


class _FakeClient:
    def __init__(self, texts):
        self.aio = type("aio", (), {})()
        self.aio.models = _FakeModels(texts)


async def test_real_mode_repairs_invalid_json_once(monkeypatch):
    monkeypatch.setattr(settings, "gemini_mock_mode", False)
    good = mock_data.mock_analysis("time_concern", "Vikram", "Arjun", "Cloud")
    good.pop("_follow_up_days")
    fake = _FakeClient(['{"not": "valid"}', json.dumps(good)])
    service = GeminiService()
    monkeypatch.setattr(service, "_client", lambda: fake)
    out = await service.analyze("SALES: hi\nLEAD: hello", {"meeting_id": "m1"}, DEFAULT_PITCH_CHECKLIST)
    assert fake.aio.models.calls == 2
    assert out.analysis.interest_level == "low" and out.is_mock is False


async def test_real_mode_gives_up_after_failed_repair(monkeypatch):
    monkeypatch.setattr(settings, "gemini_mock_mode", False)
    fake = _FakeClient(["garbage", '{"still": "bad"}'])
    service = GeminiService()
    monkeypatch.setattr(service, "_client", lambda: fake)
    with pytest.raises(GeminiError):
        await service.analyze("SALES: hi", {"meeting_id": "m1"}, DEFAULT_PITCH_CHECKLIST)


async def test_missing_api_key_is_not_retryable(monkeypatch):
    monkeypatch.setattr(settings, "gemini_mock_mode", False)
    monkeypatch.setattr(settings, "gemini_api_key", "")
    with pytest.raises(GeminiError) as exc:
        await GeminiService().analyze("SALES: hi", {}, DEFAULT_PITCH_CHECKLIST)
    assert exc.value.retryable is False


def test_caption_parsing_keeps_only_real_timestamps():
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n<v Arjun>Hello Rahul\n\n00:00:05.000 --> 00:00:07.500\n<v Rahul>Hi there\n"
    result = parse_caption_text(vtt, {"name": "Rahul Kumar"}, {"name": "Arjun Mehta"})
    assert result.has_timestamps is True
    assert [s.speaker for s in result.segments] == ["sales", "lead"]
    plain = parse_caption_text("Arjun: Hello\nRahul: Hi", {"name": "Rahul Kumar"}, {"name": "Arjun Mehta"})
    assert plain.has_timestamps is False
    assert all(s.start_seconds is None for s in plain.segments)
