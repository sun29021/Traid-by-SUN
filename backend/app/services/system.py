"""System status for Settings → Engine / Storage (API.md §3.1)."""

from __future__ import annotations

import shutil

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import Settings
from app.repositories import files as files_repo
from app.repositories import tasks as tasks_repo
from app.schemas.system import (
    EngineStatus,
    StorageStatus,
    SystemStatus,
    WorkerStatus,
)


def schema_revision(session: Session) -> str | None:
    try:
        return session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except OperationalError:
        return None


def get_status(
    session: Session, settings: Settings, *, owner_id: str, worker_running: bool
) -> SystemStatus:
    disk = shutil.disk_usage(settings.data_dir)
    return SystemStatus(
        version=__version__,
        schema_revision=schema_revision(session),
        worker=WorkerStatus(
            running=worker_running, queued=tasks_repo.count_queued(session, owner_id)
        ),
        storage=StorageStatus(
            data_dir=str(settings.data_dir),
            stored_bytes=files_repo.total_bytes(session, owner_id),
            disk_free_bytes=disk.free,
            disk_total_bytes=disk.total,
        ),
        # Models and device detection arrive in Phase 4 (task 4.3).
        engine=EngineStatus(ready=False, device=None, models=[]),
    )
