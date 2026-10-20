"""Data access for `audit_events` (append-only)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pagination import Cursor
from app.db.models import AuditEvent
from app.repositories.pagination import before


def add(session: Session, event: AuditEvent) -> AuditEvent:
    session.add(event)
    session.flush()
    return event


def list_events(
    session: Session,
    *,
    actions: Sequence[str] | None,
    created_from: datetime | None,
    created_to: datetime | None,
    cursor: Cursor | None,
    limit: int,
) -> Sequence[AuditEvent]:
    """Newest first; fetches `limit + 1` rows so the caller can tell if more exist."""
    query = select(AuditEvent)
    if actions:
        query = query.where(AuditEvent.action.in_(actions))
    if created_from is not None:
        query = query.where(AuditEvent.created_at >= created_from)
    if created_to is not None:
        query = query.where(AuditEvent.created_at <= created_to)
    if cursor is not None:
        query = query.where(before(AuditEvent.created_at, AuditEvent.id, cursor))
    query = query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
    return session.scalars(query).all()
