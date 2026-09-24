"""Transcript acquisition, normalisation and storage.

Priority: a transcript supplied by Classify (webhook or assets API) → otherwise
Gemini transcription of the downloaded recording. Speaker labels and
timestamps are stored only when the source actually provides them."""
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.database.mongodb import Collections, get_db
from app.models.analysis import TranscriptionResult
from app.utils.datetime_utils import utcnow

logger = logging.getLogger(__name__)

_CUE_TIME = re.compile(
    r"(?P<s>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})\s*-->\s*(?P<e>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})"
)
_VOICE = re.compile(r"^<v\s+([^>]+)>(.*)$")
_SPEAKER_PREFIX = re.compile(r"^([A-Za-z][\w .'-]{0,40}):\s+(.+)$")


def _ts_to_seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def _classify_speaker(name: str, lead: Dict[str, Any], host: Dict[str, Any]) -> str:
    n = (name or "").strip().lower()
    if not n:
        return "unknown"
    lead_tokens = {(lead.get("name") or "").lower(), (lead.get("email") or "").lower(), "lead", "student", "guest"}
    host_tokens = {(host.get("name") or "").lower(), (host.get("email") or "").lower(), "host", "sales", "teacher"}
    if n in host_tokens or any(t and t.split()[0] == n.split()[0] for t in host_tokens if t and "@" not in t):
        return "sales"
    if n in lead_tokens or any(t and t.split()[0] == n.split()[0] for t in lead_tokens if t and "@" not in t):
        return "lead"
    return "unknown"


def parse_caption_text(text: str, lead: Dict[str, Any], host: Dict[str, Any]) -> Optional[TranscriptionResult]:
    """Parse WebVTT/SRT captions, or 'Name: text' plain transcripts."""
    lines = [l.rstrip() for l in text.replace("\r\n", "\n").split("\n")]
    segments: List[Dict[str, Any]] = []
    i = 0
    has_cues = any(_CUE_TIME.search(l) for l in lines)
    if has_cues:
        while i < len(lines):
            m = _CUE_TIME.search(lines[i])
            if not m:
                i += 1
                continue
            start, end = _ts_to_seconds(m.group("s")), _ts_to_seconds(m.group("e"))
            i += 1
            body = []
            while i < len(lines) and lines[i].strip():
                body.append(lines[i].strip())
                i += 1
            content = " ".join(body)
            speaker_name = ""
            vm = _VOICE.match(content)
            if vm:
                speaker_name, content = vm.group(1).strip(), re.sub(r"</v>", "", vm.group(2)).strip()
            else:
                sm = _SPEAKER_PREFIX.match(content)
                if sm:
                    speaker_name, content = sm.group(1).strip(), sm.group(2).strip()
            if content:
                segments.append({"speaker": _classify_speaker(speaker_name, lead, host), "speaker_name": speaker_name,
                                 "start_seconds": start, "end_seconds": end, "text": content})
    else:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            sm = _SPEAKER_PREFIX.match(line)
            if sm:
                segments.append({"speaker": _classify_speaker(sm.group(1), lead, host), "speaker_name": sm.group(1),
                                 "start_seconds": None, "end_seconds": None, "text": sm.group(2)})
            else:
                segments.append({"speaker": "unknown", "speaker_name": "", "start_seconds": None, "end_seconds": None, "text": line})
    if not segments:
        return None
    return TranscriptionResult(
        language="unknown",
        has_speaker_labels=any(s["speaker"] != "unknown" for s in segments),
        has_timestamps=has_cues,
        segments=segments,
    )


def _from_structured(items: List[Any], lead, host) -> Optional[TranscriptionResult]:
    segments = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("transcript") or item.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        name = str(item.get("speaker") or item.get("speakerName") or item.get("name") or item.get("email") or "")
        start = item.get("start") if item.get("start") is not None else item.get("startTime")
        end = item.get("end") if item.get("end") is not None else item.get("endTime")
        try:
            start = float(start) if start is not None else None
            end = float(end) if end is not None else None
        except (TypeError, ValueError):
            start = end = None
        segments.append({"speaker": _classify_speaker(name, lead, host), "speaker_name": name,
                         "start_seconds": start, "end_seconds": end, "text": text.strip()})
    if not segments:
        return None
    return TranscriptionResult(
        language="unknown",
        has_speaker_labels=any(s["speaker"] != "unknown" for s in segments),
        has_timestamps=all(s["start_seconds"] is not None and s["end_seconds"] is not None for s in segments),
        segments=segments,
    )


async def from_classify_entries(entries: List[Any], lead: Dict[str, Any], host: Dict[str, Any]) -> Optional[TranscriptionResult]:
    """Best-effort normalisation of whatever transcript material Classify sent."""
    for entry in entries:
        candidates = entry if isinstance(entry, list) else [entry]
        structured = _from_structured(candidates, lead, host) if any(isinstance(c, dict) for c in candidates) else None
        if structured:
            return structured
        for c in candidates:
            url = None
            if isinstance(c, str) and c.startswith(("http://", "https://")):
                url = c
            elif isinstance(c, dict):
                url = next((v for v in c.values() if isinstance(v, str) and v.startswith(("http://", "https://"))), None)
            if url:
                try:
                    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                        resp = await client.get(url)
                    if resp.status_code == 200 and resp.text.strip():
                        try:
                            data = resp.json()
                            items = data if isinstance(data, list) else data.get("segments") or data.get("transcript") or []
                            parsed = _from_structured(items, lead, host) if isinstance(items, list) else None
                        except ValueError:
                            parsed = parse_caption_text(resp.text, lead, host)
                        if parsed:
                            return parsed
                except httpx.HTTPError:
                    logger.warning("transcript.classify_fetch_failed")
            elif isinstance(c, str) and len(c.strip()) > 40:
                parsed = parse_caption_text(c, lead, host)
                if parsed:
                    return parsed
    return None


def _fmt_ts(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def transcript_to_text(segments: List[Dict[str, Any]], has_timestamps: bool, has_speakers: bool) -> str:
    out = []
    for s in segments:
        prefix = []
        if has_timestamps and s.get("start_seconds") is not None:
            prefix.append(f"[{_fmt_ts(s['start_seconds'])}]")
        if has_speakers:
            prefix.append((s.get("speaker") or "unknown").upper() + ":")
        out.append((" ".join(prefix) + " " + s["text"]).strip())
    return "\n".join(out)


async def store_transcript(meeting_id, result: TranscriptionResult, source: str, model: Optional[str],
                           is_mock: bool = False) -> Dict[str, Any]:
    segments = [s.model_dump() for s in result.segments]
    doc = {
        "meeting_id": meeting_id,
        "source": source,  # classify | gemini | mock
        "model": model,
        "language": result.language,
        "has_speaker_labels": result.has_speaker_labels,
        "has_timestamps": result.has_timestamps,
        "segments": segments,
        "text": transcript_to_text(segments, result.has_timestamps, result.has_speaker_labels),
        "is_mock": is_mock,
        "created_at": utcnow(),
    }
    await get_db()[Collections.MEETING_TRANSCRIPTS].replace_one({"meeting_id": meeting_id}, doc, upsert=True)
    return doc
