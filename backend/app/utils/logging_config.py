"""Structured JSON logging. Extra fields passed via `extra={...}` are emitted as
top-level keys; known secret-bearing keys are always masked."""
import json
import logging
import sys
from datetime import datetime, timezone

from app.utils.security import redact

_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(redact(entry), default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # httpx logs full URLs at INFO; keep it quiet so query strings never leak.
    for noisy in ("httpx", "httpcore", "pymongo", "botocore", "urllib3", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
