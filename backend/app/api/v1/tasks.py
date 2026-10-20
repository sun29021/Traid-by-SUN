"""Background task status, cancel and retry (API.md §3.8)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import AcceptedUserDep, SessionDep, allowed_query_params, parse_csv_enum
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.db.models.enums import TaskStatus
from app.schemas.common import DataEnvelope, ListEnvelope, ListMeta
from app.schemas.tasks import TaskOut
from app.worker import queue

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get(
    "",
    response_model=ListEnvelope[TaskOut],
    dependencies=[Depends(allowed_query_params("status", "cursor", "limit"))],
)
def list_tasks(
    user: AcceptedUserDep,
    session: SessionDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> ListEnvelope[TaskOut]:
    """Newest first. Without `status`, returns active (queued and running) tasks."""
    tasks, next_cursor = queue.list_tasks(
        session,
        user.id,
        statuses=parse_csv_enum(status_filter, TaskStatus, "status"),
        cursor=cursor,
        limit=limit,
    )
    return ListEnvelope(
        data=[TaskOut.model_validate(task) for task in tasks],
        meta=ListMeta(next_cursor=next_cursor, count=len(tasks)),
    )


@router.get(
    "/{task_id}",
    response_model=DataEnvelope[TaskOut],
    dependencies=[Depends(allowed_query_params())],
)
def get_task(task_id: str, user: AcceptedUserDep, session: SessionDep) -> DataEnvelope[TaskOut]:
    return DataEnvelope(data=TaskOut.model_validate(queue.get_task(session, user.id, task_id)))


@router.post("/{task_id}/cancel", response_model=DataEnvelope[TaskOut])
def cancel_task(task_id: str, user: AcceptedUserDep, session: SessionDep) -> DataEnvelope[TaskOut]:
    """Queued tasks stop immediately; running tasks stop at their next checkpoint."""
    task = queue.request_cancel(session, user.id, task_id)
    return DataEnvelope(data=TaskOut.model_validate(task))


@router.post(
    "/{task_id}/retry",
    response_model=DataEnvelope[TaskOut],
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_task(task_id: str, user: AcceptedUserDep, session: SessionDep) -> DataEnvelope[TaskOut]:
    """Re-enqueue a failed task as a new task with the same input."""
    task = queue.retry(session, user.id, task_id)
    return DataEnvelope(data=TaskOut.model_validate(task))
