"""Data access for `tasks`. Owner-scoped reads; worker-only claim/finish helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import Task
from app.db.models.enums import TaskStatus

ACTIVE = (TaskStatus.QUEUED.value, TaskStatus.RUNNING.value)


def get(session: Session, owner_id: str, task_id: str) -> Task | None:
    return session.scalar(select(Task).where(Task.id == task_id, Task.owner_id == owner_id))


def list_active(session: Session, owner_id: str) -> Sequence[Task]:
    return session.scalars(
        select(Task)
        .where(Task.owner_id == owner_id, Task.status.in_(ACTIVE))
        .order_by(Task.created_at, Task.id)
    ).all()


def count_queued(session: Session, owner_id: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.owner_id == owner_id, Task.status == TaskStatus.QUEUED.value)
        )
        or 0
    )


def add(session: Session, task: Task) -> Task:
    session.add(task)
    session.flush()
    return task


# ---------------------------------------------------------------- worker-only (not owner-scoped)


def oldest_queued_id(session: Session) -> str | None:
    return session.scalar(
        select(Task.id)
        .where(Task.status == TaskStatus.QUEUED.value)
        .order_by(Task.created_at, Task.id)
        .limit(1)
    )


def mark_running(session: Session, task_id: str, now: datetime) -> bool:
    """Atomically move one task from queued to running. False if someone else got it."""
    result = session.execute(
        update(Task)
        .where(Task.id == task_id, Task.status == TaskStatus.QUEUED.value)
        .values(status=TaskStatus.RUNNING.value, started_at=now)
    )
    return bool(getattr(result, "rowcount", 0) == 1)


def get_unscoped(session: Session, task_id: str) -> Task | None:
    return session.get(Task, task_id)


def fail_running(session: Session, error_code: str, now: datetime) -> int:
    """Mark every running task as failed (used at startup after a crash)."""
    result = session.execute(
        update(Task)
        .where(Task.status == TaskStatus.RUNNING.value)
        .values(status=TaskStatus.FAILED.value, error_code=error_code, finished_at=now)
    )
    return int(getattr(result, "rowcount", 0))
