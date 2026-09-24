import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request

from app.middleware.error_handler import AppError
from app.services import webhook_service
from app.utils.security import verify_webhook
from app.workers.meeting_processor import processor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


async def _process_then_wake(event_id: str) -> None:
    await webhook_service.process_event(event_id)
    processor.wake()


@router.post(
    "/classify",
    summary="Classify meeting webhook (attendance, recordings, transcripts)",
    responses={200: {"description": "Accepted (or duplicate ignored)"}, 401: {"description": "Invalid webhook credentials"}},
)
async def classify_webhook(request: Request, background: BackgroundTasks):
    """Authenticate with the shared `api-key` header (Classify's documented
    pattern) or `X-Classify-Signature: sha256=<hmac of raw body>` using
    WEBHOOK_SECRET. The payload is stored verbatim, deduplicated by event id
    and processed asynchronously; the response returns immediately."""
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    if not verify_webhook(raw, headers.get("api-key"), headers.get("x-classify-signature")):
        logger.warning("webhook.rejected", extra={"reason": "invalid_credentials"})
        raise AppError("Invalid webhook credentials", 401, "invalid_webhook_credentials")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise AppError("Webhook body must be JSON", 400, "invalid_json")
    if not isinstance(payload, dict):
        raise AppError("Webhook body must be a JSON object", 400, "invalid_json")
    event_id, duplicate = await webhook_service.ingest(payload, raw, headers)
    if not duplicate:
        background.add_task(_process_then_wake, event_id)
    return {"received": True, "event_id": event_id, "duplicate": duplicate}
