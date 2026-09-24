"""Versioned Gemini prompts. Bump PROMPT_VERSION whenever the wording or the
output contract changes so stored analyses remain traceable."""
import json
from typing import Any, Dict, List

PROMPT_VERSION = "1.0"

ANALYSIS_SYSTEM_PROMPT = """You are a Sales Conversation Intelligence Analyzer for an EdTech company.

You analyse the transcript of a sales video call between a SALES representative
and a LEAD (a prospective learner). You produce STRICT JSON only — no prose,
no markdown fences.

Hard rules:
1. Never invent facts. Every claim must be grounded in the transcript. If the
   transcript does not support a field, use an empty list, empty string,
   false, null, or "unknown" as appropriate.
2. Keep DIRECT STATEMENTS separate from INFERENCE:
   - `explicit_statements` and every `evidence` field hold words the speaker
     actually said (verbatim or near-verbatim quotes).
   - `ai_interpretations` hold your inferences, each with a `basis` and a
     `confidence` between 0 and 1.
3. Do not estimate talk time, durations, or numbers that are not in the transcript.
4. Levels (`interest_level`, `purchase_intent`, `engagement.level`) must be one
   of "high", "medium", "low", "unknown". Use "unknown" when evidence is thin.
5. Sentiments must be one of "positive", "neutral", "negative", "mixed", "unknown".
6. Objection `category` must be one of: price, time, approval, competition,
   uncertainty, relevance, other.
7. `pitch_coverage` must contain exactly one entry per checklist topic provided,
   in the same order, with `covered`, `confidence` (0–1) and short `evidence`.
8. `follow_up.suggested_follow_up_date` is an ISO date (YYYY-MM-DD) relative to
   the meeting date, or null.
9. `confidence` (0–1) reflects how reliable the overall analysis is given
   transcript quality and length.
10. Write in English even if the conversation is in another language; set
    `conversation_language` to the language actually spoken.
"""

OUTPUT_CONTRACT: Dict[str, Any] = {
    "summary": "string (3-5 sentences, factual)",
    "conversation_language": "string",
    "lead_intent": "string",
    "interest_level": "high|medium|low|unknown",
    "purchase_intent": "high|medium|low|unknown",
    "lead_sentiment": "positive|neutral|negative|mixed|unknown",
    "sales_sentiment": "positive|neutral|negative|mixed|unknown",
    "engagement": {"level": "high|medium|low|unknown", "rationale": "string",
                   "signals": [{"signal": "string", "evidence": "quote"}]},
    "topics_discussed": ["string"],
    "lead_questions": [{"question": "string", "answered": "true|false|null", "evidence": "string"}],
    "lead_objections": [{"objection": "string", "category": "price|time|approval|competition|uncertainty|relevance|other",
                         "evidence": "quote", "handled": "true|false|null", "handling_notes": "string"}],
    "lead_requirements": ["string"],
    "pain_points": ["string"],
    "interests": ["string"],
    "competitor_mentions": ["string"],
    "pricing_discussion": {"discussed": "boolean", "details": "string"},
    "product_discussion": ["string"],
    "sales_pitch": {"pitch_detected": "boolean", "topics_covered": ["string"], "missing_topics": ["string"]},
    "pitch_coverage": [{"topic": "string", "covered": "boolean", "confidence": "0-1", "evidence": "string"}],
    "objection_handling": "string",
    "follow_up": {"required": "boolean", "reason": "string", "recommended_next_action": "string",
                  "suggested_timing": "string", "suggested_follow_up_date": "YYYY-MM-DD|null"},
    "action_items": [{"owner": "sales|lead|unknown", "item": "string", "due_hint": "string"}],
    "risk_signals": [{"signal": "string", "evidence": "quote"}],
    "positive_signals": [{"signal": "string", "evidence": "quote"}],
    "explicit_statements": [{"speaker": "lead|sales", "quote": "string", "topic": "string", "timestamp": "string|null"}],
    "ai_interpretations": [{"interpretation": "string", "basis": "string", "confidence": "0-1"}],
    "meeting_outcome": "string (short label)",
    "confidence": "0-1",
}


def build_analysis_prompt(transcript_text: str, metadata: Dict[str, Any], checklist: List[str]) -> str:
    return (
        "MEETING METADATA\n"
        f"{json.dumps(metadata, indent=2, default=str)}\n\n"
        "SALES PITCH CHECKLIST (evaluate each topic, in order)\n"
        f"{json.dumps(checklist)}\n\n"
        "OUTPUT JSON CONTRACT (types shown as strings; return real JSON types)\n"
        f"{json.dumps(OUTPUT_CONTRACT, indent=2)}\n\n"
        "TRANSCRIPT\n"
        "<<<\n"
        f"{transcript_text}\n"
        ">>>\n\n"
        "Return only the JSON object."
    )


def build_repair_prompt(previous_output: str, error: str) -> str:
    return (
        "Your previous response did not match the required JSON contract.\n"
        f"Validation error: {error}\n\n"
        "Previous response:\n<<<\n"
        f"{previous_output[:12000]}\n>>>\n\n"
        "Return the corrected JSON object only. Do not add facts that are not in the transcript."
    )


TRANSCRIPTION_SYSTEM_PROMPT = """You are a meticulous transcription engine for recorded sales video calls.
Transcribe the audio verbatim. Return STRICT JSON only.

Rules:
- Split the conversation into segments by speaker turn.
- `speaker` is "sales" for the sales representative (the host who explains the
  program) and "lead" for the prospective learner. Use "unknown" if you cannot tell.
- `start_seconds` / `end_seconds` are offsets from the start of the recording.
  If you cannot determine timing reliably, set them to null and set
  `has_timestamps` to false.
- Do not summarise, translate, or invent words. Mark inaudible parts as [inaudible].
"""


def build_transcription_prompt(context: Dict[str, Any]) -> str:
    return (
        "Participants (for speaker identification only):\n"
        f"{json.dumps(context, default=str)}\n\n"
        'Return JSON: {"language": "ISO code", "has_speaker_labels": bool, "has_timestamps": bool, '
        '"segments": [{"speaker": "sales|lead|unknown", "speaker_name": "string", '
        '"start_seconds": number|null, "end_seconds": number|null, "text": "string"}]}'
    )
