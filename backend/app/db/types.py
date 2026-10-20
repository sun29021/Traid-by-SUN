"""Column types implementing DATABASE.md §2 conventions on SQLite.

- `UtcDateTime`: ISO-8601 UTC text with millisecond precision and a `Z` suffix.
- `JsonText`: JSON stored as TEXT (pair it with a `json_valid` CHECK constraint).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.clock import isoformat_utc


def new_id() -> str:
    return str(uuid.uuid4())


class UtcDateTime(TypeDecorator[datetime]):
    impl = String(24)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        return None if value is None else isoformat_utc(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


class JsonText(TypeDecorator[Any]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def process_result_value(self, value: str | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        return json.loads(value)
