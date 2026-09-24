"""Demo seed data — every record is flagged `is_demo: true`.

    python -m app.seed            # seed if the database is empty
    python -m app.seed --reset    # wipe demo-able collections and reseed

Creates 3 users, 10 leads and 20 meetings covering completed meetings with AI
analysis, scheduled meetings, no-shows, objections, follow-ups, an in-flight
processing job and a failed recording."""
import argparse
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.constants.analysis_status import ANALYSIS_VERSION, DEFAULT_PITCH_CHECKLIST, FollowUpStatus, StageStatus
from app.constants.meeting_status import MeetingState
from app.database import mongodb
from app.database.mongodb import Collections
from app.models.analysis import TranscriptionResult
from app.models.lead import journey_event, new_lead_document
from app.models.meeting import new_meeting_document, new_stage
from app.models.user import new_user_document
from app.prompts.sales_analysis import PROMPT_VERSION
from app.services import lead_service, mock_data
from app.services.classify_service import (Participant, ScheduledMeetingInput, build_create_payload,
                                           mock_attendance_response, mock_create_response, normalize_created_meeting)
from app.services.followup_service import due_from_timing
from app.services.gemini_service import validate_analysis
from app.services.meeting_state import compute_flags, timeline_event
from app.services.transcript_service import transcript_to_text
from app.utils.datetime_utils import get_zone, utcnow
from app.utils.security import redact
from app.workers.analysis_worker import build_snapshot

logger = logging.getLogger("app.seed")

USERS = [
    ("Priya Raman", "admin@classify.demo", "Admin@123", "admin", "Sales Operations Lead"),
    ("Arjun Mehta", "arjun@classify.demo", "Sales@123", "sales", "Senior Admissions Counsellor"),
    ("Neha Kapoor", "neha@classify.demo", "Sales@123", "sales", "Admissions Counsellor"),
    ("Kathir Velan S", "kathirvelan@hclguvi.com", "Sales@123", "sales", "Sales Counsellor"),
]

LEADS = [
    ("Rahul Kumar", "rahul.kumar@example.com", "+919876543210", "Paytm", "Website", "Full Stack Development", 1),
    ("Ananya Iyer", "ananya.iyer@example.com", "+919812345670", "Stella Maris College", "Webinar", "Data Science", 2),
    ("Vikram Singh", "vikram.singh@example.com", "+919845012345", "Infosys", "Google Ads", "Cloud & DevOps", 1),
    ("Sneha Reddy", "sneha.reddy@example.com", "+919900112233", "Freshworks", "Referral", "Full Stack Development", 2),
    ("Karthik Nair", "karthik.nair@example.com", "+919633221100", "Zoho", "Website", "Full Stack Development", 1),
    ("Pooja Desai", "pooja.desai@example.com", "+919820098200", None, "Social Media", "UI/UX Design", 2),
    ("Aditya Joshi", "aditya.joshi@example.com", "+919767676767", "VIT Vellore", "Event", "Data Science", 1),
    ("Meera Pillai", "meera.pillai@example.com", "+919446644664", "UST Global", "Website", "Data Science", 2),
    ("Rohan Gupta", "rohan.gupta@example.com", "+919711223344", "HCL Technologies", "Cold Outreach", "Cloud & DevOps", 1),
    ("Farah Khan", "farah.khan@example.com", "+919004455667", "Accenture", "Partner", "UI/UX Design", 2),
]

