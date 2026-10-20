"""Keyset pagination helpers for `created_at DESC, id DESC` lists."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, TypeVar

from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.orm import InstrumentedAttribute

from app.core.pagination import Cursor, encode_cursor


class _Row(Protocol):
    @property
    def created_at(self) -> datetime: ...

    @property
    def id(self) -> str: ...


RowT = TypeVar("RowT", bound=_Row)


def before(
    created_at: InstrumentedAttribute[datetime],
    row_id: InstrumentedAttribute[str],
    cursor: Cursor,
) -> ColumnElement[bool]:
    """Rows that come after `cursor` in descending order."""
    return or_(
        created_at < cursor.created_at,
        and_(created_at == cursor.created_at, row_id < cursor.id),
    )


def split_page(rows: Sequence[RowT], limit: int) -> tuple[list[RowT], str | None]:
    """Rows were fetched with `limit + 1`; return the page and the next cursor."""
    page = list(rows[:limit])
    if len(rows) <= limit or not page:
        return page, None
    last = page[-1]
    return page, encode_cursor(last.created_at, last.id)
