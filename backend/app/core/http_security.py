"""HTTP security middleware (ARCHITECTURE.md §14).

- Host allow-list: blocks DNS-rebinding attacks against the local server.
- Security headers on every response; API responses are never cached.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable

from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import ErrorCode
from app.core.request_context import get_request_id

Middleware = Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
TEST_CLIENT_HOST = "testserver"

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; "
    "script-src 'self'; font-src 'self'; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
STATIC_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
# Interactive API docs load their own scripts; they exist only outside production.
DOCS_PATHS = frozenset({"/api/docs", "/api/openapi.json"})


def hostname(host_header: str) -> str:
    """Host header without port, lower-cased; IPv6 literals keep their brackets."""
    host = host_header.strip().lower()
    if host.startswith("["):
        return host.split("]", 1)[0] + "]"
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def host_guard(allowed_hosts: Iterable[str]) -> Middleware:
    allowed = frozenset(allowed_hosts)

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if hostname(request.headers.get("host", "")) not in allowed:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": ErrorCode.FORBIDDEN.value,
                        "message": "Invalid Host header",
                        "request_id": get_request_id(),
                    }
                },
            )
        return await call_next(request)

    return middleware


def security_headers(*, docs_enabled: bool) -> Middleware:
    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        for name, value in STATIC_SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if not (docs_enabled and path in DOCS_PATHS):
            response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    return middleware
