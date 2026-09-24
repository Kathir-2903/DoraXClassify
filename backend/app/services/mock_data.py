"""Deterministic, realistic sales-call scenarios for mock mode and demo seed data.

Everything produced here is flagged `is_mock=True` wherever it is stored so the
UI can label it as demo content."""
import hashlib
from typing import Any, Dict, List, Tuple

from app.constants.analysis_status import DEFAULT_PITCH_CHECKLIST

Line = Tuple[str, str]  # (speaker, text)

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "pricing_concern": {
        "lines": [
            ("sales", "Hi {lead}, this is {sales} from the admissions team. Thanks for making time today. Can you hear me clearly?"),
            ("lead", "Yes, loud and clear. Thanks for setting this up."),
            ("sales", "Great. To start, could you tell me a little about your current role and what made you look at {product}?"),
            ("lead", "I work in customer support at a fintech company. I've been learning JavaScript on my own for a few months but I want a structured path into a developer role."),
            ("sales", "That's a very common journey. What's been the hardest part about learning on your own?"),
            ("lead", "Honestly, consistency, and knowing what to learn next. I start tutorials and don't finish projects."),
            ("sales", "Understood. The program is built exactly for that. It's a live, mentor-led curriculum covering HTML, CSS, JavaScript, React, Node, and MongoDB, with a capstone project reviewed by industry mentors."),
            ("lead", "What is the total duration of the program?"),
            ("sales", "It's six months if you follow the weekday evening track, with about ten to twelve hours a week including live classes and practice."),
            ("lead", "Okay. Is placement support included, or is that extra?"),
            ("sales", "Placement support is included. You get mock interviews, resume reviews, and access to our hiring partner network once you clear the capstone."),
            ("lead", "That's good. And what does the program cost?"),
            ("sales", "The full program fee is ninety thousand rupees. There's a scholarship test this month that can reduce it by up to fifteen percent."),
            ("lead", "Ninety thousand is a lot for me right now. Can I pay in installments?"),
            ("sales", "Yes, we have no-cost EMI options for six and nine months through our finance partners. I can send you the exact monthly breakdown."),
            ("lead", "Please do. I'd also like the brochure with the detailed syllabus."),
            ("sales", "Absolutely. Is there anything else holding you back?"),
            ("lead", "Mostly the price. If the EMI works out I think I'm quite serious. What is the enrollment process like?"),
            ("sales", "You take the scholarship test, we confirm the fee, and then you complete the enrollment form. The next batch starts on the fifteenth."),
            ("lead", "Okay, send me the EMI details and brochure and I'll review them this week."),
            ("sales", "Will do. I'll send them within the next hour and call you on Thursday to answer any questions."),
            ("lead", "Sounds good. Thank you."),
        ],
        "analysis": {
            "summary": "{sales} introduced {product}, explored the lead's self-learning challenges, and explained curriculum, duration, placement support and pricing. {lead} expressed clear interest and asked about the enrollment process, but raised a concern about the total fee and requested EMI details and the brochure before deciding.",
            "conversation_language": "English",
            "lead_intent": "Transition from customer support into a developer role through a structured program.",
            "interest_level": "high",
            "purchase_intent": "medium",
            "lead_sentiment": "positive",
            "sales_sentiment": "positive",
            "engagement": {"level": "high", "rationale": "The lead asked several specific questions and requested follow-up material.",
                           "signals": [
                               {"signal": "Asked multiple questions", "evidence": "Asked about duration, placement, pricing, installments and enrollment."},
                               {"signal": "Requested pricing", "evidence": "\"And what does the program cost?\""},
                               {"signal": "Asked about enrollment", "evidence": "\"What is the enrollment process like?\""},
                               {"signal": "Requested follow-up", "evidence": "\"Send me the EMI details and brochure\""}]},
            "topics_discussed": ["Career background", "Curriculum", "Duration", "Placement", "Pricing", "Installments", "Enrollment"],
            "lead_questions": [
                {"question": "What is the total duration of the program?", "answered": True, "evidence": "Six months, 10–12 hours a week."},
                {"question": "Is placement support included?", "answered": True, "evidence": "Included: mock interviews, resume reviews, hiring partners."},
                {"question": "What does the program cost?", "answered": True, "evidence": "₹90,000 with up to 15% scholarship."},
                {"question": "Can I pay in installments?", "answered": True, "evidence": "No-cost EMI for 6 and 9 months."},
                {"question": "What is the enrollment process like?", "answered": True, "evidence": "Scholarship test → fee confirmation → enrollment form."}],
            "lead_objections": [
                {"objection": "Total program fee feels high", "category": "price", "evidence": "\"Ninety thousand is a lot for me right now.\"",
                 "handled": True, "handling_notes": "Offered no-cost EMI and the scholarship test."}],
            "lead_requirements": ["Structured learning path", "Placement support", "Installment payment option"],
            "pain_points": ["Inconsistent self-study", "Not finishing projects", "Unclear what to learn next"],
            "interests": ["{product}", "Placement support", "EMI options"],
            "competitor_mentions": [],
            "pricing_discussion": {"discussed": True, "details": "₹90,000 program fee; up to 15% scholarship; no-cost EMI for 6/9 months."},
            "product_discussion": ["Live mentor-led classes", "Capstone project", "Placement support"],
            "sales_pitch": {"pitch_detected": True, "topics_covered": ["Introduction", "Need Discovery", "Product Explanation", "Course Details", "Pricing", "Placement", "Objection Handling", "Next Steps"],
                            "missing_topics": ["Differentiators", "Benefits"]},
            "coverage": {"Introduction": True, "Problem Identification": True, "Need Discovery": True, "Product Explanation": True,
                         "Benefits": False, "Course Details": True, "Pricing": True, "Placement": True, "Differentiators": False,
                         "Objection Handling": True, "Next Steps": True, "Call-to-Action": True},
            "objection_handling": "Price concern was acknowledged and addressed with EMI and scholarship options.",
            "follow_up": {"required": True, "reason": "Lead asked about installment options and expressed concern about total course cost.",
                          "recommended_next_action": "Send detailed pricing breakdown with EMI plans and the brochure.",
                          "suggested_timing": "Within 24 hours", "days": 1},
            "action_items": [
                {"owner": "sales", "item": "Send EMI breakdown for 6 and 9 month plans", "due_hint": "Within the hour"},
                {"owner": "sales", "item": "Share brochure with detailed syllabus", "due_hint": "Within the hour"},
                {"owner": "sales", "item": "Call back on Thursday", "due_hint": "Thursday"},
                {"owner": "lead", "item": "Review EMI details and brochure", "due_hint": "This week"}],
            "risk_signals": [{"signal": "Price concern", "evidence": "\"Ninety thousand is a lot for me right now.\""},
                             {"signal": "No immediate decision", "evidence": "\"I'll review them this week.\""}],
            "positive_signals": [{"signal": "Asked enrollment process", "evidence": "\"What is the enrollment process like?\""},
                                 {"signal": "Requested brochure", "evidence": "\"I'd also like the brochure\""},
                                 {"signal": "Stated seriousness", "evidence": "\"If the EMI works out I think I'm quite serious.\""}],
            "explicit_statements": [
                {"speaker": "lead", "quote": "Ninety thousand is a lot for me right now.", "topic": "Pricing"},
                {"speaker": "lead", "quote": "If the EMI works out I think I'm quite serious.", "topic": "Intent"},
                {"speaker": "lead", "quote": "I start tutorials and don't finish projects.", "topic": "Pain point"}],
            "ai_interpretations": [
                {"interpretation": "Affordability, not product fit, is the main barrier to enrolling.", "basis": "Positive questions on curriculum and placement; hesitation only at price.", "confidence": 0.8},
                {"interpretation": "The lead is likely to convert if a manageable monthly EMI is confirmed.", "basis": "Conditional commitment tied to EMI.", "confidence": 0.65}],
            "meeting_outcome": "Interested — awaiting EMI details before deciding",
            "confidence": 0.86,
        },
    },
    "parent_approval": {
        "lines": [
            ("sales", "Hello {lead}, I'm {sales}. Thanks for joining. How are you today?"),
            ("lead", "I'm good, thanks. I just finished my exams last week."),
            ("sales", "Congratulations! You're in your final year, right? What are you hoping to do after graduation?"),
            ("lead", "Yes, final year B.Sc. I'm really interested in data science but my college doesn't teach much of it."),
            ("sales", "That's exactly the gap {product} fills. We start from Python and statistics and go up to machine learning with real datasets."),
            ("lead", "Do I need a strong maths background?"),
            ("sales", "Basic school-level maths is enough. We cover the statistics you need in the first month."),
            ("lead", "Okay, that's reassuring. Will I get a certificate?"),
            ("sales", "Yes, an industry-recognised certificate, plus a portfolio of four projects you can show recruiters."),
            ("lead", "How much does it cost?"),
            ("sales", "The program is seventy-five thousand rupees, and students get an additional ten percent discount."),
            ("lead", "I'll have to talk to my parents about it. They're paying for it."),
            ("sales", "Of course. Would it help if I spoke with them directly and answered their questions?"),
            ("lead", "Yes, that would help. My father will want to know about placements."),
            ("sales", "Our last cohort had strong placement outcomes. I'll share the placement report so he can see it."),
            ("lead", "Another institute offered me a cheaper course, so they'll probably compare."),
            ("sales", "That's fair. The main difference is live mentorship and the capstone review, which self-paced courses don't have."),
            ("lead", "Okay. Can we do a call with my father this weekend?"),
            ("sales", "Absolutely. I'll send a calendar invite for Saturday and share the placement report today."),
        ],
        "analysis": {
            "summary": "{sales} discussed {product} with {lead}, a final-year student interested in data science. The lead asked about prerequisites, certification and cost. Payment depends on the lead's parents, and a competing cheaper course was mentioned. A follow-up call with the lead's father was agreed.",
            "conversation_language": "English",
            "lead_intent": "Build data science skills before graduating to improve job prospects.",
            "interest_level": "medium",
            "purchase_intent": "medium",
            "lead_sentiment": "positive",
            "sales_sentiment": "positive",
            "engagement": {"level": "medium", "rationale": "Asked relevant questions but the decision depends on parents.",
                           "signals": [
                               {"signal": "Asked multiple questions", "evidence": "Asked about maths prerequisites, certificate and cost."},
                               {"signal": "Requested follow-up", "evidence": "\"Can we do a call with my father this weekend?\""},
                               {"signal": "Raised objections", "evidence": "Parent approval and cheaper competitor."}]},
            "topics_discussed": ["Career goals", "Curriculum", "Prerequisites", "Certification", "Pricing", "Placement", "Competition"],
            "lead_questions": [
                {"question": "Do I need a strong maths background?", "answered": True, "evidence": "School-level maths is enough."},
                {"question": "Will I get a certificate?", "answered": True, "evidence": "Industry-recognised certificate plus portfolio."},
                {"question": "How much does it cost?", "answered": True, "evidence": "₹75,000 with a 10% student discount."}],
            "lead_objections": [
                {"objection": "Needs parents' approval to pay", "category": "approval", "evidence": "\"I'll have to talk to my parents about it.\"",
                 "handled": True, "handling_notes": "Offered to speak with the parents directly."},
                {"objection": "Cheaper alternative offered elsewhere", "category": "competition", "evidence": "\"Another institute offered me a cheaper course\"",
                 "handled": True, "handling_notes": "Explained live mentorship and capstone review differences."}],
            "lead_requirements": ["Beginner-friendly start", "Certificate", "Placement evidence for parents"],
            "pain_points": ["College curriculum lacks data science"],
            "interests": ["{product}", "Machine learning", "Portfolio projects"],
            "competitor_mentions": ["Unnamed cheaper institute"],
            "pricing_discussion": {"discussed": True, "details": "₹75,000 with 10% student discount."},
            "product_discussion": ["Python and statistics foundation", "Machine learning with real datasets", "Four portfolio projects"],
            "sales_pitch": {"pitch_detected": True, "topics_covered": ["Introduction", "Need Discovery", "Product Explanation", "Course Details", "Pricing", "Differentiators", "Next Steps"],
                            "missing_topics": ["Benefits", "Call-to-Action"]},
            "coverage": {"Introduction": True, "Problem Identification": True, "Need Discovery": True, "Product Explanation": True,
                         "Benefits": False, "Course Details": True, "Pricing": True, "Placement": True, "Differentiators": True,
                         "Objection Handling": True, "Next Steps": True, "Call-to-Action": False},
            "objection_handling": "Approval objection handled by proposing a parent call; competitor objection addressed via differentiators.",
            "follow_up": {"required": True, "reason": "Decision depends on the lead's father, who wants placement information.",
                          "recommended_next_action": "Share the placement report and hold a call with the lead's father on Saturday.",
                          "suggested_timing": "This weekend", "days": 3},
            "action_items": [
                {"owner": "sales", "item": "Send placement report", "due_hint": "Today"},
                {"owner": "sales", "item": "Send calendar invite for Saturday parent call", "due_hint": "Today"},
                {"owner": "lead", "item": "Discuss program with parents", "due_hint": "Before Saturday"}],
            "risk_signals": [{"signal": "Needs approval", "evidence": "\"They're paying for it.\""},
                             {"signal": "Competitor comparison", "evidence": "\"they'll probably compare.\""}],
            "positive_signals": [{"signal": "Proposed a follow-up call", "evidence": "\"Can we do a call with my father this weekend?\""},
                                 {"signal": "Clear career motivation", "evidence": "\"I'm really interested in data science\""}],
            "explicit_statements": [
                {"speaker": "lead", "quote": "I'll have to talk to my parents about it. They're paying for it.", "topic": "Decision"},
                {"speaker": "lead", "quote": "Another institute offered me a cheaper course, so they'll probably compare.", "topic": "Competition"}],
            "ai_interpretations": [
                {"interpretation": "Decision authority may not be with the lead.", "basis": "Parents are funding the course.", "confidence": 0.85},
                {"interpretation": "Placement evidence is likely to be the deciding factor for the parents.", "basis": "Father's stated focus on placements.", "confidence": 0.6}],
            "meeting_outcome": "Decision pending — parent call scheduled",
            "confidence": 0.82,
        },
    },
    "time_concern": {
        "lines": [
            ("sales", "Hi {lead}, {sales} here. Thanks for joining the call."),
            ("lead", "Hi. I only have about fifteen minutes, sorry."),
            ("sales", "No problem, I'll keep it focused. You'd filled a form about {product}. What prompted that?"),
            ("lead", "I was just exploring. My manager mentioned upskilling in the appraisal."),
            ("sales", "Got it. The program covers the fundamentals through to job-ready projects, with live evening classes."),
            ("lead", "How many hours a week does it need?"),
            ("sales", "About ten hours, including two live sessions on weekday evenings."),
            ("lead", "That's difficult. I often work late and travel for work."),
            ("sales", "We also have a weekend batch and recordings of every class."),
            ("lead", "Maybe. I'm not sure I can commit right now."),
            ("sales", "Would it help if I sent you the weekend batch schedule to look at?"),
            ("lead", "Sure, you can send it. I'll look when things calm down at work."),
        ],
        "analysis": {
            "summary": "A short call where {lead} said they were exploring options after an appraisal conversation. The lead raised concerns about weekly time commitment due to late work and travel, and was non-committal. {sales} offered the weekend batch and class recordings.",
            "conversation_language": "English",
            "lead_intent": "Exploring upskilling options suggested by their manager; no firm goal stated.",
            "interest_level": "low",
            "purchase_intent": "low",
            "lead_sentiment": "neutral",
            "sales_sentiment": "positive",
            "engagement": {"level": "low", "rationale": "Short call; a single logistics question; non-committal responses.",
                           "signals": [{"signal": "Raised objections", "evidence": "\"That's difficult. I often work late and travel for work.\""}]},
            "topics_discussed": ["Motivation", "Time commitment", "Weekend batch"],
            "lead_questions": [{"question": "How many hours a week does it need?", "answered": True, "evidence": "About ten hours including two live sessions."}],
            "lead_objections": [
                {"objection": "Cannot commit weekday evenings", "category": "time", "evidence": "\"I often work late and travel for work.\"",
                 "handled": True, "handling_notes": "Offered weekend batch and recordings."},
                {"objection": "Unsure about committing now", "category": "uncertainty", "evidence": "\"I'm not sure I can commit right now.\"",
                 "handled": False, "handling_notes": ""}],
            "lead_requirements": ["Flexible schedule"],
            "pain_points": ["Irregular work hours", "Work travel"],
            "interests": ["Weekend batch"],
            "competitor_mentions": [],
            "pricing_discussion": {"discussed": False, "details": ""},
            "product_discussion": ["Live evening classes", "Weekend batch", "Class recordings"],
            "sales_pitch": {"pitch_detected": True, "topics_covered": ["Introduction", "Need Discovery", "Product Explanation"],
                            "missing_topics": ["Pricing", "Placement", "Benefits", "Differentiators", "Call-to-Action"]},
            "coverage": {"Introduction": True, "Problem Identification": False, "Need Discovery": True, "Product Explanation": True,
                         "Benefits": False, "Course Details": True, "Pricing": False, "Placement": False, "Differentiators": False,
                         "Objection Handling": True, "Next Steps": True, "Call-to-Action": False},
            "objection_handling": "Time objection partially addressed; uncertainty was not explored.",
            "follow_up": {"required": True, "reason": "Lead is time-constrained and non-committal but accepted the weekend schedule.",
                          "recommended_next_action": "Send weekend batch schedule and check in after two weeks.",
                          "suggested_timing": "In 1–2 weeks", "days": 10},
            "action_items": [{"owner": "sales", "item": "Send weekend batch schedule", "due_hint": "Today"}],
            "risk_signals": [{"signal": "Time concern", "evidence": "\"That's difficult.\""},
                             {"signal": "No immediate decision", "evidence": "\"I'll look when things calm down at work.\""}],
            "positive_signals": [{"signal": "Accepted follow-up material", "evidence": "\"Sure, you can send it.\""}],
            "explicit_statements": [{"speaker": "lead", "quote": "I'm not sure I can commit right now.", "topic": "Commitment"}],
            "ai_interpretations": [{"interpretation": "Motivation appears externally driven (manager suggestion) rather than personal.",
                                    "basis": "\"My manager mentioned upskilling in the appraisal.\"", "confidence": 0.6}],
            "meeting_outcome": "Low interest — nurture",
            "confidence": 0.78,
        },
    },
    "ready_to_enroll": {
        "lines": [
            ("sales", "Hi {lead}, {sales} here. Good to speak again!"),
            ("lead", "Hi! I went through the brochure you sent. I'm pretty convinced."),
            ("sales", "That's great to hear. What stood out for you?"),
            ("lead", "The capstone project and the mentor reviews. I compared it with another course and theirs was only recorded videos."),
            ("sales", "Exactly — every project is reviewed live by a working engineer. Did you have any open questions?"),
            ("lead", "When does the next batch start?"),
            ("sales", "The next batch starts on the first of next month. Seats are limited to forty."),
            ("lead", "And can I pay the full amount upfront? Is there a discount for that?"),
            ("sales", "Yes, upfront payment gets an additional five percent off, so it comes to eighty-five thousand five hundred."),
            ("lead", "Perfect. How do I enroll?"),
            ("sales", "I'll send you the enrollment link right after this call. It takes about ten minutes."),
            ("lead", "Great, I'll complete it today."),
        ],
        "analysis": {
            "summary": "{lead} returned after reviewing the brochure and was ready to enroll in {product}. The lead valued the capstone and mentor reviews over a recorded-only competitor, asked about the next batch date and upfront payment discount, and committed to completing enrollment the same day.",
            "conversation_language": "English",
            "lead_intent": "Enroll in the next batch.",
            "interest_level": "high",
            "purchase_intent": "high",
            "lead_sentiment": "positive",
            "sales_sentiment": "positive",
            "engagement": {"level": "high", "rationale": "Came prepared, asked buying questions and committed to a next step.",
                           "signals": [
                               {"signal": "Asked about enrollment", "evidence": "\"How do I enroll?\""},
                               {"signal": "Discussed timeline", "evidence": "\"When does the next batch start?\""},
                               {"signal": "Requested pricing", "evidence": "\"Is there a discount for that?\""}]},
            "topics_discussed": ["Brochure review", "Capstone project", "Competition", "Batch start date", "Payment", "Enrollment"],
            "lead_questions": [
                {"question": "When does the next batch start?", "answered": True, "evidence": "First of next month; 40 seats."},
                {"question": "Is there a discount for paying upfront?", "answered": True, "evidence": "Additional 5% off → ₹85,500."},
                {"question": "How do I enroll?", "answered": True, "evidence": "Enrollment link to be sent after the call."}],
            "lead_objections": [],
            "lead_requirements": ["Mentor-reviewed projects", "Upfront payment option"],
            "pain_points": [],
            "interests": ["{product}", "Capstone project", "Mentor reviews"],
            "competitor_mentions": ["Recorded-video course (unnamed)"],
            "pricing_discussion": {"discussed": True, "details": "Upfront payment discount of 5% → ₹85,500."},
            "product_discussion": ["Capstone project", "Live mentor reviews", "Batch size"],
            "sales_pitch": {"pitch_detected": True, "topics_covered": ["Introduction", "Differentiators", "Pricing", "Next Steps", "Call-to-Action"],
                            "missing_topics": ["Need Discovery", "Placement"]},
            "coverage": {"Introduction": True, "Problem Identification": False, "Need Discovery": False, "Product Explanation": True,
                         "Benefits": True, "Course Details": True, "Pricing": True, "Placement": False, "Differentiators": True,
                         "Objection Handling": True, "Next Steps": True, "Call-to-Action": True},
            "objection_handling": "No objections raised.",
            "follow_up": {"required": True, "reason": "Lead committed to enroll today; enrollment link must be sent.",
                          "recommended_next_action": "Send the enrollment link and confirm completion by end of day.",
                          "suggested_timing": "Today", "days": 0},
            "action_items": [{"owner": "sales", "item": "Send enrollment link", "due_hint": "Right after the call"},
                             {"owner": "lead", "item": "Complete enrollment form", "due_hint": "Today"}],
            "risk_signals": [],
            "positive_signals": [{"signal": "Asked enrollment process", "evidence": "\"How do I enroll?\""},
                                 {"signal": "Asked next batch date", "evidence": "\"When does the next batch start?\""},
                                 {"signal": "Committed to act", "evidence": "\"I'll complete it today.\""}],
            "explicit_statements": [{"speaker": "lead", "quote": "I'm pretty convinced.", "topic": "Intent"},
                                    {"speaker": "lead", "quote": "Great, I'll complete it today.", "topic": "Commitment"}],
            "ai_interpretations": [{"interpretation": "High likelihood of conversion this week.", "basis": "Explicit commitment and payment questions.", "confidence": 0.85}],
            "meeting_outcome": "Ready to enroll",
            "confidence": 0.9,
        },
    },
}

