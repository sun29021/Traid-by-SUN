"""Batches (API.md §3.7)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import AcceptedUserDep, SessionDep, allowed_query_params, parse_csv_enum
from app.db.models.enums import JobStatus, QualityStatus
from app.schemas.batches import (
    AcceptedCount,
    BatchCreate,
    BatchOut,
    BatchStarted,
    BatchValidate,
    BatchValidation,
)
from app.schemas.common import DataEnvelope
from app.schemas.jobs import EditJobOut
from app.schemas.tasks import TaskOut
from app.services import batches as service

router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("/validate", response_model=DataEnvelope[BatchValidation])
def validate(
    body: BatchValidate, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[BatchValidation]:
    """Dry run: which values can be rendered, which cannot (and why), duplicates."""
    return DataEnvelope(
        data=service.validate_values(
            session, user.id, body.profile_id, body.values, body.template_job_id
        )
    )


@router.post("", response_model=DataEnvelope[BatchStarted], status_code=status.HTTP_202_ACCEPTED)
def create(
    body: BatchCreate, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[BatchStarted]:
    """Create the items and start rendering. Repeating a `client_request_id` returns the
    existing batch."""
    batch, task = service.create_batch(session, user.id, body)
    return DataEnvelope(data=BatchStarted(batch=batch, task=TaskOut.model_validate(task)))


@router.get(
    "",
    response_model=DataEnvelope[list[BatchOut]],
    dependencies=[Depends(allowed_query_params("limit"))],
)
def list_batches(
    user: AcceptedUserDep, session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> DataEnvelope[list[BatchOut]]:
    return DataEnvelope(data=service.list_batches(session, user.id, limit))


@router.get(
    "/{batch_id}",
    response_model=DataEnvelope[BatchOut],
    dependencies=[Depends(allowed_query_params())],
)
def get_batch(batch_id: str, user: AcceptedUserDep, session: SessionDep) -> DataEnvelope[BatchOut]:
    return DataEnvelope(data=service.get_batch(session, user.id, batch_id))


@router.get(
    "/{batch_id}/items",
    response_model=DataEnvelope[list[EditJobOut]],
    dependencies=[Depends(allowed_query_params("status", "quality"))],
)
def list_items(
    batch_id: str,
    user: AcceptedUserDep,
    session: SessionDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    quality: str | None = None,
) -> DataEnvelope[list[EditJobOut]]:
    """Items, failures and warnings first."""
    statuses = parse_csv_enum(status_filter, JobStatus, "status")
    qualities = parse_csv_enum(quality, QualityStatus, "quality")
    return DataEnvelope(
        data=service.list_items(
            session,
            user.id,
            batch_id,
            statuses=[s.value for s in statuses] if statuses else None,
            quality=[q.value for q in qualities] if qualities else None,
        )
    )


@router.post("/{batch_id}/cancel", response_model=DataEnvelope[BatchOut])
def cancel(batch_id: str, user: AcceptedUserDep, session: SessionDep) -> DataEnvelope[BatchOut]:
    return DataEnvelope(data=service.cancel(session, user.id, batch_id))


@router.post("/{batch_id}/accept-passed", response_model=DataEnvelope[AcceptedCount])
def accept_passed(
    batch_id: str, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[AcceptedCount]:
    return DataEnvelope(
        data=AcceptedCount(accepted=service.accept_passed(session, user.id, batch_id))
    )


@router.post(
    "/{batch_id}/export", response_model=DataEnvelope[TaskOut], status_code=status.HTTP_202_ACCEPTED
)
def export(batch_id: str, user: AcceptedUserDep, session: SessionDep) -> DataEnvelope[TaskOut]:
    """ZIP of every accepted item (names from the export pattern; collisions get _2, _3)."""
    return DataEnvelope(
        data=TaskOut.model_validate(service.request_export(session, user.id, batch_id))
    )
