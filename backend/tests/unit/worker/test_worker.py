import time
from collections.abc import Callable

import pytest

from app.core.errors import AppError, ErrorCode, TooManyRequests, ValidationFailed
from app.db.engine import Database
from app.db.models import Task
from app.db.models.enums import TaskStatus, TaskSubject, TaskType
from app.repositories import tasks as tasks_repo
from app.worker import queue
from app.worker.runner import Handler, TaskContext, TaskRunner
from tests.factories import make_user


def _enqueue(db: Database, owner_id: str, task_type: TaskType = TaskType.DETECT) -> str:
    with db.session_factory() as session:
        task = queue.enqueue(
            session,
            owner_id=owner_id,
            task_type=task_type,
            subject_type=TaskSubject.SYSTEM,
            subject_id=None,
            payload={"n": 1},
        )
        return task.id


def _task(db: Database, task_id: str) -> Task:
    with db.session_factory() as session:
        task = tasks_repo.get_unscoped(session, task_id)
        assert task is not None
        return task


def _runner(db: Database, handler: Handler) -> TaskRunner:
    return TaskRunner(db, {TaskType.DETECT: handler}, poll_interval=0.01)


def test_runs_tasks_oldest_first_and_records_success(db: Database, owner_id: str) -> None:
    seen: list[str] = []
    first, second = _enqueue(db, owner_id), _enqueue(db, owner_id)
    runner = _runner(db, lambda ctx: seen.append(ctx.task_id))

    assert runner.run_once() and runner.run_once()
    assert runner.run_once() is False

    assert seen == [first, second]
    task = _task(db, first)
    assert task.status == TaskStatus.SUCCEEDED
    assert task.progress == 1.0
    assert task.started_at is not None and task.finished_at is not None


def test_handler_receives_payload_and_reports_progress(db: Database, owner_id: str) -> None:
    task_id = _enqueue(db, owner_id)
    progress: list[float] = []

    def handler(ctx: TaskContext) -> None:
        assert ctx.payload == {"n": 1} and ctx.owner_id == owner_id
        ctx.report(0.5, "Halfway")
        progress.append(_task(db, task_id).progress)

    _runner(db, handler).run_once()

    assert progress == [0.5]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ValidationFailed("No text", code=ErrorCode.NO_TEXT_FOUND), ErrorCode.NO_TEXT_FOUND),
        (RuntimeError("boom"), ErrorCode.INTERNAL_ERROR),
        (MemoryError(), ErrorCode.OUT_OF_MEMORY),
    ],
)
def test_failures_are_recorded_with_error_codes(
    db: Database, owner_id: str, error: BaseException, code: ErrorCode
) -> None:
    task_id = _enqueue(db, owner_id)

    def handler(_: TaskContext) -> None:
        raise error

    _runner(db, handler).run_once()

    task = _task(db, task_id)
    assert (task.status, task.error_code) == (TaskStatus.FAILED, code)


def test_missing_handler_fails_the_task(db: Database, owner_id: str) -> None:
    task_id = _enqueue(db, owner_id, TaskType.RENDER)

    _runner(db, lambda _: None).run_once()

    assert _task(db, task_id).error_code == ErrorCode.INTERNAL_ERROR


def test_cancel_queued_task_never_runs(db: Database, owner_id: str) -> None:
    task_id = _enqueue(db, owner_id)
    with db.session_factory() as session:
        queue.request_cancel(session, owner_id, task_id)

    assert _runner(db, lambda _: pytest.fail("must not run")).run_once() is False
    assert _task(db, task_id).status == TaskStatus.CANCELLED


def test_running_task_stops_at_next_checkpoint(db: Database, owner_id: str) -> None:
    task_id = _enqueue(db, owner_id)
    reached_end: list[bool] = []

    def handler(ctx: TaskContext) -> None:
        with db.session_factory() as session:
            queue.request_cancel(session, owner_id, ctx.task_id)
        ctx.report(0.3, "Working")  # checkpoint raises TaskCancelled
        reached_end.append(True)

    _runner(db, handler).run_once()

    task = _task(db, task_id)
    assert (task.status, task.error_code) == (TaskStatus.CANCELLED, ErrorCode.TASK_CANCELLED)
    assert reached_end == []


def test_interrupted_tasks_are_failed_on_startup(db: Database, owner_id: str) -> None:
    task_id = _enqueue(db, owner_id)
    with db.session() as session:
        task = tasks_repo.get_unscoped(session, task_id)
        assert task is not None
        task.status = TaskStatus.RUNNING.value

    assert _runner(db, lambda _: None).recover_interrupted() == 1
    assert _task(db, task_id).error_code == ErrorCode.TASK_INTERRUPTED


def test_retry_only_failed_tasks(db: Database, owner_id: str) -> None:
    task_id = _enqueue(db, owner_id)

    def fail(_: TaskContext) -> None:
        raise AppError("nope")

    _runner(db, fail).run_once()

    with db.session_factory() as session:
        retried = queue.retry(session, owner_id, task_id)
        assert retried.id != task_id and retried.status == TaskStatus.QUEUED
        assert retried.payload == {"n": 1}
        with pytest.raises(AppError) as caught:
            queue.retry(session, owner_id, retried.id)
    assert caught.value.code is ErrorCode.INVALID_STATE


def test_tasks_are_owner_scoped(db: Database, owner_id: str) -> None:
    task_id = _enqueue(db, owner_id)
    stranger = make_user(db, "stranger")

    with db.session_factory() as session, pytest.raises(AppError) as caught:
        queue.request_cancel(session, stranger, task_id)
    assert caught.value.http_status == 404


def test_queue_limit(db: Database, owner_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(queue, "MAX_QUEUED_PER_USER", 2)
    _enqueue(db, owner_id)
    _enqueue(db, owner_id)

    with pytest.raises(TooManyRequests):
        _enqueue(db, owner_id)


def test_background_thread_processes_tasks(db: Database, owner_id: str) -> None:
    done: list[str] = []
    runner = _runner(db, lambda ctx: done.append(ctx.task_id))
    runner.start()
    try:
        task_id = _enqueue(db, owner_id)
        _wait_for(lambda: _task(db, task_id).status == TaskStatus.SUCCEEDED)
    finally:
        runner.stop()

    assert done == [task_id]


def _wait_for(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    pytest.fail("condition not met in time")
