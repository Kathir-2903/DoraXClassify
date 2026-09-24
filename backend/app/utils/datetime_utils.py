"""Time helpers. Everything is stored as timezone-aware UTC; Asia/Kolkata is
the default display and scheduling timezone."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config.settings import settings

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def get_zone(name: Optional[str] = None) -> ZoneInfo:
    return ZoneInfo(name or settings.default_timezone)


def is_valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def local_to_utc(d: date, t: time, tz_name: Optional[str] = None) -> datetime:
    """Interpret a wall-clock date/time in `tz_name` and return UTC."""
    local = datetime.combine(d, t).replace(tzinfo=get_zone(tz_name))
    return local.astimezone(UTC)


def to_unix(dt: datetime) -> int:
    return int(ensure_utc(dt).timestamp())


def from_unix(value: Any) -> Optional[datetime]:
    """Accept unix seconds or milliseconds (webhook payloads vary)."""
    if value in (None, "", 0):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return parse_datetime(value)
    if num > 10_000_000_000:  # milliseconds
        num = num / 1000
    return datetime.fromtimestamp(num, UTC)


def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, (int, float)):
        return from_unix(value)
    text = str(value).strip()
    if text.isdigit():
        return from_unix(int(text))
    try:
        return ensure_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_local(dt: Optional[datetime], tz_name: Optional[str] = None) -> Optional[datetime]:
    if dt is None:
        return None
    return ensure_utc(dt).astimezone(get_zone(tz_name))


def format_local(dt: Optional[datetime], fmt: str = "%d %b %Y, %I:%M %p", tz_name: Optional[str] = None) -> str:
    local = to_local(dt, tz_name)
    return local.strftime(fmt) if local else ""


def start_of_day_local(days_ago: int = 0, tz_name: Optional[str] = None) -> datetime:
    zone = get_zone(tz_name)
    today = datetime.now(zone).date() - timedelta(days=days_ago)
    return datetime.combine(today, time.min).replace(tzinfo=zone).astimezone(UTC)


def humanize_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min" if sec == 0 else f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"