SCENARIO_KEYS = list(SCENARIOS.keys())


def pick_scenario(seed: str) -> str:
    """A scenario key passes through; anything else is hashed deterministically."""
    if seed in SCENARIOS:
        return seed
    digest = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return SCENARIO_KEYS[digest % len(SCENARIO_KEYS)]


def _fill(value: Any, ctx: Dict[str, str]) -> Any:
    if isinstance(value, str):
        out = value
        for k, v in ctx.items():
            out = out.replace("{" + k + "}", v)
        return out
    if isinstance(value, list):
        return [_fill(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, ctx) for k, v in value.items()}
    return value


def _ctx(lead_name: str, sales_name: str, product: str) -> Dict[str, str]:
    return {"lead": lead_name.split()[0] if lead_name else "there", "sales": sales_name or "the sales team",
            "product": product or "the program"}


def mock_transcript(scenario: str, lead_name: str, sales_name: str, product: str, lead_email: str = "",
                    target_seconds: float = None) -> Dict[str, Any]:
    """Return a TranscriptionResult-shaped dict with plausible timings.

    When `target_seconds` is given, turns are stretched to span the meeting so
    derived talk-time metrics stay consistent with the meeting duration."""
    ctx = _ctx(lead_name, sales_name, product)
    raw = []
    t = 4.0
    for speaker, text in SCENARIOS[scenario]["lines"]:
        text = _fill(text, ctx)
        dur = max(2.5, len(text.split()) / 2.6)  # ~155 wpm
        raw.append((speaker, text, t, dur))
        t += dur + (1.2 if speaker == "sales" else 1.8)
    scale = (target_seconds * 0.92 / t) if target_seconds and t < target_seconds else 1.0
    segments = [{
        "speaker": speaker,
        "speaker_name": sales_name if speaker == "sales" else lead_name,
        "start_seconds": round(start * scale, 1),
        "end_seconds": round((start + dur) * scale, 1),
        "text": text,
    } for speaker, text, start, dur in raw]
    return {"language": "en", "has_speaker_labels": True, "has_timestamps": True, "segments": segments}


def mock_analysis(scenario: str, lead_name: str, sales_name: str, product: str, checklist: List[str] = None) -> Dict[str, Any]:
    ctx = _ctx(lead_name, sales_name, product)
    data = _fill(dict(SCENARIOS[scenario]["analysis"]), ctx)
    coverage_map = data.pop("coverage", {})
    days = data["follow_up"].pop("days", 1)
    checklist = checklist or DEFAULT_PITCH_CHECKLIST
    data["pitch_coverage"] = [
        {"topic": topic, "covered": bool(coverage_map.get(topic, False)),
         "confidence": 0.9 if coverage_map.get(topic) else 0.75,
         "evidence": f"AI-generated transcript reference: {topic.lower()} {'discussed' if coverage_map.get(topic) else 'not detected'}"}
        for topic in checklist
    ]
    data["follow_up"]["suggested_follow_up_date"] = None
    data["_follow_up_days"] = days
    return data
