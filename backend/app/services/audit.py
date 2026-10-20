"""Audit log: append-only record of security- and output-relevant actions (PRD FR-U05)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.core.pagination import decode_cursor
from app.db.models import AuditEvent
from app.repositories import audit as audit_repo
from app.repositories.pagination import split_page


class AuditAction(StrEnum):
    """Closed list (DATABASE.md §3.11). auth.* actions belong to the deferred sign-in."""

    AUP_ACCEPTED = "system.aup_accepted"
    AUTH_SETUP = "auth.setup"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_LOGOUT = "auth.logout"
    AUTH_PASSWORD_CHANGED = "auth.password_changed"  # noqa: S105 — action name, not a secret
    PROFILE_CREATED = "profile.created"
    PROFILE_ARCHIVED = "profile.archived"
    PROFILE_DELETED = "profile.deleted"
    JOB_ACCEPTED = "job.accepted"
    JOB_REJECTED = "job.rejected"
    JOB_EXPORTED = "job.exported"
    JOB_DELETED = "job.deleted"
    BATCH_EXPORTED = "batch.exported"
    SETTINGS_UPDATED = "settings.updated"
    BACKUP_CREATED = "backup.created"


# Audit details must never contain secrets (DATABASE.md §8).
_FORBIDDEN_DETAIL_WORDS = ("password", "token", "secret", "csrf")


def record(
    session: Session,
    *,
    user_id: str | None,
    action: AuditAction,
    subject: tuple[str, str] | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one audit event inside the caller's transaction."""
    details = details or {}
    for key in details:
        if any(word in key.lower() for word in _FORBIDDEN_DETAIL_WORDS):
            raise ValueError(f"Audit details must not contain sensitive key '{key}'")
    subject_type, subject_id = subject if subject else (None, None)
    return audit_repo.add(
        session,
        AuditEvent(
            user_id=user_id,
            action=action.value,
            subject_type=subject_type,
            subject_id=subject_id,
            details=details,
        ),
    )


@dataclass(frozen=True)
class AuditPage:
    events: list[AuditEvent]
    next_cursor: str | None


def list_events(
    session: Session,
    *,
    actions: Sequence[AuditAction] | None,
    created_from: datetime | None,
    created_to: datetime | None,
    cursor: str | None,
    limit: int,
    subject_id: str | None = None,
) -> AuditPage:
    rows = audit_repo.list_events(
        session,
        actions=[action.value for action in actions] if actions else None,
        created_from=created_from,
        created_to=created_to,
        cursor=decode_cursor(cursor) if cursor else None,
        limit=limit,
        subject_id=subject_id,
    )
    events, next_cursor = split_page(rows, limit)
    return AuditPage(events, next_cursor)
