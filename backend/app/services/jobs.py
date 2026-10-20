"""Edit jobs: create, choose region, request renders, accept/reject, reopen, delete.

State machine (DATABASE.md §3.8), enforced here:

    uploaded → detecting → detected → rendering → rendered → accepted
                    ↘ failed        ↗    ↘ failed    ↘ rejected → rendering
    detected / rendered / rejected / failed → (region changed) → detected
    accepted is immutable (reopen copies it into a new job)

Invalid transitions answer 409 INVALID_STATE.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import Settings
from app.core.errors import Conflict, ErrorCode, NotFound, ValidationFailed
from app.core.pagination import decode_cursor
from app.db.models import EditJob, StoredFile, Task
from app.db.models.enums import FileKind, JobStatus, TaskStatus, TaskSubject, TaskType
from app.db.transaction import transaction
from app.engine.geometry import is_valid_quad, order_quad
from app.repositories import files as files_repo
from app.repositories import jobs as repo
from app.repositories.pagination import split_page
from app.schemas.jobs import (
    EditJobOut,
    GlyphUseOut,
    QualityOut,
    RegionOut,
    RegionUpdate,
    RenderParamsIn,
    RenderRequest,
)
from app.services import audit, learning
from app.services import profiles as profiles_service
from app.services.audit import AuditAction
from app.services.files import store_image_upload
from app.services.mappers import file_ref
from app.storage.filestore import FileStore
from app.worker import queue

REGION_STATES = (JobStatus.DETECTED, JobStatus.RENDERED, JobStatus.REJECTED, JobStatus.FAILED)
RENDER_STATES = (*REGION_STATES, JobStatus.RENDERING)
_DEFAULT_PARAMS = RenderParamsIn().model_dump()


class InvalidState(Conflict):
    code = ErrorCode.INVALID_STATE


def _require(job: EditJob, allowed: Sequence[JobStatus], action: str) -> None:
    if job.status not in {s.value for s in allowed}:
        raise InvalidState(
            f"Cannot {action} a job that is {job.status}",
            details={"status": job.status, "allowed": [s.value for s in allowed]},
        )


def get_owned(session: Session, owner_id: str, job_id: str) -> EditJob:
    job = repo.get(session, owner_id, job_id)
    if job is None:
        raise NotFound("Edit job not found")
    return job


def _file(session: Session, owner_id: str, file_id: str | None) -> StoredFile | None:
    return files_repo.get(session, owner_id, file_id) if file_id else None


def to_out(session: Session, job: EditJob) -> EditJobOut:
    stored = _file(session, job.owner_id, job.input_file_id)
    if stored is None:  # pragma: no cover - FK guarantees it
        raise NotFound("Input file not found")
    result = _file(session, job.owner_id, job.result_file_id)
    mask = _file(session, job.owner_id, job.mask_file_id)
    render: dict[str, Any] = (job.geometry or {}).get("render", {})
    params = {**_DEFAULT_PARAMS, **(job.params or {})}
    return EditJobOut(
        id=job.id,
        profile_id=job.profile_id,
        batch_id=job.batch_id,
        status=JobStatus(job.status),
        input=file_ref(stored),
        result=file_ref(result) if result else None,
        mask=file_ref(mask) if mask else None,
        regions=[
            RegionOut(
                id=r["id"],
                quad=r["quad"],
                text=r["text"],
                confidence=r["confidence"],
                score=r["score"],
                reasons=r.get("reasons", []),
            )
            for r in job.regions or []
        ],
        selected_region_id=job.selected_region_id,
        selected_quad=job.selected_quad,
        original_text=job.original_text,
        new_text=job.new_text,
        params=RenderParamsIn.model_validate(params),
        glyphs_used=[GlyphUseOut.model_validate(u) for u in render.get("glyphs_used", [])],
        quality=QualityOut.model_validate(job.quality) if job.quality else None,
        layout_mode=render.get("layout_mode"),
        warnings=list(render.get("warnings", [])),
        engine_version=job.engine_version,
        seed=job.seed,
        reject_reason=job.reject_reason,
        error_code=job.error_code,
        accepted_at=job.accepted_at,
        exported_at=job.exported_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def get_job(session: Session, owner_id: str, job_id: str) -> EditJobOut:
    return to_out(session, get_owned(session, owner_id, job_id))


def list_jobs(
    session: Session,
    owner_id: str,
    *,
    profile_id: str | None = None,
    statuses: Sequence[JobStatus] | None = None,
    quality: Sequence[str] | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    text_prefix: str | None = None,
    include_batch_items: bool = False,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[EditJobOut], str | None]:
    rows = repo.list_jobs(
        session,
        owner_id,
        profile_id=profile_id,
        statuses=[s.value for s in statuses] if statuses else None,
        quality=list(quality) if quality else None,
        created_from=created_from,
        created_to=created_to,
        text_prefix=text_prefix,
        include_batch_items=include_batch_items,
        cursor=decode_cursor(cursor) if cursor else None,
        limit=limit,
    )
    page, next_cursor = split_page(rows, limit)
    return [to_out(session, job) for job in page], next_cursor


def _starting_params(learned: dict[str, Any] | None) -> dict[str, Any]:
    """Defaults, nudged by what the owner usually adjusts for this profile (Phase 11)."""
    params = dict(_DEFAULT_PARAMS)
    for key, value in (learned or {}).items():
        if key in params and key != "glyph_overrides" and isinstance(value, int | float):
            params[key] = float(value)
    try:
        return RenderParamsIn.model_validate(params).model_dump()
    except ValueError:
        return dict(_DEFAULT_PARAMS)


def enqueue_detect(session: Session, job: EditJob) -> Task:
    return queue.enqueue(
        session,
        owner_id=job.owner_id,
        task_type=TaskType.DETECT,
        subject_type=TaskSubject.EDIT_JOB,
        subject_id=job.id,
        payload={"job_id": job.id},
    )


def create_job(
    session: Session,
    store: FileStore,
    settings: Settings,
    *,
    owner_id: str,
    profile_id: str,
    data: bytes,
    original_name: str | None,
) -> tuple[EditJobOut, Task]:
    with transaction(session):
        profile = profiles_service.get_owned(session, owner_id, profile_id)
        profiles_service.require_active(profile)
        stored = store_image_upload(
            session,
            store,
            settings,
            owner_id=owner_id,
            data=data,
            kind=FileKind.TARGET,
            original_name=original_name,
        ).file
        job = repo.add(
            session,
            EditJob(
                owner_id=owner_id,
                profile_id=profile.id,
                input_file_id=stored.id,
                status=JobStatus.UPLOADED.value,
                params=_starting_params(profile.learned_params),
                seed=secrets.randbelow(2**31),
            ),
        )
        task = enqueue_detect(session, job)
    return to_out(session, job), task


def _clear_render(job: EditJob) -> None:
    job.result_file_id = None
    job.mask_file_id = None
    job.quality = None
    job.quality_overall = None
    job.geometry = None
    job.error_code = None
    job.reject_reason = None


def set_region(
    session: Session,
    owner_id: str,
    job_id: str,
    body: RegionUpdate,
    *,
    read_text: Any = None,
) -> EditJobOut:
    """`read_text(job, quad) -> str | None` re-reads the old token (OCR) for drawn quads."""
    if (body.region_id is None) == (body.quad is None):
        raise ValidationFailed("Send exactly one of region_id or quad")
    with transaction(session):
        job = get_owned(session, owner_id, job_id)
        _require(job, REGION_STATES, "change the region of")
        stored = _file(session, owner_id, job.input_file_id)
        width, height = (stored.width or 0, stored.height or 0) if stored else (0, 0)
        if body.region_id is not None:
            region = next((r for r in job.regions or [] if r["id"] == body.region_id), None)
            if region is None:
                raise ValidationFailed("Unknown region", details={"region_id": body.region_id})
            quad = region["quad"]
            text: str | None = region["text"]
            job.selected_region_id = body.region_id
        else:
            points = order_quad(np.asarray(body.quad, dtype=np.float32))
            if not is_valid_quad(points, width, height):
                raise ValidationFailed(
                    "The region must be convex, inside the image and at least 64 px²"
                )
            quad = [[round(float(x), 1), round(float(y), 1)] for x, y in points]
            text = read_text(job, quad) if read_text is not None else None
            job.selected_region_id = None
        if body.original_text is not None:
            text = body.original_text
        job.selected_quad = quad
        job.original_text = text.strip() if text and text.strip() else None
        _clear_render(job)
        job.status = JobStatus.DETECTED.value
    return to_out(session, job)


def _validate_text(session: Session, job: EditJob, new_text: str) -> None:
    profile = profiles_service.get_owned(session, job.owner_id, job.profile_id)
    profiles_service.require_active(profile)
    outside = sorted({c for c in new_text if c not in profile.charset})
    if outside:
        raise ValidationFailed(
            "Some characters are not in this profile's character set",
            code=ErrorCode.CHAR_NOT_IN_CHARSET,
            details={"chars": outside},
        )
    strict = profile.pattern_strict and profile.token_pattern
    if strict and not re.fullmatch(str(profile.token_pattern), new_text):
        raise ValidationFailed(
            "The token does not match the profile's pattern",
            code=ErrorCode.PATTERN_MISMATCH,
            details={"pattern": profile.token_pattern},
        )
    available = repo.usable_chars(session, profile.id, bool(profile.use_auto_glyphs))
    available |= set(job.original_text or "")
    missing = sorted({c for c in new_text if c != " " and c not in available})
    if missing:
        raise Conflict(
            "The profile has no reviewed glyphs for some characters",
            code=ErrorCode.PROFILE_NOT_READY,
            details={"missing": missing},
        )


def request_render(session: Session, owner_id: str, job_id: str, body: RenderRequest) -> Task:
    with transaction(session):
        job = get_owned(session, owner_id, job_id)
        _require(job, RENDER_STATES, "render")
        if not job.selected_quad:
            raise InvalidState("Select the token region first")
        if not job.original_text:
            raise InvalidState(
                "The old text could not be read; type it in the region panel",
                details={"field": "original_text"},
            )
        _validate_text(session, job, body.new_text)
        params = (body.params or RenderParamsIn()).model_dump()
        for key in params["glyph_overrides"]:
            if not key.isdigit() or int(key) >= len(body.new_text):
                raise ValidationFailed(
                    "glyph_overrides keys must be character positions of the new text"
                )
        payload = {"job_id": job.id, "new_text": body.new_text, "params": params}

        existing = repo.active_task(session, job.id, TaskType.RENDER)
        if existing is not None:
            if existing.payload == payload:
                return existing  # the same render is already on its way
            if existing.status == TaskStatus.QUEUED.value:
                existing.payload = payload  # not started yet: render the latest request
                job.new_text, job.params = body.new_text, params
                return existing
        job.new_text = body.new_text
        job.params = params
        job.error_code = None
        job.status = JobStatus.RENDERING.value
        return queue.enqueue(
            session,
            owner_id=owner_id,
            task_type=TaskType.RENDER,
            subject_type=TaskSubject.EDIT_JOB,
            subject_id=job.id,
            payload=payload,
        )


def accept(session: Session, owner_id: str, job_id: str) -> EditJobOut:
    """Accept the current render: glyph acceptance counters + audit, one transaction."""
    with transaction(session):
        job = get_owned(session, owner_id, job_id)
        if job.status == JobStatus.ACCEPTED.value:
            return to_out(session, job)  # idempotent
        _require(job, (JobStatus.RENDERED,), "accept")
        learning.on_accept(session, job)
        job.status = JobStatus.ACCEPTED.value
        job.accepted_at = utcnow()
        audit.record(
            session,
            user_id=owner_id,
            action=AuditAction.JOB_ACCEPTED,
            subject=("edit_job", job.id),
            details={"quality": job.quality_overall, "new_text_length": len(job.new_text or "")},
        )
    return to_out(session, job)


def reject(session: Session, owner_id: str, job_id: str, reason: str | None) -> EditJobOut:
    with transaction(session):
        job = get_owned(session, owner_id, job_id)
        _require(job, (JobStatus.RENDERED,), "reject")
        learning.on_reject(session, job)
        job.status = JobStatus.REJECTED.value
        job.reject_reason = reason.strip() if reason and reason.strip() else None
        audit.record(
            session,
            user_id=owner_id,
            action=AuditAction.JOB_REJECTED,
            subject=("edit_job", job.id),
            details={"has_reason": job.reject_reason is not None},
        )
    return to_out(session, job)


def reopen(session: Session, owner_id: str, job_id: str) -> EditJobOut:
    """A new editable job with the same input, region, text and adjustments."""
    with transaction(session):
        job = get_owned(session, owner_id, job_id)
        profile = profiles_service.get_owned(session, owner_id, job.profile_id)
        profiles_service.require_active(profile)
        has_region = bool(job.selected_quad)
        copy = repo.add(
            session,
            EditJob(
                owner_id=owner_id,
                profile_id=job.profile_id,
                input_file_id=job.input_file_id,
                status=(JobStatus.DETECTED if has_region else JobStatus.UPLOADED).value,
                regions=job.regions,
                selected_region_id=job.selected_region_id,
                selected_quad=job.selected_quad,
                original_text=job.original_text,
                new_text=job.new_text,
                params=dict(job.params or _DEFAULT_PARAMS),
                seed=job.seed,
            ),
        )
        if not has_region:
            enqueue_detect(session, copy)
    return to_out(session, copy)


def delete_job(session: Session, owner_id: str, job_id: str) -> None:
    with transaction(session):
        job = get_owned(session, owner_id, job_id)
        if job.status in (JobStatus.DETECTING.value, JobStatus.RENDERING.value):
            for task_type in (TaskType.DETECT, TaskType.RENDER):
                task = repo.active_task(session, job.id, task_type)
                if task is not None:
                    task.cancel_requested = 1
                    if task.status == TaskStatus.QUEUED.value:
                        task.status = TaskStatus.CANCELLED.value
        audit.record(
            session,
            user_id=owner_id,
            action=AuditAction.JOB_DELETED,
            subject=("edit_job", job.id),
            details={"status": job.status},
        )
        repo.delete_job(session, job)
