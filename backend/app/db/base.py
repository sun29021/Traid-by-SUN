"""Declarative base with a constraint naming convention (needed for Alembic batch mode)."""

from datetime import datetime

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.clock import utcnow
from app.db.types import UtcDateTime, new_id

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def id_column() -> Mapped[str]:
    return mapped_column(primary_key=True, default=new_id)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(UtcDateTime(), default=utcnow)


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)
