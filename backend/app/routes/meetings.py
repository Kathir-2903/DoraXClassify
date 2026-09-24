import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
import jwt

from app.config.settings import settings
from app.constants.analysis_status import Stage, StageStatus
from app.constants.meeting_status import MeetingState
from app.database.mongodb import Collections, get_db
from app.dependencies.auth import CurrentUser, get_current_user, require_sales
from app.middleware.error_handler import AppError, NotFoundError
from app.schemas.analysis import ReanalyzeRequest
from app.schemas.meeting import ScheduleMeetingRequest, SimulateMeetingRequest
from app.services import attendance_service, meeting_service, report_service, webhook_service
from app.services.audit_service import log_activity
from app.services.gemini_service import GeminiError
from app.services.meeting_state import refresh_flags, timeline_event, transition
from app.services.recording_service import local_file_for_stream
from app.utils.datetime_utils import utcnow
from app.utils.security import create_media_token, decode_token
from app.utils.serialization import serialize
from app.utils.validators import to_object_id
from app.workers.analysis_worker import run_analysis
from app.workers.meeting_processor import processor, retry_stage

router = APIRouter(prefix="/api/meetings", tags=["Meetings"])

ERRORS = {400: {"description": "Classify rejected the request (user-friendly reason included)"},
          409: {"description": "Duplicate meeting / Classify conflict"},
          502: {"description": "Classify authentication or availability problem"}}


