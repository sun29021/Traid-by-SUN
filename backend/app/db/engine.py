"""SQLite engine, pragmas, session factory and migrations runner (ARCHITECTURE.md §6)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
DB_FILENAME = "traid.db"


def database_url(settings: Settings) -> str:
    return f"sqlite:///{(settings.data_dir / DB_FILENAME).as_posix()}"


def _apply_pragmas(dbapi_connection: Any, _: Any) -> None:
    if not isinstance(dbapi_connection, SQLiteConnection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def create_db_engine(url: str) -> Engine:
    # check_same_thread=False: the worker thread and request threads use their own sessions.
    engine = create_engine(url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _apply_pragmas)
    return engine


@dataclass(frozen=True)
class Database:
    engine: Engine
    session_factory: sessionmaker[Session]

    @classmethod
    def from_settings(cls, settings: Settings) -> Database:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        return cls.from_url(database_url(settings))

    @classmethod
    def from_url(cls, url: str) -> Database:
        engine = create_db_engine(url)
        return cls(engine=engine, session_factory=sessionmaker(engine, expire_on_commit=False))

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Session whose transaction commits on success and rolls back on error."""
        with self.session_factory() as session, session.begin():
            yield session

    def dispose(self) -> None:
        self.engine.dispose()


def alembic_config(engine: Engine) -> Config:
    config = Config()
    config.set_main_option("script_location", MIGRATIONS_DIR.as_posix())
    # env.py uses this engine directly (no URL option: Windows paths break ini interpolation).
    config.attributes["engine"] = engine
    return config


def run_migrations(engine: Engine, revision: str = "head") -> None:
    # The pre-migration backup runs before this at startup (services/backup_task.py).
    command.upgrade(alembic_config(engine), revision)
