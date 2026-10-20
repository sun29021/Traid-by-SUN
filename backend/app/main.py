"""FastAPI application factory.

One process serves the API under `/api/v1` and, when `frontend/dist` has been built,
the single-page app itself (ARCHITECTURE.md §1).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import __version__
from app.api.v1 import router as api_v1_router
from app.core.config import Settings, get_settings
from app.core.errors import NotFound, register_error_handlers
from app.core.logging import access_log_middleware, configure_logging
from app.core.request_context import REQUEST_ID_HEADER, request_id_middleware

VITE_DEV_ORIGIN = "http://localhost:5173"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="Traid API",
        version=__version__,
        description="Style-matched token text replacement. Designed & developed by Xavier Sun.",
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )

    register_error_handlers(app)
    # Order matters: the request-ID middleware must wrap the access log so log lines carry the ID.
    app.middleware("http")(access_log_middleware)
    app.middleware("http")(request_id_middleware)

    if not settings.is_production:
        # Vite proxies /api in development; this also allows direct calls from its origin.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[VITE_DEV_ORIGIN],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-Traid-CSRF"],
            expose_headers=[REQUEST_ID_HEADER],
        )

    app.include_router(api_v1_router)

    if settings.frontend_dist_dir.is_dir():
        _mount_spa(app, settings.frontend_dist_dir)

    return app


def _mount_spa(app: FastAPI, dist_dir: Path) -> None:
    """Serve built frontend files, falling back to index.html for client-side routes."""
    root = dist_dir.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise NotFound("Endpoint not found")
        candidate = (root / path).resolve()
        # Path traversal guard: only files inside dist/ are served.
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)
