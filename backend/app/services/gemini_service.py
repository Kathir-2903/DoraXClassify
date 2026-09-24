"""Google Gemini integration: transcription and sales-conversation analysis.

The API key is read from GEMINI_API_KEY on the server only. Responses are
requested as JSON and validated against strict Pydantic schemas; an invalid
response gets one repair attempt, then the job fails (and is retried by the
worker) rather than storing unvalidated text."""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from app.config.settings import settings
from app.models.analysis import PitchCoverageItem, SalesAnalysis, TranscriptionResult
from app.prompts.sales_analysis import (
    ANALYSIS_SYSTEM_PROMPT,
    PROMPT_VERSION,
    TRANSCRIPTION_SYSTEM_PROMPT,
    build_analysis_prompt,
    build_repair_prompt,
    build_transcription_prompt,
)
from app.services import mock_data

logger = logging.getLogger(__name__)


class GeminiError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class AnalysisOutput:
    analysis: SalesAnalysis
    model: str
    prompt_version: str
    is_mock: bool
    raw_text: Optional[str] = None
    follow_up_days: Optional[int] = None


@dataclass
class TranscriptionOutput:
    result: TranscriptionResult
    model: str
    is_mock: bool


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_text(text: str) -> Any:
    cleaned = _FENCE.sub("", (text or "").strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def validate_analysis(data: Any, checklist: List[str]) -> SalesAnalysis:
    """Validate Gemini output and align pitch coverage 1:1 with the checklist."""
    analysis = SalesAnalysis.model_validate(data)
    by_topic = {c.topic.strip().lower(): c for c in analysis.pitch_coverage}
    analysis.pitch_coverage = [
        by_topic[t.lower()].model_copy(update={"topic": t})
        if t.lower() in by_topic
        else PitchCoverageItem(topic=t, covered=False, confidence=0.0, evidence="Not evaluated by the model")
        for t in checklist
    ]
    return analysis


class GeminiService:
    def _client(self):
        if not settings.gemini_api_key:
            raise GeminiError("GEMINI_API_KEY is not configured", retryable=False)
        from google import genai
        from google.genai import types

        return genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000)),
        )

    async def _generate_json(self, client, model: str, contents: list, system_prompt: str) -> str:
        from google.genai import types

        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
        except Exception as exc:  # SDK raises its own error hierarchy
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            retryable = status in (None, 408, 429, 500, 502, 503, 504)
            raise GeminiError(f"Gemini request failed ({status or type(exc).__name__})", retryable=retryable) from exc
        text = getattr(response, "text", None)
        if not text:
            raise GeminiError("Gemini returned an empty response")
        return text

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------
    async def transcribe(self, media_path: Optional[str], mime_type: str, context: Dict[str, Any],
                         mock_seed: Optional[str] = None) -> TranscriptionOutput:
        if settings.gemini_mock_mode:
            scenario = mock_data.pick_scenario(mock_seed or context.get("meeting_id", "seed"))
            data = mock_data.mock_transcript(scenario, context.get("lead_name", ""), context.get("sales_person_name", ""),
                                             context.get("product", ""), target_seconds=context.get("duration_seconds"))
            return TranscriptionOutput(TranscriptionResult.model_validate(data), "mock-transcriber", True)
        if not media_path:
            raise GeminiError("No media available to transcribe", retryable=False)

        client = self._client()
        model = settings.transcription_model
        uploaded = None
        try:
            from google.genai import types

            uploaded = await client.aio.files.upload(file=media_path, config=types.UploadFileConfig(mime_type=mime_type))
            for _ in range(120):  # large videos are processed asynchronously by the Files API
                state = getattr(getattr(uploaded, "state", None), "name", "ACTIVE")
                if state == "ACTIVE":
                    break
                if state == "FAILED":
                    raise GeminiError("Gemini could not process the media file", retryable=False)
                await asyncio.sleep(5)
                uploaded = await client.aio.files.get(name=uploaded.name)
            text = await self._generate_json(client, model, [uploaded, build_transcription_prompt(context)],
                                             TRANSCRIPTION_SYSTEM_PROMPT)
            try:
                result = TranscriptionResult.model_validate(parse_json_text(text))
            except (ValueError, ValidationError) as exc:
                raise GeminiError(f"Transcription output failed validation: {type(exc).__name__}") from exc
            if not result.segments:
                raise GeminiError("Transcription returned no speech", retryable=False)
            # Only trust timestamps if every segment has them.
            result.has_timestamps = result.has_timestamps and all(
                s.start_seconds is not None and s.end_seconds is not None for s in result.segments
            )
            result.has_speaker_labels = any(s.speaker != "unknown" for s in result.segments)
            return TranscriptionOutput(result, model, False)
        finally:
            if uploaded is not None:
                try:
                    await client.aio.files.delete(name=uploaded.name)
                except Exception:
                    logger.warning("gemini.file_delete_failed")

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------
    async def analyze(self, transcript_text: str, metadata: Dict[str, Any], checklist: List[str],
                      mock_seed: Optional[str] = None) -> AnalysisOutput:
        if settings.gemini_mock_mode:
            scenario = mock_data.pick_scenario(mock_seed or metadata.get("meeting_id", "seed"))
            data = mock_data.mock_analysis(scenario, metadata.get("lead", {}).get("name", ""),
                                           metadata.get("sales_person", {}).get("name", ""),
                                           metadata.get("lead", {}).get("interested_product") or "", checklist)
            days = data.pop("_follow_up_days", None)
            return AnalysisOutput(validate_analysis(data, checklist), "mock-gemini", PROMPT_VERSION, True,
                                  follow_up_days=days)

        if not transcript_text.strip():
            raise GeminiError("Transcript is empty", retryable=False)
        client = self._client()
        model = settings.gemini_model
        prompt = build_analysis_prompt(transcript_text, metadata, checklist)
        text = await self._generate_json(client, model, [prompt], ANALYSIS_SYSTEM_PROMPT)
        try:
            return AnalysisOutput(validate_analysis(parse_json_text(text), checklist), model, PROMPT_VERSION, False, text)
        except (ValueError, ValidationError) as first_error:
            logger.warning("gemini.analysis_invalid_json", extra={"error": str(first_error)[:300]})
            repair = build_repair_prompt(text, str(first_error)[:1500])
            text2 = await self._generate_json(client, model, [prompt, text, repair], ANALYSIS_SYSTEM_PROMPT)
            try:
                return AnalysisOutput(validate_analysis(parse_json_text(text2), checklist), model, PROMPT_VERSION, False, text2)
            except (ValueError, ValidationError) as exc:
                raise GeminiError("Gemini output did not match the analysis schema after repair") from exc


gemini_service = GeminiService()
