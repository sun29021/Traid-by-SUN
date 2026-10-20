"""Edit jobs (API.md §3.6)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status

from app.api.deps import (
    AcceptedUserDep,
    SessionDep,
    SettingsDep,
    allowed_query_params,
    get_file_store,
    parse_csv_enum,
)
from app.core.errors import ValidationFailed
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.core.rate_limit import upload_limit
from app.db.models.enums import JobStatus, QualityStatus
from app.schemas.common import DataEnvelope, ListEnvelope, ListMeta
from app.schemas.jobs import (
    EditJobOut,
    ExportOut,
    ExportRequest,
    GlyphVariantOut,
    JobCreated,
    RegionUpdate,
    RejectRequest,
    RenderRequest,
)
from app.schemas.tasks import TaskOut
from app.services import export as export_service
from app.services import jobs as jobs_service
from app.services import profiles as profiles_service
from app.services.job_engine import JobDeps, glyph_variants, harvest_glyphs, read_region_text
from app.storage.filestore import FileStore

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger("traid.api.jobs")

FileStoreDep = Annotated[FileStore, Depends(get_file_store)]


def get_job_deps(request: Request) -> JobDeps:
    deps: JobDeps = request.app.state.job_deps
    return deps


JobDepsDep = Annotated[JobDeps, Depends(get_job_deps)]


def _day(value: date | None, *, end: bool = False) -> datetime | None:
    if value is None:
        return None
    moment = datetime.combine(value, time.min, tzinfo=UTC)
    return moment + timedelta(days=1) if end else moment


@router.post(
    "",
    response_model=DataEnvelope[JobCreated],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(upload_limit)],
)
def create_job(
    user: AcceptedUserDep,
    session: SessionDep,
    settings: SettingsDep,
    store: FileStoreDep,
    file: Annotated[UploadFile, File(description="Target image: JPEG, PNG or TIFF")],
    profile_id: Annotated[str, Form(max_length=36)],
) -> DataEnvelope[JobCreated]:
    """Store the image and start text detection (task returned)."""
    limit = settings.max_upload_mb * 1024 * 1024 + 1
    job, task = jobs_service.create_job(
        session,
        store,
        settings,
        owner_id=user.id,
        profile_id=profile_id,
        data=file.file.read(limit),
        original_name=file.filename,
    )
    return DataEnvelope(data=JobCreated(job=job, task=TaskOut.model_validate(task)))


@router.get(
    "",
    response_model=ListEnvelope[EditJobOut],
    dependencies=[
        Depends(
            allowed_query_params(
                "profile_id",
                "status",
                "quality",
                "from",
                "to",
                "q",
                "include_batch_items",
                "cursor",
                "limit",
            )
        )
    ],
)
def list_jobs(
    user: AcceptedUserDep,
    session: SessionDep,
    profile_id: Annotated[str | None, Query(max_length=36)] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    quality: str | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    q: Annotated[str | None, Query(max_length=64)] = None,
    include_batch_items: bool = False,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> ListEnvelope[EditJobOut]:
    """History, newest first. `q` matches the start of the old or new token."""
    qualities = parse_csv_enum(quality, QualityStatus, "quality")
    jobs, next_cursor = jobs_service.list_jobs(
        session,
        user.id,
        profile_id=profile_id,
        statuses=parse_csv_enum(status_filter, JobStatus, "status"),
        quality=[q.value for q in qualities] if qualities else None,
        created_from=_day(date_from),
        created_to=_day(date_to, end=True),
        text_prefix=q or None,
        include_batch_items=include_batch_items,
        cursor=cursor,
        limit=limit,
    )
    return ListEnvelope(data=jobs, meta=ListMeta(next_cursor=next_cursor, count=len(jobs)))


@router.get(
    "/{job_id}",
    response_model=DataEnvelope[EditJobOut],
    dependencies=[Depends(allowed_query_params())],
)
def get_job(job_id: str, user: AcceptedUserDep, session: SessionDep) -> DataEnvelope[EditJobOut]:
    return DataEnvelope(data=jobs_service.get_job(session, user.id, job_id))


@router.put("/{job_id}/region", response_model=DataEnvelope[EditJobOut])
def set_region(
    job_id: str, body: RegionUpdate, user: AcceptedUserDep, session: SessionDep, deps: JobDepsDep
) -> DataEnvelope[EditJobOut]:
    """Choose a detected region or draw a quad (old text is re-read by OCR)."""
    job = jobs_service.set_region(
        session,
        user.id,
        job_id,
        body,
        read_text=lambda j, quad: read_region_text(deps, session, j, quad),
    )
    return DataEnvelope(data=job)


@router.post(
    "/{job_id}/render",
    response_model=DataEnvelope[TaskOut],
    status_code=status.HTTP_202_ACCEPTED,
)
def render(
    job_id: str, body: RenderRequest, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[TaskOut]:
    """Validate the new token now, render in the background (an identical request in
    flight is returned instead of starting another)."""
    task = jobs_service.request_render(session, user.id, job_id, body)
    return DataEnvelope(data=TaskOut.model_validate(task))


@router.get(
    "/{job_id}/glyph-variants",
    response_model=DataEnvelope[list[GlyphVariantOut]],
    dependencies=[Depends(allowed_query_params("position"))],
)
def get_glyph_variants(
    job_id: str,
    user: AcceptedUserDep,
    session: SessionDep,
    deps: JobDepsDep,
    position: Annotated[int, Query(ge=0, le=63)],
) -> DataEnvelope[list[GlyphVariantOut]]:
    """Top 6 real glyphs for one character of the new token, best first."""
    job = jobs_service.get_owned(session, user.id, job_id)
    profile = profiles_service.get_owned(session, user.id, job.profile_id)
    if not job.new_text or position >= len(job.new_text):
        raise ValidationFailed("position is outside the new text")
    items = glyph_variants(deps, session, job, profile, position)
    return DataEnvelope(data=[GlyphVariantOut.model_validate(i) for i in items])


@router.post("/{job_id}/accept", response_model=DataEnvelope[EditJobOut])
def accept(
    job_id: str, user: AcceptedUserDep, session: SessionDep, deps: JobDepsDep
) -> DataEnvelope[EditJobOut]:
    """Accept the render: learning update + audit; the job's original characters become
    glyph candidates for review."""
    job = jobs_service.accept(session, user.id, job_id)
    try:
        harvest_glyphs(deps, job_id)
    except Exception:  # harvesting is a bonus; the accept already succeeded
        logger.exception("Glyph harvest failed", extra={"job_id": job_id})
    return DataEnvelope(data=job)


@router.post("/{job_id}/reject", response_model=DataEnvelope[EditJobOut])
def reject(
    job_id: str, user: AcceptedUserDep, session: SessionDep, body: RejectRequest | None = None
) -> DataEnvelope[EditJobOut]:
    reason = body.reason if body else None
    return DataEnvelope(data=jobs_service.reject(session, user.id, job_id, reason))


@router.post(
    "/{job_id}/export",
    response_model=DataEnvelope[ExportOut],
    status_code=status.HTTP_201_CREATED,
)
def export(
    job_id: str,
    user: AcceptedUserDep,
    session: SessionDep,
    store: FileStoreDep,
    body: ExportRequest | None = None,
) -> DataEnvelope[ExportOut]:
    return DataEnvelope(
        data=export_service.export_job(session, store, user.id, job_id, body or ExportRequest())
    )


@router.post(
    "/{job_id}/reopen", response_model=DataEnvelope[EditJobOut], status_code=status.HTTP_201_CREATED
)
def reopen(job_id: str, user: AcceptedUserDep, session: SessionDep) -> DataEnvelope[EditJobOut]:
    return DataEnvelope(data=jobs_service.reopen(session, user.id, job_id))


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, user: AcceptedUserDep, session: SessionDep) -> Response:
    jobs_service.delete_job(session, user.id, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
