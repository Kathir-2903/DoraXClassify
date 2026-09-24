"""Dashboard, analytics and call-quality computations.

Counts use MongoDB queries/aggregations; per-day series are bucketed from a
projected, date-bounded cursor. Nothing is extrapolated: when data is
insufficient a metric is returned with `available: false`."""
from collections import Counter, OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.constants.analysis_status import FollowUpStatus, StageStatus
from app.constants.meeting_status import MeetingState
from app.database.mongodb import Collections, get_db
from app.dependencies.auth import CurrentUser, scope_filter
from app.utils.datetime_utils import get_zone, parse_datetime, start_of_day_local, utcnow

S = MeetingState
SCHEDULED_STATES = [S.SCHEDULED, S.INVITATION_SENT, S.WAITING_FOR_LEAD, S.LEAD_JOINED, S.SALES_PERSON_JOINED, S.IN_PROGRESS]
COMPLETED_STATES = [S.MEETING_COMPLETED, S.ANALYSIS_COMPLETED, S.FOLLOW_UP_REQUIRED, S.CLOSED]
PROCESSING_STATES = [S.RECORDING_PROCESSING, S.TRANSCRIPT_PROCESSING, S.AI_ANALYSIS_PROCESSING]
MIN_INSIGHT_SAMPLE = 3

OBJECTION_LABELS = {"price": "Pricing", "time": "Time commitment", "approval": "Needs approval",
                    "competition": "Competition", "uncertainty": "Uncertainty", "relevance": "Relevance", "other": "Other"}


def _base(user: CurrentUser, params: Dict[str, Any]) -> Dict[str, Any]:
    query: Dict[str, Any] = {"status.overall": {"$ne": S.DRAFT.value}}
    query.update(scope_filter(user, requested=params.get("sales_person_id")))
    if params.get("lead_source"):
        query["lead_snapshot.lead_source"] = params["lead_source"]
    if params.get("product"):
        query["lead_snapshot.interested_product"] = params["product"]
    if params.get("status"):
        query["status.overall"] = {"$in": [s for s in str(params["status"]).split(",") if s]}
    return query


def _date_range(params: Dict[str, Any], default_days: int = 30):
    end = parse_datetime(params.get("date_to")) if params.get("date_to") else None
    start = parse_datetime(params.get("date_from")) if params.get("date_from") else None
    if end and len(str(params.get("date_to"))) <= 10:
        end = end + timedelta(days=1)
    if not start:
        start = start_of_day_local(int(params.get("days") or default_days) - 1)
    return start, end


def _pct(num: int, den: int) -> Optional[float]:
    return round(num * 100.0 / den, 1) if den else None


