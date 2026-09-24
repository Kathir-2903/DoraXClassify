"""Durable, MongoDB-backed processing pipeline.

    Webhook → (recording) → (transcript) → (analysis) → dashboard

Each stage's state lives on the meeting (`processing.<stage>`), so work
survives restarts and is claimed atomically (safe with several API replicas).
Failures are retried with exponential backoff up to MAX_RETRY_ATTEMPTS; after
that the stage stays `failed` and appears in the admin Processing Monitor."""
import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from pymongo import ReturnDocument

from app.config.settings import settings
from app.constants.analysis_status import Stage, StageStatus
from app.constants.meeting_status import MeetingState
from app.database.mongodb import Collections, get_db
from app.models.analysis import TranscriptionResult
from app.services import attendance_service, followup_service, lead_service, meeting_service, mock_data, notification_service, transcript_service, webhook_service
from app.services.gemini_service import GeminiError, gemini_service
from app.services.meeting_state import refresh_flags, timeline_event, transition
from app.services.recording_service import RecordingError, download_recording, extract_audio
from app.services.whisper_service import WhisperError
from app.services.whisper_service import transcribe as whisper_transcribe
from app.utils.datetime_utils import utcnow
from app.workers.analysis_worker import run_analysis

logger = logging.getLogger(__name__)

PREREQUISITES = {
    Stage.RECORDING: {},
    Stage.TRANSCRIPT: {"processing.recording.status": {"$in": [StageStatus.COMPLETED.value, StageStatus.UNAVAILABLE.value]}},
    Stage.ANALYSIS: {"processing.transcript.status": StageStatus.COMPLETED.value},
}
STAGE_STATE = {
    Stage.RECORDING: MeetingState.RECORDING_PROCESSING,
    Stage.TRANSCRIPT: MeetingState.TRANSCRIPT_PROCESSING,
    Stage.ANALYSIS: MeetingState.AI_ANALYSIS_PROCESSING,
}
FAIL_LABELS = {
    Stage.RECORDING: ("recording_failed", "Recording processing failed"),
    Stage.TRANSCRIPT: ("transcript_failed", "Transcript generation failed"),
    Stage.ANALYSIS: ("analysis_failed", "AI analysis failed"),
}


class StageUnavailable(Exception):
    """Source data does not exist (e.g. Classify sent no recording)."""


