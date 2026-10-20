"""JSON logging to a rotating file in `data/logs` (+ console in development).

Never log passwords, session tokens, CSRF secrets, token values or image content
(ARCHITECTURE.md §13). Log IDs instead.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings
from app.core.request_context import get_request_id

_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS}
        if extras:
            payload.update(extras)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = JsonFormatter()

    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        settings.logs_dir / "traid.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if not settings.is_production:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

    # Uvicorn's access log would print raw query strings; we log requests ourselves.
    logging.getLogger("uvicorn.access").disabled = True


_access_logger = logging.getLogger("traid.http")


async def access_log_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    # Log the route template (e.g. /api/v1/jobs/{job_id}), never raw query values.
    path = getattr(route, "path", request.url.path)
    _access_logger.info(
        "request",
        extra={
            "method": request.method,
            "path": path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return response