async def overview(user: CurrentUser, params: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    meetings = db[Collections.MEETINGS]
    q = _base(user, params)
    lead_q = scope_filter(user, requested=params.get("sales_person_id"))
    now = utcnow()
    today = start_of_day_local(0)

    completed_q = {**q, "status.meeting_completed": True, "status.no_show": {"$ne": True}}
    attendance_known = await meetings.count_documents({**q, "$or": [{"status.lead_joined": True}, {"status.no_show": True}]})
    joined = await meetings.count_documents({**q, "status.lead_joined": True})

    durations = await meetings.aggregate([
        {"$match": {**completed_q, "attendance.duration_seconds": {"$gt": 0}}},
        {"$group": {"_id": None, "avg": {"$avg": "$attendance.duration_seconds"}, "n": {"$sum": 1}}},
    ]).to_list(length=1)

    follow_q = {**scope_filter(user, "owner_id", params.get("sales_person_id")),
                "status": {"$in": [FollowUpStatus.PENDING.value, FollowUpStatus.SNOOZED.value]}}
    return {
        "total_leads": await db[Collections.LEADS].count_documents(lead_q),
        "meetings_scheduled": await meetings.count_documents(q),
        "meetings_upcoming": await meetings.count_documents({**q, "schedule.start_time": {"$gt": now},
                                                              "status.overall": {"$in": [s.value for s in SCHEDULED_STATES]}}),
        "meetings_completed": await meetings.count_documents(completed_q),
        "meetings_today": await meetings.count_documents({**q, "schedule.start_time": {"$gte": today, "$lt": today + timedelta(days=1)}}),
        "lead_join_rate": _pct(joined, attendance_known),
        "lead_join_sample": attendance_known,
        "average_meeting_duration_seconds": int(durations[0]["avg"]) if durations and durations[0].get("avg") else None,
        "follow_ups_required": await db[Collections.FOLLOW_UPS].count_documents(follow_q),
        "analysis_completed": await meetings.count_documents({**q, "status.analysis_completed": True}),
        "no_shows": await meetings.count_documents({**q, "status.no_show": True}),
        "recording_failures": await meetings.count_documents({**q, "processing.recording.status": StageStatus.FAILED.value}),
        "transcript_failures": await meetings.count_documents({**q, "processing.transcript.status": StageStatus.FAILED.value}),
        "ai_failures": await meetings.count_documents({**q, "processing.analysis.status": StageStatus.FAILED.value}),
        "processing_now": await meetings.count_documents({**q, "processing.active": True}),
        "generated_at": now,
    }


def _bucket_label(seconds: Optional[float]) -> Optional[str]:
    if not seconds:
        return None
    m = seconds / 60
    if m < 5:
        return "0-5 min"
    if m < 15:
        return "5-15 min"
    if m < 30:
        return "15-30 min"
    if m < 60:
        return "30-60 min"
    return "60+ min"


DURATION_BUCKETS = ["0-5 min", "5-15 min", "15-30 min", "30-60 min", "60+ min"]


def _status_group(meeting: Dict[str, Any]) -> str:
    st = meeting["status"]
    overall = st["overall"]
    if st.get("no_show") or overall == S.NO_SHOW.value:
        return "No Show"
    if overall == S.FAILED.value:
        return "Failed"
    if overall in {s.value for s in PROCESSING_STATES}:
        return "Processing"
    if st.get("meeting_completed") or overall in {s.value for s in COMPLETED_STATES}:
        return "Completed"
    return "Scheduled"


async def meeting_charts(user: CurrentUser, params: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    start, end = _date_range(params)
    q = _base(user, params)
    rng = {"$gte": start}
    if end:
        rng["$lt"] = end
    q["schedule.start_time"] = rng
    zone = get_zone()
    cursor = db[Collections.MEETINGS].find(q, {"schedule.start_time": 1, "status": 1, "attendance.duration_seconds": 1})

    last_day = (end - timedelta(seconds=1)).astimezone(zone).date() if end else datetime.now(zone).date()
    first_day = start.astimezone(zone).date()
    series: "OrderedDict[str, Dict[str, int]]" = OrderedDict()
    day = first_day
    while day <= last_day and len(series) < 400:
        series[day.isoformat()] = {"date": day.isoformat(), "scheduled": 0, "completed": 0, "no_show": 0}
        day += timedelta(days=1)

    status_counts: Counter = Counter()
    durations: Counter = Counter()
    async for m in cursor:
        key = m["schedule"]["start_time"].astimezone(zone).date().isoformat()
        group = _status_group(m)
        status_counts[group] += 1
        if key in series:
            series[key]["scheduled"] += 1
            if group == "No Show":
                series[key]["no_show"] += 1
            elif m["status"].get("meeting_completed"):
                series[key]["completed"] += 1
        bucket = _bucket_label((m.get("attendance") or {}).get("duration_seconds"))
        if bucket and m["status"].get("meeting_completed") and not m["status"].get("no_show"):
            durations[bucket] += 1

    return {
        "range": {"from": start, "to": end},
        "meetings_over_time": list(series.values()),
        "status_breakdown": [{"name": n, "value": status_counts.get(n, 0)} for n in ("Scheduled", "Completed", "No Show", "Processing", "Failed")],
        "duration_distribution": [{"bucket": b, "count": durations.get(b, 0)} for b in DURATION_BUCKETS],
    }


async def engagement_breakdown(user: CurrentUser, params: Dict[str, Any]) -> Dict[str, Any]:
    q = {**_base(user, params), "status.analysis_completed": True}
    counts: Counter = Counter()
    interest: Counter = Counter()
    intent: Counter = Counter()
    async for m in get_db()[Collections.MEETINGS].find(q, {"analysis.snapshot": 1}):
        snap = (m.get("analysis") or {}).get("snapshot") or {}
        counts[snap.get("engagement_level") or "unknown"] += 1
        interest[snap.get("interest_level") or "unknown"] += 1
        intent[snap.get("purchase_intent") or "unknown"] += 1
    levels = ["high", "medium", "low", "unknown"]
    return {
        "sample_size": sum(counts.values()),
        "ai_generated": True,
        "engagement": [{"level": l.title(), "count": counts.get(l, 0)} for l in levels],
        "interest": [{"level": l.title(), "count": interest.get(l, 0)} for l in levels],
        "intent": [{"level": l.title(), "count": intent.get(l, 0)} for l in levels],
    }


async def follow_up_pipeline(user: CurrentUser, params: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    owner_q = scope_filter(user, "owner_id", params.get("sales_person_id"))
    analysed_no_follow = await db[Collections.MEETINGS].count_documents(
        {**_base(user, params), "status.analysis_completed": True, "status.follow_up_required": False})
    open_count = await db[Collections.FOLLOW_UPS].count_documents(
        {**owner_q, "status": {"$in": [FollowUpStatus.PENDING.value, FollowUpStatus.SNOOZED.value]}})
    done = await db[Collections.FOLLOW_UPS].count_documents({**owner_q, "status": FollowUpStatus.COMPLETED.value})
    overdue = await db[Collections.FOLLOW_UPS].count_documents(
        {**owner_q, "status": {"$ne": FollowUpStatus.COMPLETED.value}, "due_date": {"$lt": utcnow()}})
    return {
        "pipeline": [
            {"stage": "No Follow-up", "count": analysed_no_follow},
            {"stage": "Follow-up Required", "count": open_count},
            {"stage": "Follow-up Completed", "count": done},
        ],
        "overdue": overdue,
    }


def _top(counter: Counter, label_map: Optional[Dict[str, str]] = None, min_count: int = 2) -> Dict[str, Any]:
    if not counter:
        return {"available": False, "reason": "Not enough data yet"}
    value, count = counter.most_common(1)[0]
    if count < min_count:
        return {"available": False, "reason": "No recurring pattern yet"}
    return {"available": True, "value": (label_map or {}).get(value, value), "count": count}


async def ai_insights(user: CurrentUser, params: Dict[str, Any]) -> Dict[str, Any]:
    q = {**_base(user, params), "status.analysis_completed": True}
    objections: Counter = Counter()
    topics: Counter = Counter()
    questions: Counter = Counter()
    products: Counter = Counter()
    follow_drivers: Counter = Counter()
    sample = 0
    async for m in get_db()[Collections.MEETINGS].find(q, {"analysis.snapshot": 1, "lead_snapshot.interested_product": 1}):
        snap = (m.get("analysis") or {}).get("snapshot") or {}
        sample += 1
        objections.update(set(snap.get("objection_categories") or []))
        topics.update({t.strip().title() for t in snap.get("topics") or [] if t})
        if snap.get("top_question"):
            questions[_norm_question(snap["top_question"])] += 1
        if (m.get("lead_snapshot") or {}).get("interested_product"):
            products[m["lead_snapshot"]["interested_product"]] += 1
        if snap.get("follow_up_required") and snap.get("objection_categories"):
            follow_drivers.update(set(snap["objection_categories"]))
    if sample < MIN_INSIGHT_SAMPLE:
        na = {"available": False, "reason": f"Needs at least {MIN_INSIGHT_SAMPLE} analysed meetings"}
        return {"sample_size": sample, "ai_generated": True, "top_objection": na, "top_topic": na,
                "top_question": na, "top_product": na, "top_follow_up_reason": na}
    return {
        "sample_size": sample,
        "ai_generated": True,
        "top_objection": _top(objections, OBJECTION_LABELS),
        "top_topic": _top(topics),
        "top_question": _top(questions),
        "top_product": _top(products),
        "top_follow_up_reason": _top(follow_drivers, {k: f"{v} concerns" for k, v in OBJECTION_LABELS.items()}),
    }


def _norm_question(q: str) -> str:
    q = " ".join(q.strip().rstrip("?").lower().split())
    return q[:1].upper() + q[1:] + "?"


def compute_call_quality(meeting: Dict[str, Any], transcript: Optional[Dict[str, Any]],
                         analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Non-authoritative call metrics. Talk-time style metrics are only
    computed when the transcript has both speaker labels and timestamps."""
    def metric(value, available=True, source=None, ai=False, note=None):
        return {"value": value if available else None, "available": available, "source": source,
                "ai_generated": ai, "note": note}

    attendance = meeting.get("attendance") or {}
    out: Dict[str, Any] = {}
    duration = attendance.get("duration_seconds")
    out["total_duration_seconds"] = metric(duration, duration is not None, "classify",
                                           note=None if duration is not None else "Not available from meeting data")

    segs = (transcript or {}).get("segments") or []
    timed = bool(transcript and transcript.get("has_timestamps") and transcript.get("has_speaker_labels") and segs)
    src_note = "Estimated from AI-generated transcript timestamps" if (transcript or {}).get("source") in ("gemini", "mock", "whisper") else "From transcript timestamps"
    if timed:
        lead_t = sum(max(0.0, (s["end_seconds"] or 0) - (s["start_seconds"] or 0)) for s in segs if s["speaker"] == "lead")
        sales_t = sum(max(0.0, (s["end_seconds"] or 0) - (s["start_seconds"] or 0)) for s in segs if s["speaker"] == "sales")
        ordered = sorted(segs, key=lambda s: s["start_seconds"] or 0)
        interruptions = sum(1 for a, b in zip(ordered, ordered[1:])
                            if b["speaker"] != a["speaker"] and (b["start_seconds"] or 0) < (a["end_seconds"] or 0) - 0.3)
        gaps = sum(max(0.0, (b["start_seconds"] or 0) - (a["end_seconds"] or 0)) for a, b in zip(ordered, ordered[1:])
                   if (b["start_seconds"] or 0) - (a["end_seconds"] or 0) > 3)
        total_talk = lead_t + sales_t
        out["lead_talk_seconds"] = metric(round(lead_t), True, "transcript", note=src_note)
        out["sales_talk_seconds"] = metric(round(sales_t), True, "transcript", note=src_note)
        out["talk_ratio"] = metric({"lead_pct": _pct(round(lead_t), round(total_talk)), "sales_pct": _pct(round(sales_t), round(total_talk))},
                                   total_talk > 0, "transcript", note=src_note)
        out["interruptions"] = metric(interruptions, True, "transcript", note=src_note)
        out["silence_seconds"] = metric(round(gaps), True, "transcript", note=f"{src_note} (gaps > 3s)")
    else:
        na = "Speaker talk-time data unavailable" if transcript else "Transcript unavailable"
        for key in ("lead_talk_seconds", "sales_talk_seconds", "talk_ratio", "interruptions", "silence_seconds"):
            out[key] = metric(None, False, None, note=na)

    result = (analysis or {}).get("result")
    if result:
        coverage = result.get("pitch_coverage") or []
        out["questions"] = metric(len(result.get("lead_questions") or []), True, "ai", ai=True)
        out["objections"] = metric(len(result.get("lead_objections") or []), True, "ai", ai=True)
        out["topics_discussed"] = metric(len(result.get("topics_discussed") or []), True, "ai", ai=True)
        out["pitch_coverage"] = metric({"covered": sum(1 for c in coverage if c.get("covered")), "total": len(coverage)},
                                       bool(coverage), "ai", ai=True)
        out["follow_up_required"] = metric(bool((result.get("follow_up") or {}).get("required")), True, "ai", ai=True)
    else:
        for key in ("questions", "objections", "topics_discussed", "pitch_coverage", "follow_up_required"):
            out[key] = metric(None, False, None, note="AI analysis unavailable")
    return out