# (lead index, day offset, local hour, kind, scenario, duration minutes)
MEETINGS = [
    (0, -12, 11, "completed", "pricing_concern", 32),
    (0, -3, 17, "completed", "ready_to_enroll", 18),
    (1, -10, 16, "completed", "parent_approval", 26),
    (1, 1, 18, "scheduled", None, 30),
    (2, -18, 12, "completed", "time_concern", 14),
    (2, -8, 19, "completed", "time_concern", 12),
    (3, -15, 15, "no_show", None, 30),
    (3, -6, 15, "completed", "pricing_concern", 34),
    (4, -14, 10, "completed", "pricing_concern", 29),
    (4, -5, 12, "completed", "ready_to_enroll", 16),
    (5, -4, 14, "no_show", None, 30),
    (5, 2, 11, "scheduled", None, 30),
    (6, -20, 17, "completed", "parent_approval", 24),
    (6, -2, 18, "completed", "pricing_concern", 31),
    (7, -16, 13, "completed", "parent_approval", 27),
    (7, -1, 12, "processing", "pricing_concern", 28),
    (8, -7, 11, "no_show", None, 30),
    (8, 0, None, "scheduled_today", None, 30),
    (9, -9, 16, "failed", "time_concern", 22),
    (9, 4, 15, "scheduled", None, 45),
]


