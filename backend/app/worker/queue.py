"""Task queue operations used by services (enqueue, cancel, retry) — ARCHITECTURE.md §3.4."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import Conflict, ErrorCode, NotFound, TooManyRequests
from app.db.models import Task
from app.db.models.enums import TaskStatus, TaskSubject, TaskType
from app.db.transaction import transaction
from app.repositories import tasks as tasks_repo

MAX_QUEUED_PER_USER = 200  # API.md §6


def enqueue(
    session: Session,
    *,
    owner_id: str,
    task_type: TaskType,
    subject_type: TaskSubject,
    subject_id: str | None,
    payload: dict[str, Any] | None = None,
) -> Task:
    with transaction(session):
        if tasks_repo.count_queued(session, owner_id) >= MAX_QUEUED_PER_USER:
            raise TooManyRequests("Too many queued tasks; wait for some to finish")
        return tasks_repo.add(
            session,
            Task(
                owner_id=owner_id,
                type=task_type.value,
                subject_type=subject_type.value,
                subject_id=subject_id,
                payload=payload or {},
                status=TaskStatus.QUEUED.value,
                progress=0.0,
                cancel_requested=0,
            ),
        )


def get_task(session: Session, owner_id: str, task_id: str) -> Task:
    task = tasks_repo.get(session, owner_id, task_id)
    if task is None:
        raise NotFound("Task not found")
    return task


def request_cancel(session: Session, owner_id: str, task_id: str) -> Task:
    """Cancel a queued task now; ask a running task to stop at its next checkpoint."""
    with transaction(session):
        task = get_task(session, owner_id, task_id)
        if task.status == TaskStatus.QUEUED.value:
            task.status = TaskStatus.CANCELLED.value
            task.error_code = ErrorCode.TASK_CANCELLED.value
            task.finished_at = utcnow()
        elif task.status == TaskStatus.RUNNING.value:
            task.cancel_requested = 1
        return task  # finished tasks: idempotent no-op


def retry(session: Session, owner_id: str, task_id: str) -> Task:
    """Re-enqueue a failed task with the same payload as a new task."""
    with transaction(session):
        task = get_task(session, owner_id, task_id)
        if task.status != TaskStatus.FAILED.value:
            raise Conflict("Only failed tasks can be retried", code=ErrorCode.INVALID_STATE)
        return enqueue(
            session,
            owner_id=owner_id,
            task_type=TaskType(task.type),
            subject_type=TaskSubject(task.subject_type),
            subject_id=task.subject_id,
            payload=dict(task.payload),
        )
