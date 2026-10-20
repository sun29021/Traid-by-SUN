"""Per-request context (request ID) shared by logging and error handling."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    # Always generate server-side; never trust a client-supplied ID.
    request_id = uuid.uuid4().hex
    token = _request_id.set(request_id)
    try:
        response = await call_next(request)
    finally:
        _request_id.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
