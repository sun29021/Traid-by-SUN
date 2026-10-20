"""Alembic environment.

Used both programmatically (`app.db.engine.run_migrations`, which passes the engine in
`config.attributes`) and from the CLI (`alembic upgrade head` in `backend/`), where the
database URL comes from Traid settings. Logging is left to Traid's own configuration.
"""

from alembic import context
from sqlalchemy import Engine

import app.db.models  # noqa: F401 — registers all tables on Base.metadata
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import Database

target_metadata = Base.metadata


def _engine() -> Engine:
    engine = context.config.attributes.get("engine")
    if isinstance(engine, Engine):
        return engine
    return Database.from_settings(get_settings()).engine


def run_migrations_online() -> None:
    with _engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite cannot ALTER most constraints in place
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) migrations are not supported for Traid.")
run_migrations_online()
