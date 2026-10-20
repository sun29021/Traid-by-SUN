"""`audit_events` table — append-only (DATABASE.md §3.11).

UPDATE/DELETE are blocked by triggers created in the migration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, id_column
from app.db.types import JsonText


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("json_valid(details)", name="details_json"),
        Index("ix_audit_events_created_at", "created_at"),
    )

    id: Mapped[str] = id_column()
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64))
    subject_type: Mapped[str | None] = mapped_column(String(32))
    subject_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict[str, Any]] = mapped_column(JsonText(), default=dict)
    created_at: Mapped[datetime] = created_at_column()
