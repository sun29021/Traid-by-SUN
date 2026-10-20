"""Command-line backup (used by scripts/backup.ps1): `python -m app.backup_cli`.

Works whether or not Traid is running (SQLite online backup). Prints the backup path
and exits non-zero when the integrity check fails.
"""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.db.engine import Database
from app.services import app_settings
from app.services import backup as backups
from app.services.system import schema_revision


def main() -> int:
    settings = get_settings()
    db = Database.from_settings(settings)
    try:
        with db.session() as session:
            retention = int(app_settings.get(session, "storage.backup_retention"))
            revision = schema_revision(session)
    except Exception:  # no database yet: back up the files only
        retention, revision = 10, None
    finally:
        db.dispose()
    info = backups.create_backup(
        settings.data_dir, kind="manual", schema_revision=revision, retention=retention
    )
    path = backups.backups_dir(settings.data_dir) / info.name
    integrity = "ok" if info.integrity_ok else "FAILED"
    print(f"Backup written: {path} ({info.file_count} files, integrity {integrity})")
    return 0 if info.integrity_ok else 1


if __name__ == "__main__":
    sys.exit(main())
