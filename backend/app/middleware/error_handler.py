"""Consistent error envelopes. Internal details and stack traces never reach clients."""
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Domain error with a user-facing message."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "bad_request",
        reason: Optional[str] = None,
        hint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.reason = reason
        self.hint = hint
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, resource: str = "Resource"):
        super().__init__(f"{resource} not found", status_code=404, code="not_found")


class ForbiddenError(AppError):
    def __init__(self, message: str = "You do not have access to this resource"):
        super().__init__(message, status_code=403, code="forbidden")


def _body(code: str, message: str, reason=None, hint=None, details=None, request_id=None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if reason:
        error["reason"] = reason
    if hint:
        error["hint"] = hint
    if details:
        error["details"] = details
    if request_id:
        error["request_id"] = request_id
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.reason, exc.hint, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(f"http_{exc.status_code}", message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        fields = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
            msg = str(err.get("msg", "Invalid value")).replace("Value error, ", "")
            fields.append({"field": ".".join(loc), "message": msg})
        first = fields[0]["message"] if fields else "Invalid request"
        return JSONResponse(
            status_code=422,
            content=_body("validation_error", first, details={"fields": fields}),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        request_id = uuid.uuid4().hex[:12]
        logger.exception("unhandled_error", extra={"request_id": request_id, "path": request.url.path})
        return JSONResponse(
            status_code=500,
            content=_body("internal_error", "Something went wrong. Please try again.", request_id=request_id),
        )
