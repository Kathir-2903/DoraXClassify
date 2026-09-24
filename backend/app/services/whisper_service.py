"""Local speech-to-text via faster-whisper.

A free, real alternative to Gemini's video transcription — no API key, no
per-call cost, so demo/test runs still get a genuine transcript of the real
recording instead of scripted text. The model is loaded once per process and
reused; transcription is CPU-bound so it runs in a thread.

Limitation: faster-whisper transcribes speech but does not perform speaker
diarization, so every segment comes back with speaker "unknown" — unlike a
Classify-supplied transcript or Gemini's video transcription, neither of
which this replaces when a real transcript/API is available."""
import asyncio
import logging
from typing import Optional

from app.config.settings import settings
from app.models.analysis import TranscriptionResult

logger = logging.getLogger(__name__)

_model = None


class WhisperError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        logger.info("whisper.loading_model", extra={"size": settings.whisper_model_size, "device": settings.whisper_device})
        _model = WhisperModel(settings.whisper_model_size, device=settings.whisper_device,
                              compute_type=settings.whisper_compute_type)
    return _model


def _transcribe_sync(media_path: str) -> TranscriptionResult:
    model = _get_model()
    segments, info = model.transcribe(media_path, vad_filter=True)
    out = []
    for s in segments:
        text = (s.text or "").strip()
        if not text:
            continue
        out.append({"speaker": "unknown", "speaker_name": "", "start_seconds": round(max(0.0, s.start), 2),
                    "end_seconds": round(max(0.0, s.end), 2), "text": text})
    return TranscriptionResult(language=info.language or "unknown", has_speaker_labels=False,
                               has_timestamps=bool(out), segments=out)


async def transcribe(media_path: Optional[str]) -> TranscriptionResult:
    if not media_path:
        raise WhisperError("No media available to transcribe", retryable=False)
    try:
        result = await asyncio.to_thread(_transcribe_sync, media_path)
    except WhisperError:
        raise
    except Exception as exc:
        raise WhisperError(f"Local transcription failed: {type(exc).__name__}") from exc
    if not result.segments:
        raise WhisperError("Transcription returned no speech", retryable=False)
    return result