async def claim(stage: Stage) -> Optional[Dict[str, Any]]:
    now = utcnow()
    key = f"processing.{stage.value}"
    query = {
        "status.meeting_completed": True,
        "status.no_show": {"$ne": True},
        f"{key}.attempt_count": {"$lt": settings.max_retry_attempts},
        "$or": [
            {f"{key}.status": StageStatus.PENDING.value},
            {f"{key}.status": StageStatus.FAILED.value, f"{key}.next_retry_at": {"$ne": None, "$lte": now}},
        ],
        **PREREQUISITES[stage],
    }
    return await get_db()[Collections.MEETINGS].find_one_and_update(
        query,
        {"$set": {f"{key}.status": StageStatus.PROCESSING.value, f"{key}.started_at": now,
                  f"{key}.last_attempt_at": now, f"{key}.next_retry_at": None, "processing.active": True},
         "$inc": {f"{key}.attempt_count": 1}},
        sort=[("updated_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def _complete(meeting_id, stage: Stage, extra: Optional[Dict[str, Any]] = None, event=None) -> None:
    key = f"processing.{stage.value}"
    update: Dict[str, Any] = {"$set": {f"{key}.status": StageStatus.COMPLETED.value, f"{key}.completed_at": utcnow(),
                                       f"{key}.error_message": None, "updated_at": utcnow(), **(extra or {})}}
    if event:
        update["$push"] = {"timeline": event}
    await get_db()[Collections.MEETINGS].update_one({"_id": meeting_id}, update)


async def _mark_unavailable(meeting_id, stage: Stage, reason: str, event=None) -> None:
    key = f"processing.{stage.value}"
    update: Dict[str, Any] = {"$set": {f"{key}.status": StageStatus.UNAVAILABLE.value, f"{key}.error_message": reason,
                                       f"{key}.completed_at": utcnow(), "updated_at": utcnow()}}
    if event:
        update["$push"] = {"timeline": event}
    await get_db()[Collections.MEETINGS].update_one({"_id": meeting_id}, update)


async def _fail(meeting: Dict[str, Any], stage: Stage, message: str, retryable: bool) -> None:
    key = f"processing.{stage.value}"
    attempts = meeting["processing"][stage.value]["attempt_count"]
    final = not retryable or attempts >= settings.max_retry_attempts
    delay = settings.retry_backoff_seconds * (2 ** max(attempts - 1, 0))
    event_key, label = FAIL_LABELS[stage]
    await get_db()[Collections.MEETINGS].update_one(
        {"_id": meeting["_id"]},
        {"$set": {f"{key}.status": StageStatus.FAILED.value, f"{key}.error_message": message[:500],
                  f"{key}.next_retry_at": None if final else utcnow() + timedelta(seconds=delay), "updated_at": utcnow()},
         "$push": {"timeline": timeline_event(event_key, label if final else f"{label} — retrying",
                                              "error" if final else "warning", "system", details=message[:300])}},
    )
    if final:
        await transition(meeting["_id"], MeetingState.FAILED)
    logger.warning("processing.stage_failed", extra={"meeting_id": str(meeting["_id"]), "stage": stage.value,
                                                     "attempt": attempts, "final": final, "error": message[:300]})


# --------------------------------------------------------------------------
# Stage handlers
# --------------------------------------------------------------------------
async def process_recording(meeting: Dict[str, Any]) -> None:
    db = get_db()
    mid = meeting["_id"]
    await transition(mid, MeetingState.RECORDING_PROCESSING)
    rec = await db[Collections.MEETING_RECORDINGS].find_one({"meeting_id": mid}) or {}
    urls = list(rec.get("source_urls") or [])

    if not urls:
        raise StageUnavailable("Classify did not provide a recording for this meeting")

    last_error: Optional[RecordingError] = None
    for url in urls:
        try:
            file = await download_recording(str(mid), url)
            break
        except RecordingError as exc:
            last_error = exc
    else:
        raise last_error or RecordingError("Recording download failed")

    now = utcnow()
    duration = file.duration_seconds or (meeting.get("attendance") or {}).get("duration_seconds")
    await db[Collections.MEETING_RECORDINGS].update_one(
        {"meeting_id": mid},
        {"$set": {"local_path": file.path, "content_type": file.content_type, "size_bytes": file.size_bytes,
                  "duration_seconds": duration, "is_mock": file.is_mock, "status": "completed", "downloaded_at": now,
                  "used_source_index": urls.index(url)}},
        upsert=True,
    )
    await _complete(
        mid, Stage.RECORDING,
        {"status.recording_available": True,
         "recording": {"status": "available", "download_status": "completed", "duration_seconds": duration,
                       "size_bytes": file.size_bytes, "content_type": file.content_type, "is_mock": file.is_mock,
                       "playable": bool(file.path)}},
        timeline_event("recording_available", "Recording Available", "success", "classify",
                       details="Demo recording (mock mode)" if file.is_mock else None),
    )


async def process_transcript(meeting: Dict[str, Any]) -> None:
    db = get_db()
    mid = meeting["_id"]
    await transition(mid, MeetingState.TRANSCRIPT_PROCESSING)
    rec = await db[Collections.MEETING_RECORDINGS].find_one({"meeting_id": mid}) or {}
    lead = meeting["lead_snapshot"]
    host = meeting["sales_person_snapshot"]

    result, source, model, is_mock = None, None, None, False
    if rec.get("classify_transcripts"):
        result = await transcript_service.from_classify_entries(rec["classify_transcripts"], lead, host)
        if result:
            source, model = "classify", None

    if result is None:
        if meeting["processing"]["recording"]["status"] != StageStatus.COMPLETED.value:
            raise StageUnavailable("No recording or transcript is available for this meeting")
        media_path, mime = rec.get("local_path"), rec.get("content_type") or "video/mp4"
        if media_path:
            audio = await extract_audio(media_path)
            if audio:
                media_path, mime = audio, "audio/mpeg"
        lead_doc = await db[Collections.LEADS].find_one({"_id": meeting["lead_id"]}, {"interested_product": 1})
        context = {"meeting_id": str(mid), "lead_name": lead.get("name"), "sales_person_name": host.get("name"),
                   "product": (lead_doc or {}).get("interested_product") or "",
                   "duration_seconds": (meeting.get("attendance") or {}).get("duration_seconds")}

        if media_path is None:
            # No real recording exists at all (a fully-mock Classify meeting) —
            # nothing to run a real transcription engine on, so fall back to a
            # scripted example transcript. Flagged is_mock so the UI can say so.
            scenario = mock_data.pick_scenario(rec.get("mock_scenario") or context["meeting_id"])
            data = mock_data.mock_transcript(scenario, context["lead_name"], context["sales_person_name"],
                                             context["product"], target_seconds=context["duration_seconds"])
            result, model, is_mock, source = TranscriptionResult.model_validate(data), "mock-transcriber", True, "mock"
        elif settings.transcription_provider == "gemini":
            output = await gemini_service.transcribe(media_path, mime, context, mock_seed=rec.get("mock_scenario"))
            result, model, is_mock = output.result, output.model, output.is_mock
            source = "mock" if output.is_mock else "gemini"
        else:
            result = await whisper_transcribe(media_path)
            model, is_mock, source = f"faster-whisper-{settings.whisper_model_size}", False, "whisper"

    doc = await transcript_service.store_transcript(mid, result, source, model, is_mock)
    if rec.get("mock_scenario"):
        await db[Collections.MEETING_TRANSCRIPTS].update_one({"meeting_id": mid}, {"$set": {"mock_scenario": rec["mock_scenario"]}})
    await _complete(
        mid, Stage.TRANSCRIPT,
        {"status.transcript_available": True,
         "transcript": {"status": "available", "source": source, "segment_count": len(doc["segments"]),
                        "has_speaker_labels": doc["has_speaker_labels"], "has_timestamps": doc["has_timestamps"],
                        "language": doc["language"], "is_mock": is_mock}},
        timeline_event("transcript_ready", "Transcript Generated", "success", source,
                       ai=source in ("gemini", "mock", "whisper")),
    )


async def process_analysis(meeting: Dict[str, Any]) -> None:
    await transition(meeting["_id"], MeetingState.AI_ANALYSIS_PROCESSING)
    await run_analysis(meeting, trigger="pipeline")
    await _complete(meeting["_id"], Stage.ANALYSIS)
    await lead_service.refresh_lead_intelligence(meeting["lead_id"])


HANDLERS = {Stage.RECORDING: process_recording, Stage.TRANSCRIPT: process_transcript, Stage.ANALYSIS: process_analysis}


async def run_stage(stage: Stage, meeting: Dict[str, Any]) -> None:
    mid = meeting["_id"]
    try:
        await HANDLERS[stage](meeting)
    except StageUnavailable as exc:
        event_key = {Stage.RECORDING: "recording_missing", Stage.TRANSCRIPT: "transcript_unavailable",
                     Stage.ANALYSIS: "analysis_unavailable"}[stage]
        label = {Stage.RECORDING: "Recording not available", Stage.TRANSCRIPT: "Transcript unavailable",
                 Stage.ANALYSIS: "AI analysis unavailable"}[stage]
        await _mark_unavailable(mid, stage, str(exc), timeline_event(event_key, label, "warning", "system", details=str(exc)))
        if stage == Stage.TRANSCRIPT:
            await _mark_unavailable(mid, Stage.ANALYSIS, "Transcript unavailable")
            await transition(mid, MeetingState.MEETING_COMPLETED)
    except (RecordingError, GeminiError, WhisperError) as exc:
        await _fail(meeting, stage, str(exc), exc.retryable)
    except Exception as exc:  # unexpected: retry, but never crash the worker
        logger.exception("processing.unexpected_error", extra={"meeting_id": str(mid), "stage": stage.value})
        await _fail(meeting, stage, f"Unexpected error: {type(exc).__name__}", True)
    finally:
        await refresh_flags(mid)


async def recover_stuck() -> int:
    """Stages left `processing` by a crashed worker are failed so they retry."""
    cutoff = utcnow() - timedelta(minutes=settings.stage_timeout_minutes)
    count = 0
    for stage in Stage:
        key = f"processing.{stage.value}"
        result = await get_db()[Collections.MEETINGS].update_many(
            {f"{key}.status": StageStatus.PROCESSING.value, f"{key}.started_at": {"$lt": cutoff}},
            {"$set": {f"{key}.status": StageStatus.FAILED.value, f"{key}.error_message": "Timed out",
                      f"{key}.next_retry_at": utcnow()}},
        )
        count += result.modified_count
    return count


async def process_pending_once(max_per_stage: int = 5) -> int:
    """Run every due stage once. Used by the loop and directly by tests/seed."""
    processed = 0
    for stage in (Stage.RECORDING, Stage.TRANSCRIPT, Stage.ANALYSIS):
        for _ in range(max_per_stage):
            meeting = await claim(stage)
            if not meeting:
                break
            await run_stage(stage, meeting)
            processed += 1
    return processed


async def drain(max_rounds: int = 10) -> None:
    """Process until nothing is due (recording → transcript → analysis chain)."""
    for _ in range(max_rounds):
        if not await process_pending_once():
            return


async def retry_stage(meeting_id, stage: Stage) -> None:
    """Admin/owner-triggered retry: reset attempts and requeue the stage."""
    key = f"processing.{stage.value}"
    sets = {f"{key}.status": StageStatus.PENDING.value, f"{key}.attempt_count": 0, f"{key}.next_retry_at": None,
            f"{key}.error_message": None, "processing.active": True, "updated_at": utcnow()}
    later = {Stage.RECORDING: [Stage.TRANSCRIPT, Stage.ANALYSIS], Stage.TRANSCRIPT: [Stage.ANALYSIS], Stage.ANALYSIS: []}[stage]
    for s in later:
        sets.update({f"processing.{s.value}.status": StageStatus.PENDING.value, f"processing.{s.value}.attempt_count": 0,
                     f"processing.{s.value}.error_message": None})
    await get_db()[Collections.MEETINGS].update_one({"_id": meeting_id}, {"$set": sets})
    await transition(meeting_id, STAGE_STATE[stage])
    await refresh_flags(meeting_id)
    processor.wake()


class ProcessingWorker:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._wake = asyncio.Event()
        self._stopping = False
        self._last_sweep = 0.0

    def wake(self) -> None:
        self._wake.set()

    async def _tick(self) -> None:
        await recover_stuck()
        await webhook_service.retry_failed_events()
        await attendance_service.sync_due_meetings()
        await drain(max_rounds=3)
        await notification_service.retry_due_notifications()
        loop_time = asyncio.get_running_loop().time()
        if loop_time - self._last_sweep > 60:
            self._last_sweep = loop_time
            await meeting_service.lifecycle_sweep()
            await followup_service.wake_snoozed()

    async def _run(self) -> None:
        logger.info("worker.started")
        while not self._stopping:
            try:
                await self._tick()
            except Exception:
                logger.exception("worker.tick_failed")
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=settings.worker_poll_seconds)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    def start(self) -> None:
        if self._task is None:
            self._wake = asyncio.Event()
            self._stopping = False
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._task = None


processor = ProcessingWorker()
