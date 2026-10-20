"""FastAPI application factory.

One process serves the API under `/api/v1` and, when `frontend/dist` has been built,
the single-page app itself (ARCHITECTURE.md §1). Startup applies database migrations,
recovers interrupted tasks and starts the single background worker.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import __version__
from app.api.v1 import router as api_v1_router
from app.core.config import Environment, Settings, get_settings
from app.core.errors import NotFound, register_error_handlers
from app.core.http_security import LOCAL_HOSTS, TEST_CLIENT_HOST, host_guard, security_headers
from app.core.logging import access_log_middleware, configure_logging
from app.core.request_context import REQUEST_ID_HEADER, request_id_middleware
from app.db.engine import Database, run_migrations
from app.storage.filestore import FileStore
from app.worker.handlers import HANDLERS
from app.worker.runner import TaskRunner

VITE_DEV_ORIGIN = "http://localhost:5173"


def create_app(settings: Settings | None = None, *, start_worker: bool = True) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    docs_enabled = not settings.is_production

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database.from_settings(settings)
        run_migrations(db.engine)
        runner = TaskRunner(db, HANDLERS)
        runner.recover_interrupted()
        if start_worker:
            runner.start()
        app.state.settings = settings
        app.state.db = db
        app.state.file_store = FileStore(settings.data_dir / "files")
        app.state.task_runner = runner
        try:
            yield
        finally:
            runner.stop()
            db.dispose()

    app = FastAPI(
        title="Traid API",
        version=__version__,
        description="Style-matched token text replacement. Designed & developed by Xavier Sun.",
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    register_error_handlers(app)

    # Middleware runs outermost-last-added. Effective order for a request:
    # CORS (dev) → request ID → security headers → access log → host guard → route.
    allowed_hosts = set(LOCAL_HOSTS)
    if settings.env is Environment.TEST:
        allowed_hosts.add(TEST_CLIENT_HOST)
    app.middleware("http")(host_guard(allowed_hosts))
    app.middleware("http")(access_log_middleware)
    app.middleware("http")(security_headers(docs_enabled=docs_enabled))
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

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise NotFound("Endpoint not found")
        candidate = (root / path).resolve()
        # Path traversal guard: only files inside dist/ are served.
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)
