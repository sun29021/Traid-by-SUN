"""Owner settings with defaults applied (DATABASE.md §3.12; the full API arrives in Phase 13)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AppSetting

DEFAULTS: dict[str, Any] = {
    "export.default_format": "original",
    "export.filename_pattern": "{template}_{token}",
    "export.metadata_marker": True,
    "export.jpeg_quality_mode": "match_source",
    "storage.backup_retention": 10,
}


def get(session: Session, key: str) -> Any:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = session.get(AppSetting, key)
    return DEFAULTS[key] if row is None else row.value


def all_settings(session: Session) -> dict[str, Any]:
    return {key: get(session, key) for key in DEFAULTS}