def _at(days: int, hour: Optional[int]) -> datetime:
    zone = get_zone()
    if hour is None:  # later today, rounded to the next half hour + 3h
        now = datetime.now(zone) + timedelta(hours=3)
        local = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
    else:
        local = (datetime.now(zone) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return local.astimezone(utcnow().tzinfo)


def _sent(at: datetime, provider="mock") -> Dict[str, Any]:
    return {"status": "sent", "sent_at": at, "provider": provider, "provider_message_id": f"demo-{uuid.uuid4().hex[:12]}",
            "error": None, "attempt_count": 1, "last_attempt_at": at, "next_retry_at": None}


async def seed_demo_data(db, reset: bool = False) -> Dict[str, int]:
    if reset:
        for name in (Collections.USERS, Collections.LEADS, Collections.MEETINGS, Collections.MEETING_RECORDINGS,
                     Collections.MEETING_TRANSCRIPTS, Collections.MEETING_ANALYTICS, Collections.NOTIFICATIONS,
                     Collections.WEBHOOK_EVENTS, Collections.ACTIVITY_LOGS, Collections.FOLLOW_UPS,
                     Collections.DASHBOARD_SNAPSHOTS, Collections.APP_SETTINGS):
            await db[name].delete_many({})
    elif await db[Collections.USERS].count_documents({}):
        logger.info("seed.skipped_non_empty")
        return {}

    users = []
    for name, email, pwd, role, title in USERS:
        doc = new_user_document(name, email, pwd, role, title, is_demo=True)
        doc["_id"] = (await db[Collections.USERS].insert_one(doc)).inserted_id
        users.append(doc)
    admin = users[0]

    await db[Collections.APP_SETTINGS].update_one({"key": "pitch_checklist"},
                                                  {"$set": {"value": DEFAULT_PITCH_CHECKLIST, "updated_at": utcnow()}}, upsert=True)

    leads = []
    for i, (name, email, phone, company, source, product, sp) in enumerate(LEADS):
        data = {"name": name, "email": email, "phone": phone, "company": company, "lead_source": source,
                "interested_product": product, "notes": "Demo lead created by seed script."}
        doc = new_lead_document(data, users[sp]["_id"], admin["_id"], is_demo=True)
        created = _at(-28 + i, 10)
        doc["created_at"] = doc["updated_at"] = doc["last_activity_at"] = created
        doc["journey"][0]["at"] = created
        doc["_id"] = (await db[Collections.LEADS].insert_one(doc)).inserted_id
        leads.append(doc)

    counts = {"meetings": 0, "analyses": 0, "follow_ups": 0}
    for lead_idx, day, hour, kind, scenario, minutes in MEETINGS:
        lead = leads[lead_idx]
        sales = next(u for u in users if u["_id"] == lead["sales_person_id"])
        start = _at(day, hour)
        end = start + timedelta(minutes=minutes if kind not in ("scheduled", "scheduled_today") else minutes)
        scheduled_at = min(start - timedelta(days=1, hours=2), utcnow() - timedelta(minutes=30))
        label = f"Sales Discussion - {lead['name']}"
        meeting_input = ScheduledMeetingInput(label, int(start.timestamp()), int(end.timestamp()),
                                              Participant(lead["name"], lead["email"]), Participant(sales["name"], sales["email"]))
        response = mock_create_response(build_create_payload(meeting_input))
        doc = new_meeting_document(lead=lead, sales_person=sales, label=label, start_time=start, end_time=end,
                                   timezone=settings.classify_timezone, min_duration=1,
                                   idempotency_key=f"seed-{uuid.uuid4().hex}", created_by=sales["_id"])
        doc.update({"is_demo": True, "created_at": scheduled_at, "updated_at": scheduled_at,
                    "classify": normalize_created_meeting(response), "raw_classify_response": redact(response)})
        st = doc["status"]
        st.update({"overall": MeetingState.INVITATION_SENT.value, "meeting_created": True, "invitation_sent": True,
                   "email_sent": True})
        doc["notifications"] = {"email": _sent(scheduled_at + timedelta(seconds=20))}
        tl = [timeline_event("meeting_scheduled", "Meeting Scheduled", "success", "classify", at=scheduled_at),
              timeline_event("email_sent", "Email Sent", "success", "mock", at=scheduled_at + timedelta(seconds=20)),
              timeline_event("invitation_sent", "Lead Invited", "success", at=scheduled_at + timedelta(seconds=25))]
        journey = [journey_event("meeting_scheduled", "Meeting Scheduled", "user", None, label, at=scheduled_at)]

        analysis_doc = transcript_doc = None
        if kind == "no_show":
            st.update({"overall": MeetingState.NO_SHOW.value, "no_show": True})
            for s in ("recording", "transcript", "analysis"):
                doc["processing"][s] = new_stage(StageStatus.SKIPPED)
            doc["attendance"] = {"received_at": end + timedelta(minutes=5), "actual_start": start, "actual_end": end,
                                 "duration_seconds": minutes * 60, "total_present": 0, "total_absent": 1, "total_students": 1,
                                 "lead": {"email": lead["email"], "present": False, "attendance_status": "absent",
                                          "attended_seconds": 0, "attended_time_raw": 0},
                                 "host": None, "attendees_count": 1, "lead_joined": False, "source": "classify_webhook"}
            doc["webhook_received_at"] = end + timedelta(minutes=5)
            tl += [timeline_event("webhook_received", "Attendance received from Classify", "info", "classify", at=end + timedelta(minutes=5)),
                   timeline_event("no_show", "Lead did not join", "error", "classify", at=end + timedelta(minutes=5),
                                  details="Classify attendance shows the lead did not attend.")]
            journey.append(journey_event("no_show", "Lead did not join", "classify", None, at=end + timedelta(minutes=5)))
        elif kind in ("completed", "processing", "failed"):
            actual_start = start + timedelta(minutes=2)
            actual_end = actual_start + timedelta(minutes=minutes)
            received = actual_end + timedelta(minutes=3)
            st.update({"lead_joined": True, "meeting_started": True, "meeting_completed": True})
            doc["attendance"] = {"received_at": received, "actual_start": actual_start, "actual_end": actual_end,
                                 "duration_seconds": minutes * 60, "total_present": 1, "total_absent": 0, "total_students": 1,
                                 "lead": {"email": lead["email"], "present": True, "attendance_status": "present",
                                          "attended_seconds": (minutes - 1) * 60, "attended_time_raw": minutes - 1},
                                 "host": None, "attendees_count": 1, "lead_joined": True, "source": "classify_webhook"}
            doc["webhook_received_at"] = received
            tl += [timeline_event("lead_joined", "Lead Joined", "success", "classify", at=actual_start),
                   timeline_event("meeting_started", "Meeting Started", "info", "classify", at=actual_start),
                   timeline_event("meeting_completed", "Meeting Completed", "success", "classify", at=actual_end,
                                  details=f"Duration {minutes} min"),
                   timeline_event("webhook_received", "Attendance received from Classify", "info", "classify", at=received)]
            journey.append(journey_event("meeting_completed", "Meeting Completed", "classify", None, f"{minutes} min", at=actual_end))

            if kind == "processing":
                st["overall"] = MeetingState.RECORDING_PROCESSING.value
                doc["processing"]["active"] = True
            elif kind == "failed":
                st["overall"] = MeetingState.FAILED.value
                doc["processing"]["recording"] = {**new_stage(StageStatus.FAILED), "attempt_count": 3,
                                                  "last_attempt_at": received + timedelta(minutes=8),
                                                  "started_at": received + timedelta(minutes=8),
                                                  "error_message": "Access to the recording was denied (403)"}
                tl += [timeline_event("recording_failed", "Recording processing failed — retrying", "warning", "system",
                                      details="Access to the recording was denied (403)", at=received + timedelta(minutes=1)),
                       timeline_event("recording_failed", "Recording processing failed", "error", "system",
                                      details="Access to the recording was denied (403)", at=received + timedelta(minutes=8))]
            else:
                t_rec, t_tr, t_an = received + timedelta(minutes=1), received + timedelta(minutes=3), received + timedelta(minutes=5)
                transcript = mock_data.mock_transcript(scenario, lead["name"], sales["name"], lead["interested_product"],
                                                       target_seconds=minutes * 60)
                result = TranscriptionResult.model_validate(transcript)
                segs = [s.model_dump() for s in result.segments]
                transcript_doc = {"source": "mock", "model": "mock-transcriber", "language": "en", "has_speaker_labels": True,
                                  "has_timestamps": True, "segments": segs, "text": transcript_to_text(segs, True, True),
                                  "is_mock": True, "mock_scenario": scenario, "created_at": t_tr}
                raw = mock_data.mock_analysis(scenario, lead["name"], sales["name"], lead["interested_product"])
                days = raw.pop("_follow_up_days", 1)
                analysis = validate_analysis(raw, DEFAULT_PITCH_CHECKLIST).model_dump()
                snapshot = build_snapshot(analysis)
                analysis_doc = {"lead_id": lead["_id"], "sales_person_id": sales["_id"], "result": analysis,
                                "model": "mock-gemini", "prompt_version": PROMPT_VERSION, "analysis_version": ANALYSIS_VERSION,
                                "checklist": DEFAULT_PITCH_CHECKLIST, "transcript_source": "mock", "trigger": "pipeline",
                                "is_current": True, "is_mock": True, "status": "completed", "created_at": t_an}
                follow = snapshot["follow_up_required"]
                st.update({"recording_available": True, "transcript_available": True, "analysis_completed": True,
                           "follow_up_required": follow,
                           "overall": (MeetingState.FOLLOW_UP_REQUIRED if follow else MeetingState.ANALYSIS_COMPLETED).value})
                for s, at in (("recording", t_rec), ("transcript", t_tr), ("analysis", t_an)):
                    doc["processing"][s] = {**new_stage(StageStatus.COMPLETED), "attempt_count": 1, "started_at": at - timedelta(seconds=40),
                                            "last_attempt_at": at - timedelta(seconds=40), "completed_at": at}
                doc["recording"] = {"status": "available", "download_status": "completed", "duration_seconds": minutes * 60,
                                    "size_bytes": None, "content_type": "video/mp4", "is_mock": True, "playable": False}
                doc["transcript"] = {"status": "available", "source": "mock", "segment_count": len(segs),
                                     "has_speaker_labels": True, "has_timestamps": True, "language": "en", "is_mock": True}
                doc["analysis"] = {"status": "completed", "current_analysis_id": None, "version_count": 1,
                                   "model": "mock-gemini", "prompt_version": PROMPT_VERSION, "analysis_version": ANALYSIS_VERSION,
                                   "completed_at": t_an, "snapshot": snapshot, "is_mock": True}
                tl += [timeline_event("recording_available", "Recording Available", "success", "classify", at=t_rec,
                                      details="Demo recording (mock mode)"),
                       timeline_event("transcript_ready", "Transcript Generated", "success", "mock", at=t_tr, ai=True),
                       timeline_event("analysis_completed", "AI Analysis Complete", "success", "gemini", at=t_an, ai=True,
                                      details=f"Model mock-gemini · prompt v{PROMPT_VERSION}")]
                journey += [journey_event("analysis_ready", "AI Analysis Ready", "ai", None, at=t_an),
                            journey_event("interest_detected", f"Interest Detected: {snapshot['interest_level'].title()}", "ai", None, at=t_an)]
                if snapshot.get("main_objection"):
                    journey.append(journey_event("objection", f"Objection: {snapshot['main_objection']}", "ai", None, at=t_an))
                if follow:
                    tl.append(timeline_event("follow_up_required", "Follow-up Required", "warning", "gemini", at=t_an + timedelta(seconds=30),
                                             ai=True, details=snapshot["recommended_next_action"]))
                    journey.append(journey_event("follow_up_suggested", "Follow-up Suggested", "ai", None,
                                                 snapshot["recommended_next_action"], at=t_an + timedelta(seconds=30)))
                doc["_follow_days"] = days
        if doc.get("webhook_received_at"):
            doc["attendance_sync"] = {"status": "completed", "attempt_count": 1, "last_attempt_at": doc["webhook_received_at"],
                                      "next_attempt_at": None, "last_message": "Details sent successfully",
                                      "last_status": "200 OK", "completed_at": doc["webhook_received_at"]}
        doc["timeline"] = sorted(tl, key=lambda e: e["at"])
        doc["updated_at"] = max(e["at"] for e in tl)
        follow_days = doc.pop("_follow_days", None)
        doc["flags"] = compute_flags(doc, {"result": analysis_doc["result"]} if analysis_doc else None)
        mid = (await db[Collections.MEETINGS].insert_one(doc)).inserted_id
        counts["meetings"] += 1

        rec = {"meeting_id": mid, "created_at": doc["created_at"]}
        if kind in ("completed", "processing"):
            rec.update({"source_urls": [f"mock://recordings/{doc['classify']['unique_id']}.mp4"], "is_mock": True,
                        "mock_scenario": scenario, "status": "completed" if kind == "completed" else "pending",
                        "local_path": None, "content_type": "video/mp4", "duration_seconds": minutes * 60})
            await db[Collections.MEETING_RECORDINGS].insert_one(rec)
        elif kind == "failed":
            rec.update({"source_urls": [f"https://classify-recordings.s3.ap-south-1.amazonaws.com/demo/{doc['classify']['unique_id']}.mp4"],
                        "status": "failed", "is_mock": True})
            await db[Collections.MEETING_RECORDINGS].insert_one(rec)

        if doc.get("webhook_received_at"):
            # Stored exactly as the SendAttendanceDetails response the sync would have received.
            att = doc["attendance"]
            payload = mock_attendance_response(
                doc, outcome="no_show" if kind == "no_show" else "completed",
                duration_minutes=minutes, end=att["actual_end"])
            if kind == "failed":
                payload["SessionDetailsToSend"]["AssetDetails"] = [{"type": "recording", "url": rec["source_urls"][0]}]
            payload["_demo"] = True
            await db[Collections.WEBHOOK_EVENTS].insert_one({
                "event_id": f"seed-{uuid.uuid4().hex}", "source": "classify_attendance_api",
                "classify_unique_id": doc["classify"]["unique_id"], "meeting_id": mid, "received_at": doc["webhook_received_at"],
                "headers": {}, "payload": payload, "processed": True, "processing_status": "processed", "attempt_count": 1,
                "processed_at": doc["webhook_received_at"], "error_message": None,
            })

        if transcript_doc:
            await db[Collections.MEETING_TRANSCRIPTS].insert_one({"meeting_id": mid, **transcript_doc})
        if analysis_doc:
            aid = (await db[Collections.MEETING_ANALYTICS].insert_one({"meeting_id": mid, **analysis_doc})).inserted_id
            await db[Collections.MEETINGS].update_one({"_id": mid}, {"$set": {"analysis.current_analysis_id": aid}})
            counts["analyses"] += 1
            fu = analysis_doc["result"]["follow_up"]
            if fu.get("required"):
                due = due_from_timing(doc["attendance"]["actual_end"], None, fu.get("suggested_timing", ""), follow_days)
                superseded = any(m[0] == lead_idx and m[1] > day and m[3] == "completed" for m in MEETINGS)
                await db[Collections.FOLLOW_UPS].insert_one({
                    "lead_id": lead["_id"], "meeting_id": mid, "owner_id": sales["_id"], "lead_name": lead["name"],
                    "meeting_label": label, "reason": fu["reason"], "recommended_action": fu["recommended_next_action"],
                    "suggested_timing": fu.get("suggested_timing"), "analysis_id": aid, "due_date": due,
                    "status": FollowUpStatus.COMPLETED.value if superseded else FollowUpStatus.PENDING.value,
                    "completed_at": due if superseded else None, "source": "ai", "ai_generated": True,
                    "notes": [{"text": "Sent the requested details; lead booked another call.", "at": due, "by": sales["_id"],
                               "by_name": sales["name"]}] if superseded else [],
                    "snoozed_until": None, "is_demo": True, "created_at": analysis_doc["created_at"], "updated_at": analysis_doc["created_at"],
                })
                counts["follow_ups"] += 1
        for event in journey:
            event["meeting_id"] = mid
            await lead_service.add_journey(lead["_id"], event, touch=False)

    for lead in leads:
        await lead_service.refresh_lead_intelligence(lead["_id"])
        latest = await db[Collections.MEETINGS].find_one({"lead_id": lead["_id"]}, sort=[("updated_at", -1)])
        status = "new"
        if latest:
            snap = (latest.get("analysis") or {}).get("snapshot") or {}
            if latest["status"].get("no_show"):
                status = "no_show"
            elif snap.get("follow_up_required"):
                status = "follow_up"
            elif latest["status"].get("meeting_completed"):
                status = "engaged"
            else:
                status = "meeting_scheduled"
            if snap.get("meeting_outcome") == "Ready to enroll" and lead["name"] == "Karthik Nair":
                status = "won"
        await db[Collections.LEADS].update_one({"_id": lead["_id"]},
                                               {"$set": {"lead_status": status, "last_activity_at": latest["updated_at"] if latest else lead["created_at"]}})

    await db[Collections.ACTIVITY_LOGS].insert_one({"user_id": admin["_id"], "user_name": admin["name"], "action": "seed.demo_data",
                                                    "resource": "system", "resource_id": None, "timestamp": utcnow(),
                                                    "metadata": {"demo": True, **counts}})
    logger.info("seed.completed", extra=counts)
    return counts


async def _main(reset: bool) -> None:
    from app.utils.logging_config import configure_logging

    configure_logging("INFO")
    db = await mongodb.connect()
    counts = await seed_demo_data(db, reset=reset)
    await mongodb.disconnect()
    if counts:
        print(f"Seeded demo data: {counts}")
        print("Logins: admin@classify.demo / Admin@123 · arjun@classify.demo / Sales@123 · neha@classify.demo / Sales@123")
    else:
        print("Database already has users; nothing seeded. Use --reset to wipe and reseed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Classify demo data")
    parser.add_argument("--reset", action="store_true", help="Delete existing data first")
    args = parser.parse_args()
    asyncio.run(_main(args.reset))

