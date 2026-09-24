"""Server-side CSV exports and the PDF meeting report."""
import csv
import io
import re
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from app.utils.datetime_utils import format_local, humanize_duration


_PHONE = re.compile(r"^\+\d{7,15}$")


def _cell(value: Any) -> str:
    """Neutralise spreadsheet formula injection (E.164 phone numbers are safe)."""
    text = "" if value is None else str(value)
    if _PHONE.match(text):
        return text
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


async def csv_stream(header: List[str], rows: AsyncIterator[List[Any]]) -> AsyncIterator[str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    yield buf.getvalue()
    async for row in rows:
        buf.seek(0)
        buf.truncate(0)
        writer.writerow([_cell(v) for v in row])
        yield buf.getvalue()


def lead_row(lead: Dict[str, Any]) -> List[Any]:
    intel = lead.get("intelligence") or {}
    return [
        lead.get("name"), lead.get("email"), lead.get("phone"), lead.get("company"),
        (lead.get("sales_person") or {}).get("name"), lead.get("lead_source"), lead.get("interested_product"),
        lead.get("lead_status"), intel.get("meetings_count"), format_local(intel.get("last_meeting_at")),
        lead.get("last_meeting_status_label") or "", humanize_duration(intel.get("last_duration_seconds")) if intel.get("last_duration_seconds") else "",
        intel.get("interest_level") or "", intel.get("purchase_intent") or "",
        "Yes" if intel.get("follow_up_required") else "No", format_local(lead.get("created_at")),
        "Yes" if lead.get("is_demo") else "No",
    ]


LEAD_HEADER = ["Name", "Email", "Phone", "Company", "Assigned Sales Person", "Lead Source", "Interested Product",
               "Lead Status", "Meetings", "Last Meeting", "Last Meeting Status", "Last Duration",
               "Interest (AI)", "Intent (AI)", "Follow-up", "Created", "Demo Data"]

MEETING_HEADER = ["Meeting ID", "Label", "Lead", "Lead Email", "Sales Person", "Scheduled Start", "Timezone",
                  "Scheduled Minutes", "Status", "Lead Joined", "Actual Duration", "Email",
                  "Recording", "Transcript", "Analysis", "Interest (AI)", "Intent (AI)", "Main Objection (AI)",
                  "Follow-up (AI)", "Classify Unique ID", "Demo Data"]


def meeting_row(m: Dict[str, Any]) -> List[Any]:
    snap = (m.get("analysis") or {}).get("snapshot") or {}
    proc = m.get("processing") or {}
    return [
        str(m["_id"]), m.get("label"), m["lead_snapshot"].get("name"), m["lead_snapshot"].get("email"),
        m["sales_person_snapshot"].get("name"), format_local(m["schedule"]["start_time"]), m["schedule"].get("timezone"),
        m["schedule"].get("duration_minutes"), m.get("status_label") or m["status"]["overall"],
        "No" if m["status"].get("no_show") else ("Yes" if m["status"].get("lead_joined") else "Unknown"),
        humanize_duration((m.get("attendance") or {}).get("duration_seconds")) if (m.get("attendance") or {}).get("duration_seconds") else "",
        (m.get("notifications") or {}).get("email", {}).get("status"),
        proc.get("recording", {}).get("status"), proc.get("transcript", {}).get("status"), proc.get("analysis", {}).get("status"),
        snap.get("interest_level") or "", snap.get("purchase_intent") or "", snap.get("main_objection") or "",
        "" if not snap else ("Yes" if snap.get("follow_up_required") else "No"),
        (m.get("classify") or {}).get("unique_id") or "", "Yes" if m.get("is_demo") else "No",
    ]


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
ORANGE = colors.HexColor("#EA580C")
INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18, textColor=INK, alignment=TA_LEFT, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=9, textColor=MUTED, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12, textColor=INK, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=13.5, textColor=INK),
        "small": ParagraphStyle("sm", parent=base["Normal"], fontSize=8, leading=11, textColor=MUTED),
        "ai": ParagraphStyle("ai", parent=base["Normal"], fontSize=7.5, textColor=ORANGE, fontName="Helvetica-Bold"),
    }


def _p(text: Any, style) -> Paragraph:
    return Paragraph(escape(str(text if text not in (None, "") else "—")), style)


