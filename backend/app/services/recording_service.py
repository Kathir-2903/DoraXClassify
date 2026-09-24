"""Recording retrieval and media processing.

Classify's webhook may only give us an S3 URL. We access it server-side:
  * s3://bucket/key or https://bucket.s3.<region>.amazonaws.com/key (and the
    path-style variant) → downloaded with boto3 using S3_ACCESS_KEY/SECRET
    when configured;
  * any other http(s) URL (e.g. a pre-signed link) → streamed with httpx;
  * mock://… → demo recordings (no bytes, marked as mock).
Files are stored under RECORDING_STORAGE_DIR and streamed to authorised users
through the API — credentials and source URLs never reach the browser."""
import asyncio
import logging
import mimetypes
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


class RecordingError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class RecordingFile:
    path: Optional[str]
    content_type: str
    size_bytes: Optional[int]
    duration_seconds: Optional[float]
    is_mock: bool = False


_VIRTUAL_HOSTED = re.compile(r"^(?P<bucket>[^.]+(?:\.[^.]+)*?)\.s3[.-](?:(?P<region>[a-z0-9-]+)\.)?amazonaws\.com$")
_PATH_STYLE = re.compile(r"^s3[.-](?:(?P<region>[a-z0-9-]+)\.)?amazonaws\.com$")


def parse_s3_url(url: str) -> Optional[Tuple[str, str]]:
    """Return (bucket, key) for S3 URLs, else None."""
    parsed = urlparse(url)
    if parsed.scheme == "s3":
        return parsed.netloc, unquote(parsed.path.lstrip("/"))
    if parsed.scheme not in ("http", "https"):
        return None
    host = parsed.netloc.lower()
    m = _VIRTUAL_HOSTED.match(host)
    if m and m.group("bucket") != "s3":
        return m.group("bucket"), unquote(parsed.path.lstrip("/"))
    if _PATH_STYLE.match(host):
        parts = parsed.path.lstrip("/").split("/", 1)
        if len(parts) == 2:
            return parts[0], unquote(parts[1])
    return None


def _storage_dir() -> Path:
    path = Path(settings.recording_storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _guess_ext(url: str, content_type: Optional[str]) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    if ext in (".mp4", ".webm", ".mkv", ".mov", ".m4a", ".mp3", ".wav", ".ogg", ".aac"):
        return ext
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) if content_type else None
    return guessed or ".mp4"


def _s3_download_sync(bucket: str, key: str, dest: str) -> Tuple[str, int]:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region or None,
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
    )
    head = client.head_object(Bucket=bucket, Key=key)
    size = int(head.get("ContentLength") or 0)
    if size > settings.recording_max_bytes:
        raise RecordingError("Recording exceeds the configured size limit", retryable=False)
    client.download_file(bucket, key, dest)
    return head.get("ContentType") or "video/mp4", size


async def _http_download(url: str, dest: str) -> Tuple[str, int]:
    written = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0), follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            if resp.status_code in (401, 403):
                raise RecordingError(f"Access to the recording was denied ({resp.status_code})", retryable=False)
            if resp.status_code == 404:
                raise RecordingError("Recording not found at the source URL", retryable=True)
            if resp.status_code >= 400:
                raise RecordingError(f"Recording download failed ({resp.status_code})")
            content_type = resp.headers.get("content-type", "video/mp4")
            with open(dest, "wb") as fh:
                async for chunk in resp.aiter_bytes(1024 * 1024):
                    written += len(chunk)
                    if written > settings.recording_max_bytes:
                        raise RecordingError("Recording exceeds the configured size limit", retryable=False)
                    fh.write(chunk)
    return content_type, written


async def probe_duration(path: str) -> Optional[float]:
    if not shutil.which(settings.ffprobe_binary):
        return None
    proc = await asyncio.create_subprocess_exec(
        settings.ffprobe_binary, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    try:
        return round(float(out.decode().strip()), 1)
    except ValueError:
        return None


async def download_recording(meeting_id: str, url: str) -> RecordingFile:
    if url.startswith("mock://"):
        return RecordingFile(path=None, content_type="video/mp4", size_bytes=None, duration_seconds=None, is_mock=True)

    tmp = _storage_dir() / f"{meeting_id}.part"
    s3 = parse_s3_url(url)
    try:
        if s3 and settings.s3_access_key and settings.s3_secret_key:
            bucket, key = s3
            content_type, size = await asyncio.to_thread(_s3_download_sync, bucket, key, str(tmp))
        elif url.startswith("s3://"):
            raise RecordingError("S3 credentials are not configured (S3_ACCESS_KEY / S3_SECRET_KEY)", retryable=False)
        else:
            content_type, size = await _http_download(url, str(tmp))
    except RecordingError:
        tmp.unlink(missing_ok=True)
        raise
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        name = type(exc).__name__
        retryable = name not in ("NoCredentialsError", "InvalidAccessKeyId")
        if name == "ClientError":
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            retryable = code not in ("403", "AccessDenied", "404", "NoSuchKey", "InvalidAccessKeyId", "SignatureDoesNotMatch")
            name = f"S3 {code or 'error'}"
        raise RecordingError(f"Recording download failed: {name}", retryable=retryable) from exc

    final = _storage_dir() / f"{meeting_id}{_guess_ext(url, content_type)}"
    os.replace(tmp, final)
    duration = await probe_duration(str(final))
    return RecordingFile(path=str(final), content_type=content_type.split(";")[0], size_bytes=size, duration_seconds=duration)


async def extract_audio(video_path: str) -> Optional[str]:
    """Extract a mono 16 kHz audio track for transcription. Returns None when
    FFmpeg is unavailable — Gemini can then take the original media."""
    if not shutil.which(settings.ffmpeg_binary):
        logger.info("recording.ffmpeg_missing")
        return None
    out = str(Path(video_path).with_suffix(".audio.mp3"))
    proc = await asyncio.create_subprocess_exec(
        settings.ffmpeg_binary, "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", out,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("recording.ffmpeg_failed", extra={"stderr": err.decode(errors="ignore")[-300:]})
        return None
    return out


def local_file_for_stream(path: Optional[str]) -> Optional[Path]:
    if not path:
        return None
    p = Path(path)
    base = Path(settings.recording_storage_dir).resolve()
    try:
        p.resolve().relative_to(base)
    except ValueError:
        return None  # never stream files outside the storage directory
    return p if p.exists() else None
