"""Audit event schema (API.md §2)."""

from typing import Any

from app.schemas.common import ApiModel, UtcTimestamp


class AuditEventOut(ApiModel):
    id: str
    user_id: str | None
    action: str
    subject_type: str | None
    subject_id: str | None
    details: dict[str, Any]
    created_at: UtcTimestamp
