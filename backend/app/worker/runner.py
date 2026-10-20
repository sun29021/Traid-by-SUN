"""Single background thread that executes queued tasks in order (ARCHITECTURE.md §3.4).

One worker keeps CPU/GPU use and memory predictable. Handlers receive a `TaskContext`
for progress reporting and cooperative cancellation; they never touch the HTTP layer.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.core.clock import utcnow
from app.core.errors import AppError, ErrorCode
from app.db.engine import Database
from app.db.models.enums import TaskStatus, TaskType
from app.repositories import tasks as tasks_repo

logger = logging.getLogger("traid.worker")

DEFAULT_POLL_INTERVAL_S = 0.25
MAX_MESSAGE_LENGTH = 200


class TaskCancelled(Exception):
    """Raised inside a handler when the owner asked to cancel the running task."""


@dataclass(frozen=True)
class TaskContext:
    task_id: str
    owner_id: str
    type: TaskType
    subject_type: str
    subject_id: str | None
    payload: dict[str, Any]
    _db: Database = field(repr=False)

    def report(self, progress: float, message: str | None = None) -> None:
        """Persist progress (0 to 1) and a stage label; also a cancellation checkpoint."""
        with self._db.session() as session:
            task = tasks_repo.get_unscoped(session, self.task_id)
            if task is None:
                raise TaskCancelled
            task.progress = min(max(progress, 0.0), 1.0)
            task.message = message[:MAX_MESSAGE_LENGTH] if message else None
            cancel = bool(task.cancel_requested)
        if cancel:
            raise TaskCancelled

    def check_cancelled(self) -> None:
        with self._db.session() as session:
            task = tasks_repo.get_unscoped(session, self.task_id)
            if task is None or task.cancel_requested:
                raise TaskCancelled


Handler = Callable[[TaskContext], None]


class TaskRunner:
    def __init__(
        self,
        db: Database,
        handlers: Mapping[TaskType, Handler],
        poll_interval: float = DEFAULT_POLL_INTERVAL_S,
    ) -> None:
        self._db = db
        self._handlers = dict(handlers)
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ lifecycle

    def recover_interrupted(self) -> int:
        """Tasks left `running` by a crash or shutdown become `failed` (retryable)."""
        with self._db.session() as session:
            count = tasks_repo.fail_running(session, ErrorCode.TASK_INTERRUPTED.value, utcnow())
        if count:
            logger.warning("Marked interrupted tasks as failed", extra={"count": count})
        return count

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="traid-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.exception("Worker loop error")
                worked = False
            if not worked:
                self._stop.wait(self._poll_interval)

    # ------------------------------------------------------------ execution

    def run_once(self) -> bool:
        """Claim and run the oldest queued task. Returns False when the queue is empty.

        Tests call this directly to run tasks synchronously.
        """
        context = self._claim()
        if context is None:
            return False

        status, error_code, message = TaskStatus.SUCCEEDED, None, None
        try:
            handler = self._handlers.get(context.type)
            if handler is None:
                raise AppError(f"No handler registered for task type '{context.type}'")
            handler(context)
        except TaskCancelled:
            status, error_code = TaskStatus.CANCELLED, ErrorCode.TASK_CANCELLED
        except AppError as exc:
            status, error_code, message = TaskStatus.FAILED, exc.code, exc.message
        except MemoryError:
            status, error_code = TaskStatus.FAILED, ErrorCode.OUT_OF_MEMORY
            message = "Ran out of memory"
        except Exception:
            logger.exception("Task failed", extra={"task_id": context.task_id})
            status, error_code = TaskStatus.FAILED, ErrorCode.INTERNAL_ERROR
            message = "Unexpected error; see logs"

        self._finish(context.task_id, status, error_code, message)
        return True

    def _claim(self) -> TaskContext | None:
        with self._db.session() as session:
            task_id = tasks_repo.oldest_queued_id(session)
            if task_id is None or not tasks_repo.mark_running(session, task_id, utcnow()):
                return None
            task = tasks_repo.get_unscoped(session, task_id)
            assert task is not None  # noqa: S101 — just claimed inside this transaction
            return TaskContext(
                task_id=task.id,
                owner_id=task.owner_id,
                type=TaskType(task.type),
                subject_type=task.subject_type,
                subject_id=task.subject_id,
                payload=dict(task.payload),
                _db=self._db,
            )

    def _finish(
        self,
        task_id: str,
        status: TaskStatus,
        error_code: ErrorCode | None,
        message: str | None,
    ) -> None:
        with self._db.session() as session:
            task = tasks_repo.get_unscoped(session, task_id)
            if task is None:
                return
            task.status = status.value
            task.error_code = error_code.value if error_code else None
            if status is TaskStatus.SUCCEEDED:
                task.progress = 1.0
            if message is not None:
                task.message = message[:MAX_MESSAGE_LENGTH]
            task.finished_at = utcnow()
        logger.info(
            "Task finished",
            extra={
                "task_id": task_id,
                "status": status.value,
                "error_code": error_code.value if error_code else None,
            },
        )