def _kv_table(rows: Iterable, st) -> Table:
    data = [[_p(k, st["small"]), _p(v, st["body"])] for k, v in rows]
    t = Table(data, colWidths=[45 * mm, 125 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _bullets(items: Iterable[str], st) -> List[Any]:
    items = [i for i in items if i]
    if not items:
        return [_p("None identified", st["small"])]
    return [Paragraph("• " + escape(str(i)), st["body"]) for i in items]


def build_meeting_pdf(meeting: Dict[str, Any], lead: Optional[Dict[str, Any]], analysis: Optional[Dict[str, Any]],
                      transcript: Optional[Dict[str, Any]]) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Meeting Report - {meeting.get('label')}", author="Dora X Classify")
    tz = meeting["schedule"].get("timezone")
    att = meeting.get("attendance") or {}
    story: List[Any] = [
        Paragraph("Dora X Classify · Meeting Report", st["title"]),
        _p(f"{meeting.get('label')} · generated report{' · DEMO DATA' if meeting.get('is_demo') else ''}", st["sub"]),
        Paragraph("Lead Information", st["h2"]),
        _kv_table([("Name", (lead or meeting["lead_snapshot"]).get("name")), ("Email", (lead or meeting["lead_snapshot"]).get("email")),
                   ("Phone", (lead or meeting["lead_snapshot"]).get("phone")), ("Company", (lead or {}).get("company")),
                   ("Interested product", (lead or {}).get("interested_product"))], st),
        Paragraph("Meeting Information", st["h2"]),
        _kv_table([("Sales person", meeting["sales_person_snapshot"].get("name")),
                   ("Scheduled", format_local(meeting["schedule"]["start_time"], tz_name=tz) + f" ({tz})"),
                   ("Actual start", format_local(att.get("actual_start"), tz_name=tz) or "Not available from meeting data"),
                   ("Actual end", format_local(att.get("actual_end"), tz_name=tz) or "Not available from meeting data"),
                   ("Duration", humanize_duration(att.get("duration_seconds")) if att.get("duration_seconds") else "Not available from meeting data"),
                   ("Lead joined", "No" if meeting["status"].get("no_show") else ("Yes" if meeting["status"].get("lead_joined") else "Not reported")),
                   ("Status", meeting.get("status_label") or meeting["status"]["overall"])], st),
    ]

    result = (analysis or {}).get("result")
    if result:
        story += [
            Spacer(1, 4),
            Paragraph(f"AI ANALYSIS — generated by {escape(str(analysis.get('model')))} (prompt v{escape(str(analysis.get('prompt_version')))}). "
                      "AI output is interpretation, not verified fact.", st["ai"]),
            Paragraph("Summary", st["h2"]), _p(result.get("summary"), st["body"]),
            Paragraph("Lead Intelligence", st["h2"]),
            _kv_table([("Interest", (result.get("interest_level") or "").title()), ("Purchase intent", (result.get("purchase_intent") or "").title()),
                       ("Engagement", ((result.get("engagement") or {}).get("level") or "").title()),
                       ("Sentiment", (result.get("lead_sentiment") or "").title()), ("Outcome", result.get("meeting_outcome"))], st),
            Paragraph("Topics", st["h2"]), *_bullets(result.get("topics_discussed") or [], st),
            Paragraph("Questions", st["h2"]), *_bullets([q.get("question") for q in result.get("lead_questions") or []], st),
            Paragraph("Objections", st["h2"]),
            *_bullets([f"{o.get('objection')} — {o.get('evidence')}" for o in result.get("lead_objections") or []], st),
        ]
        coverage = result.get("pitch_coverage") or []
        if coverage:
            data = [[_p("Topic", st["small"]), _p("Covered", st["small"]), _p("Confidence", st["small"])]] + [
                [_p(c["topic"], st["body"]), _p("Yes" if c.get("covered") else "No", st["body"]), _p(f"{int((c.get('confidence') or 0) * 100)}%", st["body"])]
                for c in coverage]
            t = Table(data, colWidths=[90 * mm, 35 * mm, 45 * mm])
            t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC"))]))
            story += [Paragraph(f"Pitch Coverage ({sum(1 for c in coverage if c.get('covered'))} / {len(coverage)})", st["h2"]), t]
        follow = result.get("follow_up") or {}
        story += [
            Paragraph("Follow-up (AI Recommendation)", st["h2"]),
            _kv_table([("Required", "Yes" if follow.get("required") else "No"), ("Reason", follow.get("reason")),
                       ("Recommended action", follow.get("recommended_next_action")), ("Timing", follow.get("suggested_timing"))], st),
            Paragraph("Action Items", st["h2"]),
            *_bullets([f"[{a.get('owner')}] {a.get('item')}" + (f" ({a.get('due_hint')})" if a.get("due_hint") else "")
                       for a in result.get("action_items") or []], st),
        ]
    else:
        story += [Paragraph("AI Analysis", st["h2"]), _p("AI analysis unavailable", st["small"])]

    story.append(Paragraph("Transcript", st["h2"]))
    segments = (transcript or {}).get("segments") or []
    if not segments:
        story.append(_p("Transcript unavailable", st["small"]))
    else:
        if transcript.get("source") in ("gemini", "mock", "whisper"):
            story.append(Paragraph("Transcript generated by AI; speaker labels and timings are estimates.", st["ai"]))
        for s in segments:
            prefix = ""
            if transcript.get("has_timestamps") and s.get("start_seconds") is not None:
                sec = int(s["start_seconds"])
                prefix += f"{sec // 60:02d}:{sec % 60:02d}  "
            if transcript.get("has_speaker_labels"):
                prefix += f"{(s.get('speaker') or 'unknown').upper()}: "
            story.append(KeepTogether(Paragraph(f"<b>{escape(prefix)}</b>{escape(s['text'])}", st["body"])))
    doc.build(story)
    return buf.getvalue()


def transcript_text_file(meeting: Dict[str, Any], transcript: Dict[str, Any]) -> str:
    lines = [f"Transcript — {meeting.get('label')}",
             f"Lead: {meeting['lead_snapshot'].get('name')} · Sales: {meeting['sales_person_snapshot'].get('name')}",
             f"Source: {transcript.get('source')}{' (AI-generated; speaker labels/timings are estimates)' if transcript.get('source') in ('gemini', 'mock', 'whisper') else ''}",
             ""]
    lines.append(transcript.get("text") or "")
    return "\n".join(lines)
