"""Typed application errors and the single error-envelope handler (API.md §1.1, §1.3)."""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id

logger = logging.getLogger("traid.errors")


class ErrorCode(StrEnum):
    """Closed list of error codes. Adding a code requires updating API.md §1.3."""

    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    FORBIDDEN = "FORBIDDEN"
    CSRF_FAILED = "CSRF_FAILED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    SETUP_ALREADY_DONE = "SETUP_ALREADY_DONE"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    IMAGE_DECODE_FAILED = "IMAGE_DECODE_FAILED"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    DUPLICATE_FILE = "DUPLICATE_FILE"
    INVALID_STATE = "INVALID_STATE"
    PROFILE_ARCHIVED = "PROFILE_ARCHIVED"
    PROFILE_NOT_READY = "PROFILE_NOT_READY"
    GLYPH_MISSING = "GLYPH_MISSING"
    CHAR_NOT_IN_CHARSET = "CHAR_NOT_IN_CHARSET"
    PATTERN_MISMATCH = "PATTERN_MISMATCH"
    INVALID_PATTERN = "INVALID_PATTERN"
    NO_TEXT_FOUND = "NO_TEXT_FOUND"
    SEGMENTATION_FAILED = "SEGMENTATION_FAILED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    INPAINT_FALLBACK_USED = "INPAINT_FALLBACK_USED"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    TASK_INTERRUPTED = "TASK_INTERRUPTED"
    TASK_CANCELLED = "TASK_CANCELLED"
    STORAGE_ERROR = "STORAGE_ERROR"
    DISK_FULL = "DISK_FULL"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base class for all expected application errors."""

    http_status: int = 500
    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details


class BadRequest(AppError):
    http_status = 400
    code = ErrorCode.VALIDATION_FAILED


class Unauthorized(AppError):
    http_status = 401
    code = ErrorCode.UNAUTHENTICATED


class Forbidden(AppError):
    http_status = 403
    code = ErrorCode.FORBIDDEN


class NotFound(AppError):
    http_status = 404
    code = ErrorCode.NOT_FOUND


class Conflict(AppError):
    http_status = 409
    code = ErrorCode.CONFLICT


class PayloadTooLarge(AppError):
    http_status = 413
    code = ErrorCode.UPLOAD_TOO_LARGE


class UnsupportedMediaType(AppError):
    http_status = 415
    code = ErrorCode.UNSUPPORTED_MEDIA_TYPE


class ValidationFailed(AppError):
    http_status = 422
    code = ErrorCode.VALIDATION_FAILED


class TooManyRequests(AppError):
    http_status = 429
    code = ErrorCode.RATE_LIMITED


class StorageFailure(AppError):
    http_status = 500
    code = ErrorCode.STORAGE_ERROR


class EngineUnavailable(AppError):
    http_status = 503
    code = ErrorCode.MODEL_UNAVAILABLE


def _envelope(
    code: ErrorCode, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code.value, "message": message, "request_id": get_request_id()}
    if details:
        error["details"] = details
    return {"error": error}


_HTTP_STATUS_CODES: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.VALIDATION_FAILED,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.UPLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    429: ErrorCode.RATE_LIMITED,
}


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 — registered for AppError only
    return JSONResponse(
        status_code=exc.http_status, content=_envelope(exc.code, exc.message, exc.details)
    )


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    fields = [
        {
            "path": ".".join(
                str(part) for part in err.get("loc", ()) if part not in ("body", "query", "path")
            ),
            "code": ErrorCode.VALIDATION_FAILED.value,
            "message": str(err.get("msg", "Invalid value")),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_envelope(
            ErrorCode.VALIDATION_FAILED, "Request validation failed", {"fields": fields}
        ),
    )


async def _handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = _HTTP_STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code, content=_envelope(code, message), headers=exc.headers
    )


async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    # Full traceback goes to the log only; the client gets a request ID to correlate.
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=_envelope(
            ErrorCode.INTERNAL_ERROR, "Something went wrong. Check the logs for this request ID."
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
