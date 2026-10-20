"""The `backup` task and the startup hooks that protect the owner's data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.core.errors import AppError, ErrorCode
from app.db.engine import DB_FILENAME, Database, alembic_config
from app.services import app_settings, audit
from app.services import backup as backups
from app.services.audit import AuditAction
from app.services.system import schema_revision
from app.worker.runner import TaskContext

logger = logging.getLogger("traid.backup")


@dataclass(frozen=True)
class BackupDeps:
    db: Database
    data_dir: Path


def handle_backup(deps: BackupDeps, ctx: TaskContext) -> None:
    with deps.db.session() as session:
        retention = int(app_settings.get(session, "storage.backup_retention"))
        revision = schema_revision(session)
    ctx.report(0.1, "Copying the database and files")
    try:
        info = backups.create_backup(
            deps.data_dir, kind="manual", schema_revision=revision, retention=retention
        )
    except OSError as exc:
        raise AppError("The backup could not be written", code=ErrorCode.STORAGE_ERROR) from exc
    with deps.db.session() as session:
        audit.record(
            session,
            user_id=ctx.owner_id,
            action=AuditAction.BACKUP_CREATED,
            details={
                "name": info.name,
                "files": info.file_count,
                "integrity_ok": info.integrity_ok,
            },
        )
    if not info.integrity_ok:
        raise AppError("The backup failed its integrity check", code=ErrorCode.STORAGE_ERROR)
    ctx.report(1.0, f"Backup {info.name} created")


def pending_migration(db: Database) -> str | None:
    """The current revision when migrations are pending on an existing database, else None."""
    with db.engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current is None:
        return None  # brand-new database: nothing to protect
    head = ScriptDirectory.from_config(alembic_config(db.engine)).get_current_head()
    return current if current != head else None


def backup_before_migration(db: Database, data_dir: Path) -> Path | None:
    """DATABASE.md §9: a pre-migration backup, so a failed upgrade loses nothing."""
    if not (data_dir / DB_FILENAME).is_file():
        return None
    current = pending_migration(db)
    if current is None:
        return None
    info = backups.create_backup(data_dir, kind="pre-migrate", schema_revision=current)
    logger.info("Pre-migration backup created", extra={"backup": info.name})
    return backups.backups_dir(data_dir) / info.name
