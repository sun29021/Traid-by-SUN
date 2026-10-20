"""HTTP security middleware (ARCHITECTURE.md §7.1, §14).

- Host allow-list: blocks DNS-rebinding attacks against the local server.
- Local request guard: only Traid's own page may call the API. There is no sign-in
  (PRD D-03), so this is what stops other websites from changing data.
- Security headers on every response; API responses are never cached.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable

from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import ErrorCode, error_response

Middleware = Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
TEST_CLIENT_HOST = "testserver"

CLIENT_HEADER = "X-Traid-Client"
CLIENT_HEADER_VALUE = "web"
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

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


def local_origins(port: int) -> set[str]:
    return {f"http://{host}:{port}" for host in LOCAL_HOSTS}


def host_guard(allowed_hosts: Iterable[str]) -> Middleware:
    allowed = frozenset(allowed_hosts)

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if hostname(request.headers.get("host", "")) not in allowed:
            return error_response(400, ErrorCode.FORBIDDEN, "Invalid Host header")
        return await call_next(request)

    return middleware


def request_guard(allowed_origins: Iterable[str]) -> Middleware:
    """Reject API calls that do not come from Traid's own page.

    1. A present `Origin` must be one of ours (covers cross-site fetch and form posts).
    2. State-changing requests must carry `X-Traid-Client: web`. Browsers send custom
       headers cross-origin only after a CORS preflight, which Traid never approves.
    """
    allowed = frozenset(allowed_origins)

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin is not None and origin not in allowed:
                return error_response(
                    403, ErrorCode.CSRF_FAILED, "Requests from other websites are not allowed"
                )
            if (
                request.method in STATE_CHANGING_METHODS
                and request.headers.get(CLIENT_HEADER) != CLIENT_HEADER_VALUE
            ):
                return error_response(403, ErrorCode.CSRF_FAILED, f"Missing {CLIENT_HEADER} header")
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
