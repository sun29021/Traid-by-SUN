"""`tasks` table — the persisted background queue (DATABASE.md §3.10)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, id_column
from app.db.models.enums import TaskStatus, TaskSubject, TaskType, check_in
from app.db.types import JsonText, UtcDateTime


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(check_in("type", TaskType), name="type"),
        CheckConstraint(check_in("subject_type", TaskSubject), name="subject_type"),
        CheckConstraint(check_in("status", TaskStatus), name="status"),
        CheckConstraint("progress BETWEEN 0 AND 1", name="progress"),
        CheckConstraint("cancel_requested IN (0, 1)", name="cancel_requested"),
        CheckConstraint("json_valid(payload)", name="payload_json"),
        Index("ix_tasks_status_created_at", "status", "created_at"),
        Index("ix_tasks_subject_type_subject_id_status", "subject_type", "subject_id", "status"),
    )

    id: Mapped[str] = id_column()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(32))
    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str | None] = mapped_column(String(36))
    payload: Mapped[dict[str, Any]] = mapped_column(JsonText(), default=dict)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.QUEUED.value)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(String(200))
    cancel_requested: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_column()
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
