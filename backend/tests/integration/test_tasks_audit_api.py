"""Task and audit endpoints on top of the Phase 1 queue."""

import re

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.db.engine import Database
from app.db.models.enums import TaskStatus, TaskSubject, TaskType
from app.worker import queue
from app.worker.runner import TaskContext, TaskRunner

ISO_MS_Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")


def _app_db(client: TestClient) -> Database:
    db: Database = client.app.state.db  # type: ignore[attr-defined]
    return db


def _owner(client: TestClient) -> str:
    owner_id: str = client.app.state.owner_id  # type: ignore[attr-defined]
    return owner_id


def _enqueue(client: TestClient, n: int = 1) -> list[str]:
    db = _app_db(client)
    ids = []
    with db.session_factory() as session:
        for i in range(n):
            task = queue.enqueue(
                session,
                owner_id=_owner(client),
                task_type=TaskType.DETECT,
                subject_type=TaskSubject.SYSTEM,
                subject_id=None,
                payload={"i": i},
            )
            ids.append(task.id)
    return ids


def _run_failing(client: TestClient) -> None:
    def fail(_: TaskContext) -> None:
        raise AppError("boom")

    TaskRunner(_app_db(client), {TaskType.DETECT: fail}).run_once()


def test_get_task_shape(accepted_client: TestClient) -> None:
    (task_id,) = _enqueue(accepted_client)

    data = accepted_client.get(f"/api/v1/tasks/{task_id}").json()["data"]

    assert set(data) == {
        "id", "type", "subject_type", "subject_id", "status", "progress", "message",
        "error_code", "created_at", "started_at", "finished_at",
    }  # fmt: skip
    assert (data["status"], data["type"], data["progress"]) == ("queued", "detect", 0.0)
    assert ISO_MS_Z.match(data["created_at"])
    assert "payload" not in data and "owner_id" not in data


def test_unknown_task_is_404(accepted_client: TestClient) -> None:
    response = accepted_client.get("/api/v1/tasks/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_list_defaults_to_active_and_paginates(accepted_client: TestClient) -> None:
    ids = _enqueue(accepted_client, 3)

    first = accepted_client.get("/api/v1/tasks", params={"limit": 2}).json()
    second = accepted_client.get(
        "/api/v1/tasks", params={"limit": 2, "cursor": first["meta"]["next_cursor"]}
    ).json()

    listed = [t["id"] for t in first["data"]] + [t["id"] for t in second["data"]]
    assert sorted(listed) == sorted(ids)
    assert first["meta"]["count"] == 2
    assert second["meta"] == {"next_cursor": None, "count": 1}


def test_list_filters_by_status(accepted_client: TestClient) -> None:
    _enqueue(accepted_client, 2)
    _run_failing(accepted_client)

    failed = accepted_client.get("/api/v1/tasks", params={"status": "failed"}).json()["data"]
    active = accepted_client.get("/api/v1/tasks").json()["data"]

    assert [t["status"] for t in failed] == ["failed"]
    assert [t["status"] for t in active] == ["queued"]


@pytest.mark.parametrize(
    "params",
    [{"status": "bogus"}, {"limit": 0}, {"limit": 101}, {"cursor": "not-a-cursor"}, {"page": 2}],
)
def test_list_rejects_bad_query(accepted_client: TestClient, params: dict[str, object]) -> None:
    response = accepted_client.get("/api/v1/tasks", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_cancel_queued_task(accepted_client: TestClient) -> None:
    (task_id,) = _enqueue(accepted_client)

    data = accepted_client.post(f"/api/v1/tasks/{task_id}/cancel").json()["data"]

    assert (data["status"], data["error_code"]) == ("cancelled", "TASK_CANCELLED")


def test_retry_failed_task_creates_a_new_task(accepted_client: TestClient) -> None:
    (task_id,) = _enqueue(accepted_client)
    _run_failing(accepted_client)

    response = accepted_client.post(f"/api/v1/tasks/{task_id}/retry")

    assert response.status_code == 202
    data = response.json()["data"]
    assert data["id"] != task_id and data["status"] == TaskStatus.QUEUED


def test_retry_non_failed_task_is_409(accepted_client: TestClient) -> None:
    (task_id,) = _enqueue(accepted_client)

    response = accepted_client.post(f"/api/v1/tasks/{task_id}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_audit_log_lists_and_filters(accepted_client: TestClient) -> None:
    body = accepted_client.get("/api/v1/audit").json()

    assert [e["action"] for e in body["data"]] == ["system.aup_accepted"]
    assert body["data"][0]["subject_type"] == "user"

    none = accepted_client.get("/api/v1/audit", params={"action": "job.exported"}).json()
    assert none["data"] == []

    future = accepted_client.get("/api/v1/audit", params={"from": "2999-01-01T00:00:00Z"}).json()
    assert future["data"] == []


@pytest.mark.parametrize(
    "params",
    [{"action": "made.up"}, {"from": "2026-10-20T00:00:00"}, {"from": "yesterday"}, {"x": "1"}],
)
def test_audit_rejects_bad_query(accepted_client: TestClient, params: dict[str, str]) -> None:
    assert accepted_client.get("/api/v1/audit", params=params).status_code == 422