@router.post("/schedule", status_code=201, summary="Schedule a Classify meeting and send invitations (sales only)", responses=ERRORS)
async def schedule(body: ScheduleMeetingRequest, user: CurrentUser = Depends(require_sales),
                   idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", min_length=8, max_length=128)):
    """Validates the request, converts the selected Asia/Kolkata date/time to
    Unix timestamps, calls Classify `POST /createMS`, stores the complete
    response, sends the email invitation and returns the meeting.

    Idempotent: repeating a request with the same `Idempotency-Key` returns the
    original meeting instead of creating a duplicate."""
    return serialize(await meeting_service.schedule_meeting(user, body, idempotency_key))


@router.get("", summary="List meetings")
async def list_meetings(
    user: CurrentUser = Depends(get_current_user),
    q: Optional[str] = None,
    status: Optional[str] = Query(None, description="Comma-separated lifecycle states"),
    sales_person_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    analysis_status: Optional[str] = None,
    follow_up: Optional[str] = Query(None, pattern="^(true|false)$"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    params = {"q": q, "status": status, "sales_person_id": sales_person_id, "lead_id": lead_id,
              "analysis_status": analysis_status, "follow_up": follow_up, "date_from": date_from, "date_to": date_to,
              "order": order, "page": page, "page_size": page_size}
    return serialize(await meeting_service.list_meetings(user, params))


@router.get("/export.csv", summary="Export meetings as CSV")
async def export_meetings(user: CurrentUser = Depends(get_current_user), q: Optional[str] = None,
                          status: Optional[str] = None, sales_person_id: Optional[str] = None,
                          date_from: Optional[str] = None, date_to: Optional[str] = None):
    params = {"q": q, "status": status, "sales_person_id": sales_person_id, "date_from": date_from, "date_to": date_to}
    query = meeting_service.build_meeting_query(user, params)
    await log_activity(user, "export.meetings", "meeting", None, {"filters": {k: v for k, v in params.items() if v}})

    async def rows():
        async for m in get_db()[Collections.MEETINGS].find(query, {"raw_classify_response": 0, "timeline": 0}).sort("schedule.start_time", -1):
            yield report_service.meeting_row(meeting_service.present_meeting(m, user))

    return StreamingResponse(report_service.csv_stream(report_service.MEETING_HEADER, rows()), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="classify-meetings-{utcnow():%Y%m%d-%H%M}.csv"'})


@router.get("/{meeting_id}", summary="Meeting detail with lifecycle, flags, analysis and call quality")
async def get_meeting(meeting_id: str, user: CurrentUser = Depends(get_current_user)):
    return serialize(await meeting_service.get_meeting_detail(user, meeting_id))


@router.get("/{meeting_id}/status", summary="Lightweight status for polling")
async def get_status(meeting_id: str, user: CurrentUser = Depends(get_current_user)):
    m = await meeting_service.get_meeting_for_user(user, meeting_id)
    return serialize({
        "id": m["_id"], "status": m["status"], "processing": m.get("processing"), "flags": m.get("flags"),
        "journey": meeting_service.build_journey(m), "notifications": m.get("notifications"),
        "polling": {"active": meeting_service._should_poll(m), "interval_seconds": 5}, "updated_at": m.get("updated_at"),
    })


@router.post("/{meeting_id}/send-email", summary="Resend the email invitation")
async def send_email(meeting_id: str, user: CurrentUser = Depends(get_current_user)):
    return serialize(await meeting_service.resend_email(user, meeting_id))


@router.get("/{meeting_id}/analysis", summary="Current AI analysis and version history")
async def get_analysis(meeting_id: str, user: CurrentUser = Depends(get_current_user),
                       version_id: Optional[str] = Query(None, description="Specific analysis version")):
    m = await meeting_service.get_meeting_for_user(user, meeting_id)
    db = get_db()
    query = {"meeting_id": m["_id"]}
    query.update({"_id": to_object_id(version_id, "version id")} if version_id else {"is_current": True})
    analysis = await db[Collections.MEETING_ANALYTICS].find_one(query, {"raw_response": 0})
    versions = await db[Collections.MEETING_ANALYTICS].find(
        {"meeting_id": m["_id"]}, {"model": 1, "prompt_version": 1, "analysis_version": 1, "created_at": 1, "is_current": 1, "trigger": 1}
    ).sort("created_at", -1).to_list(length=50)
    return serialize({"status": m["processing"]["analysis"]["status"], "analysis": analysis, "versions": versions,
                      "ai_generated": True})


@router.post("/{meeting_id}/reanalyze", summary="Re-run AI analysis on the stored transcript (no re-download)")
async def reanalyze(meeting_id: str, body: Optional[ReanalyzeRequest] = None, user: CurrentUser = Depends(get_current_user)):
    m = await meeting_service.get_meeting_for_user(user, meeting_id)
    transcript = await get_db()[Collections.MEETING_TRANSCRIPTS].find_one({"meeting_id": m["_id"]}, {"_id": 1})
    if not transcript:
        raise AppError("Transcript unavailable", 409, "transcript_unavailable",
                       hint="Re-analysis uses the stored transcript. Retry transcript processing first.")
    now = utcnow()
    await get_db()[Collections.MEETINGS].update_one(
        {"_id": m["_id"]},
        {"$set": {"processing.analysis.status": StageStatus.PROCESSING.value, "processing.analysis.started_at": now,
                  "processing.analysis.error_message": None},
         "$push": {"timeline": timeline_event("reanalysis_started", "Re-analysis requested", "info", "user",
                                              details=(body.reason if body else None))}},
    )
    await transition(m["_id"], MeetingState.AI_ANALYSIS_PROCESSING)
    await log_activity(user, "meeting.reanalyze", "meeting", m["_id"], {"reason": body.reason if body else None})
    try:
        fresh = await get_db()[Collections.MEETINGS].find_one({"_id": m["_id"]})
        await run_analysis(fresh, trigger="reanalyze", user=user)
        await get_db()[Collections.MEETINGS].update_one(
            {"_id": m["_id"]}, {"$set": {"processing.analysis.status": StageStatus.COMPLETED.value, "processing.analysis.completed_at": utcnow()}})
    except GeminiError as exc:
        await get_db()[Collections.MEETINGS].update_one(
            {"_id": m["_id"]},
            {"$set": {"processing.analysis.status": StageStatus.FAILED.value, "processing.analysis.error_message": str(exc)},
             "$push": {"timeline": timeline_event("analysis_failed", "AI analysis failed", "error", "gemini", details=str(exc))}})
        await transition(m["_id"], MeetingState.FAILED)
        await refresh_flags(m["_id"])
        raise AppError("AI analysis failed", 502, "analysis_failed", reason=str(exc), hint="Try again in a few minutes.")
    return serialize(await meeting_service.get_meeting_detail(user, meeting_id, audit=False))


@router.get("/{meeting_id}/transcript", summary="Transcript segments (optionally filtered)")
async def get_transcript(meeting_id: str, user: CurrentUser = Depends(get_current_user),
                         q: Optional[str] = Query(None, max_length=200, description="Search text")):
    m = await meeting_service.get_meeting_for_user(user, meeting_id)
    t = await get_db()[Collections.MEETING_TRANSCRIPTS].find_one({"meeting_id": m["_id"]}, {"text": 0})
    if not t:
        return serialize({"available": False, "status": m["processing"]["transcript"]["status"],
                          "message": "Transcript unavailable", "segments": []})
    segments = t.get("segments") or []
    if q:
        pattern = re.compile(re.escape(q), re.IGNORECASE)
        segments = [dict(s, index=i) for i, s in enumerate(segments) if pattern.search(s.get("text", ""))]
    else:
        segments = [dict(s, index=i) for i, s in enumerate(segments)]
    return serialize({
        "available": True, "source": t.get("source"), "language": t.get("language"),
        "has_speaker_labels": t.get("has_speaker_labels"), "has_timestamps": t.get("has_timestamps"),
        "is_mock": t.get("is_mock", False), "ai_generated": t.get("source") in ("gemini", "mock", "whisper"),
        "actual_start": (m.get("attendance") or {}).get("actual_start"),
        "total_segments": len(t.get("segments") or []), "segments": segments,
    })


@router.get("/{meeting_id}/transcript/download", summary="Download transcript as text")
async def download_transcript(meeting_id: str, user: CurrentUser = Depends(get_current_user)):
    m = await meeting_service.get_meeting_for_user(user, meeting_id)
    t = await get_db()[Collections.MEETING_TRANSCRIPTS].find_one({"meeting_id": m["_id"]})
    if not t:
        raise NotFoundError("Transcript")
    await log_activity(user, "meeting.transcript_downloaded", "meeting", m["_id"])
    return PlainTextResponse(report_service.transcript_text_file(m, t),
                             headers={"Content-Disposition": f'attachment; filename="transcript-{meeting_id}.txt"'})


@router.get("/{meeting_id}/report.pdf", summary="Download the meeting report as PDF")
async def meeting_report(meeting_id: str, user: CurrentUser = Depends(get_current_user)):
    m = await meeting_service.get_meeting_for_user(user, meeting_id)
    db = get_db()
    lead = await db[Collections.LEADS].find_one({"_id": m["lead_id"]})
    analysis = None
    if (m.get("analysis") or {}).get("current_analysis_id"):
        analysis = await db[Collections.MEETING_ANALYTICS].find_one({"_id": m["analysis"]["current_analysis_id"]})
    transcript = await db[Collections.MEETING_TRANSCRIPTS].find_one({"meeting_id": m["_id"]})
    pdf = report_service.build_meeting_pdf(meeting_service.present_meeting(m, user), lead, analysis, transcript)
    await log_activity(user, "meeting.report_downloaded", "meeting", m["_id"])
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="meeting-report-{meeting_id}.pdf"'})


@router.get("/{meeting_id}/recording", summary="Recording status and a short-lived playback URL")
async def get_recording(meeting_id: str, user: CurrentUser = Depends(get_current_user)):
    """Never returns the source S3 URL. Playback is proxied by the backend
    using a token scoped to this meeting and valid for a few minutes."""
    m = await meeting_service.get_meeting_for_user(user, meeting_id)
    rec = await get_db()[Collections.MEETING_RECORDINGS].find_one({"meeting_id": m["_id"]}) or {}
    playable = bool(local_file_for_stream(rec.get("local_path")))
    return serialize({
        "status": m["processing"]["recording"]["status"],
        "available": bool(m["status"].get("recording_available")),
        "is_mock": rec.get("is_mock", False),
        "duration_seconds": rec.get("duration_seconds"),
        "size_bytes": rec.get("size_bytes"),
        "content_type": rec.get("content_type"),
        "source_count": len(rec.get("source_urls") or []),
        "playable": playable,
        "playback_url": f"/api/meetings/{meeting_id}/recording/stream?token={create_media_token(user.id, meeting_id)}" if playable else None,
        "error": m["processing"]["recording"].get("error_message"),
    })


@router.get("/{meeting_id}/recording/stream", summary="Stream the recording (token from /recording)", include_in_schema=True)
async def stream_recording(meeting_id: str, token: str = Query(...)):
    try:
        payload = decode_token(token, "media")
    except jwt.InvalidTokenError:
        raise AppError("Playback link expired", 401, "media_token_invalid")
    if payload.get("mid") != meeting_id:
        raise AppError("Playback link is not valid for this meeting", 403, "forbidden")
    rec = await get_db()[Collections.MEETING_RECORDINGS].find_one({"meeting_id": to_object_id(meeting_id, "meeting id")})
    path = local_file_for_stream((rec or {}).get("local_path"))
    if not path:
        raise NotFoundError("Recording file")
    return FileResponse(str(path), media_type=rec.get("content_type") or "video/mp4")


@router.post("/{meeting_id}/retry", summary="Retry a failed processing stage")
async def retry(meeting_id: str, stage: Stage = Query(...), user: CurrentUser = Depends(get_current_user)):
    m = await meeting_service.get_meeting_for_user(user, meeting_id)
    if not m["status"].get("meeting_completed") or m["status"].get("no_show"):
        raise AppError("This meeting has nothing to process", 409, "nothing_to_process")
    await retry_stage(m["_id"], stage)
    await log_activity(user, "processing.retry", "meeting", m["_id"], {"stage": stage.value})
    return serialize(await meeting_service.get_meeting_detail(user, meeting_id, audit=False))


@router.post("/{meeting_id}/sync-attendance", summary="Pull attendance + recordings from Classify now (SendAttendanceDetails)",
             responses={409: {"description": "Meeting has not ended yet / nothing to sync"}})
async def sync_attendance(meeting_id: str, user: CurrentUser = Depends(get_current_user)):
    """Calls Classify's SendAttendanceDetails for this meeting immediately
    (the worker also does this automatically after the scheduled end)."""
    m = await meeting_service.get_meeting_for_user(user, meeting_id)
    if not m["status"].get("meeting_created") or not m["classify"].get("unique_id"):
        raise AppError("Meeting was not created in Classify", 409, "meeting_not_created")
    if m["status"].get("meeting_completed"):
        raise AppError("Meeting already has results", 409, "already_completed")
    # A no-show verdict can be re-checked: Classify's attendance API has been
    # observed to omit guest participants entirely even when they genuinely
    # joined (guest mode isn't pre-registered, unlike a batch_data student).
    if m["classify"].get("is_mock") and not settings.classify_mock_mode:
        raise AppError(
            "This is a demo meeting created in mock mode", 409, "mock_meeting",
            reason="Classify has no real record of it, so attendance cannot be fetched.",
            hint="Schedule a new meeting to test the live Classify integration.",
        )
    outcome = await attendance_service.sync_meeting(m, triggered_by=user)
    processor.wake()
    await log_activity(user, "meeting.attendance_sync", "meeting", m["_id"], {"outcome": outcome["outcome"]})
    detail = await meeting_service.get_meeting_detail(user, meeting_id, audit=False)
    detail["sync_result"] = outcome
    return serialize(detail)


@router.post("/{meeting_id}/simulate", summary="Demo only: simulate Classify's SendAttendanceDetails result",
             responses={403: {"description": "Only available when CLASSIFY_MOCK_MODE=true"}})
async def simulate(meeting_id: str, body: Optional[SimulateMeetingRequest] = None, user: CurrentUser = Depends(get_current_user)):
    body = body or SimulateMeetingRequest()
    m = await meeting_service.get_meeting_for_user(user, meeting_id)
    if not settings.classify_mock_mode or not m["classify"].get("is_mock"):
        raise AppError("Simulation is only available for mock-mode meetings", 403, "simulation_disabled")
    if m["status"].get("meeting_completed") or m["status"].get("no_show"):
        raise AppError("This meeting already has results", 409, "already_completed")
    payload = webhook_service.build_simulated_payload(m, body.outcome, body.duration_minutes)
    event_id, _ = await webhook_service.ingest(payload, b"", {"x-event-id": f"sim-{meeting_id}-{body.outcome}"}, source="simulation")
    await webhook_service.process_event(event_id)
    processor.wake()
    await log_activity(user, "meeting.simulated", "meeting", m["_id"], {"outcome": body.outcome})
    return serialize(await meeting_service.get_meeting_detail(user, meeting_id, audit=False))

