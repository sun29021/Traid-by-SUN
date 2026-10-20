"""Owner settings with defaults applied (DATABASE.md §3.12, API.md §3.10)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.db.models import AppSetting
from app.db.transaction import transaction
from app.services import audit
from app.services.audit import AuditAction

DEFAULTS: dict[str, Any] = {
    "export.default_format": "original",
    "export.filename_pattern": "{template}_{token}",
    "export.metadata_marker": True,
    "export.jpeg_quality_mode": "match_source",
    "storage.backup_retention": 10,
    "export.default_author": "",
    "export.default_copyright": "",
}

_PATTERN = re.compile(r"^[A-Za-z0-9_{}.\-]{1,120}$")
_TOKENS = re.compile(r"\{(\w+)\}")
_QUALITY = re.compile(r"^(match_source|fixed:(\d{2,3}))$")


def get(session: Session, key: str) -> Any:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = session.get(AppSetting, key)
    return DEFAULTS[key] if row is None else row.value


def all_settings(session: Session) -> dict[str, Any]:
    return {key: get(session, key) for key in DEFAULTS}


def _validate(key: str, value: Any) -> Any:
    if key not in DEFAULTS:
        raise ValidationFailed("Unknown setting", details={"key": key})
    if key == "export.default_format":
        if value not in ("original", "jpeg", "png", "tiff"):
            raise ValidationFailed("Choose original, jpeg, png or tiff", details={"key": key})
    elif key == "export.filename_pattern":
        if not isinstance(value, str) or not _PATTERN.fullmatch(value):
            raise ValidationFailed(
                "Use up to 120 letters, digits, _ . - and {tokens}", details={"key": key}
            )
        unknown = set(_TOKENS.findall(value)) - {"template", "token", "date", "n"}
        if unknown:
            raise ValidationFailed(
                "Unknown token in the pattern: {" + sorted(unknown)[0] + "}", details={"key": key}
            )
    elif key in ("export.default_author", "export.default_copyright"):
        if not isinstance(value, str) or len(value) > 300 or not value.isprintable():
            raise ValidationFailed("Use up to 300 printable characters", details={"key": key})
    elif key == "export.metadata_marker":
        if not isinstance(value, bool):
            raise ValidationFailed("Must be true or false", details={"key": key})
    elif key == "export.jpeg_quality_mode":
        match = _QUALITY.fullmatch(value) if isinstance(value, str) else None
        if match is None or (match.group(2) and not 60 <= int(match.group(2)) <= 100):
            raise ValidationFailed("Use match_source or fixed:60 … fixed:100", details={"key": key})
    elif key == "storage.backup_retention" and (
        isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 50
    ):
        raise ValidationFailed("Keep between 1 and 50 backups", details={"key": key})
    return value


def update(session: Session, owner_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Validate everything first, then store and audit in one transaction."""
    clean = {key: _validate(key, value) for key, value in changes.items()}
    with transaction(session):
        for key, value in clean.items():
            row = session.get(AppSetting, key)
            if row is None:
                session.add(AppSetting(key=key, value=value, updated_by=owner_id))
            else:
                row.value = value
                row.updated_by = owner_id
        if clean:
            audit.record(
                session,
                user_id=owner_id,
                action=AuditAction.SETTINGS_UPDATED,
                details={"keys": sorted(clean)},
            )
    return all_settings(session)
