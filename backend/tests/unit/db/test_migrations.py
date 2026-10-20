import sqlite3
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.core.config import Settings
from app.db.base import Base
from app.db.engine import DB_FILENAME, Database, alembic_config, run_migrations

EXPECTED_TABLES = {"users", "sessions", "audit_events", "app_settings", "files", "tasks"}


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as con:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return {row[0] for row in rows} - {"alembic_version"}


def test_upgrade_downgrade_upgrade(settings: Settings) -> None:
    db = Database.from_settings(settings)
    path = settings.data_dir / DB_FILENAME
    try:
        run_migrations(db.engine)
        assert _tables(path) == EXPECTED_TABLES

        command.downgrade(alembic_config(db.engine), "base")
        assert _tables(path) == set()

        run_migrations(db.engine)
        assert _tables(path) == EXPECTED_TABLES
    finally:
        db.dispose()


def test_models_match_migrations(db: Database) -> None:
    """ORM models and migrations must not drift (AGENTS.md §9)."""
    with db.engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


def test_pragmas_are_applied(db: Database) -> None:
    with db.engine.connect() as connection:
        raw = connection.connection.dbapi_connection
        assert raw is not None
        assert raw.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert raw.execute("PRAGMA journal_mode").fetchone() == ("wal",)
