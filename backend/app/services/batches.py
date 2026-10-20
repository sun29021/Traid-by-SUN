"""Batches: many tokens rendered from one template job (PRD J4, API.md §3.7).

Items are ordinary edit jobs with `batch_id` set, copying the template's input,
region, old text, adjustments and seed. The `batch_run` task renders them in order;
the text removal of the template is cached and reused, so each item only lays out
and composites (ARCHITECTURE §3.3). Accepting and reviewing items uses `/jobs/{id}`.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from collections.abc import Sequence
from pathlib import PurePath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.db.models import Batch, EditJob, StoredFile
from app.db.models.enums import (
    BatchStatus,
    FileKind,
    JobStatus,
    MimeType,
    TaskStatus,
    TaskSubject,
    TaskType,
)
from app.db.transaction import transaction
from app.repositories import files as files_repo
from app.repositories import jobs as jobs_repo
from app.schemas.batches import (
    BatchCounts,
    BatchCreate,
    BatchOut,
    BatchValidation,
    InvalidValue,
)
from app.schemas.jobs import EditJobOut
from app.services import audit, export, learning
from app.services import jobs as jobs_service
from app.services import profiles as profiles_service
from app.services.audit import AuditAction
from app.services.files import store_generated_file
from app.services.job_engine import JobDeps, render_job
from app.services.mappers import file_ref
from app.worker import queue
from app.worker.runner import TaskCancelled, TaskContext

logger = logging.getLogger("traid.batches")

MAX_VALUES = 1000
_QUALITY_ORDER = {"fail": 0, "warn": 1, "pass": 2, None: 3}


def _owned(session: Session, owner_id: str, batch_id: str) -> Batch:
    batch = session.scalar(select(Batch).where(Batch.id == batch_id, Batch.owner_id == owner_id))
    if batch is None:
        raise NotFound("Batch not found")
    return batch


def _items(session: Session, batch_id: str) -> list[EditJob]:
    rows = session.scalars(select(EditJob).where(EditJob.batch_id == batch_id)).all()
    return sorted(rows, key=lambda j: (j.geometry or {}).get("batch_position", 0))


def counts(items: Sequence[EditJob]) -> BatchCounts:
    tally = dict.fromkeys(("pending", "rendered", "warn", "failed", "accepted", "rejected"), 0)
    for job in items:
        if job.status in (JobStatus.DETECTED.value, JobStatus.RENDERING.value):
            tally["pending"] += 1
        elif job.status == JobStatus.RENDERED.value:
            tally["rendered" if job.quality_overall == "pass" else "warn"] += 1
        elif job.status in tally:
            tally[job.status] += 1
    return BatchCounts(**tally)


def to_out(session: Session, batch: Batch) -> BatchOut:
    zip_file = (
        files_repo.get(session, batch.owner_id, batch.export_file_id)
        if batch.export_file_id
        else None
    )
    return BatchOut(
        id=batch.id,
        profile_id=batch.profile_id,
        template_job_id=batch.template_job_id,
        name=batch.name,
        status=BatchStatus(batch.status),
        total_count=batch.total_count,
        counts=counts(_items(session, batch.id)),
        export_file=file_ref(zip_file) if zip_file else None,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
    )


# ---------------------------------------------------------------- validation


def validate_values(
    session: Session,
    owner_id: str,
    profile_id: str,
    values: Sequence[str],
    template_job_id: str | None = None,
) -> BatchValidation:
    """Dry-run check of every value (trimmed; blank lines ignored)."""
    profile = profiles_service.get_owned(session, owner_id, profile_id)
    original = ""
    if template_job_id:
        original = jobs_service.get_owned(session, owner_id, template_job_id).original_text or ""
    usable = jobs_repo.usable_chars(session, profile.id, bool(profile.use_auto_glyphs)) | set(
        original
    )
    seen: set[str] = set()
    valid: list[str] = []
    invalid: list[InvalidValue] = []
    duplicates: list[str] = []
    for raw in values:
        value = raw.strip()
        if not value:
            continue
        if value in seen:
            duplicates.append(value)
            continue
        seen.add(value)
        outside = sorted({c for c in value if c not in profile.charset})
        missing = sorted({c for c in value if c != " " and c not in usable})
        if len(value) > 64:
            invalid.append(
                InvalidValue(
                    value=value, code="VALIDATION_FAILED", message="Longer than 64 characters"
                )
            )
        elif outside:
            invalid.append(
                InvalidValue(
                    value=value,
                    code="CHAR_NOT_IN_CHARSET",
                    message="Not in the character set: " + " ".join(outside),
                )
            )
        elif (
            profile.pattern_strict
            and profile.token_pattern
            and not re.fullmatch(profile.token_pattern, value)
        ):
            invalid.append(
                InvalidValue(
                    value=value, code="PATTERN_MISMATCH", message="Does not match the pattern"
                )
            )
        elif missing:
            invalid.append(
                InvalidValue(
                    value=value,
                    code="GLYPH_MISSING",
                    message="No reviewed glyphs for: " + " ".join(missing),
                )
            )
        else:
            valid.append(value)
    return BatchValidation(valid=valid, invalid=invalid, duplicates=duplicates)


# ---------------------------------------------------------------- lifecycle


def create_batch(session: Session, owner_id: str, body: BatchCreate) -> tuple[BatchOut, Any]:
    with transaction(session):
        if body.client_request_id:
            existing = session.scalar(
                select(Batch).where(
                    Batch.owner_id == owner_id, Batch.client_request_id == body.client_request_id
                )
            )
            if existing is not None:  # idempotent retry of the same request
                task = jobs_repo.latest_task(session, existing.id, TaskType.BATCH_RUN)
                return to_out(session, existing), task
        template = jobs_service.get_owned(session, owner_id, body.template_job_id)
        if template.status not in (JobStatus.RENDERED.value, JobStatus.ACCEPTED.value):
            raise jobs_service.InvalidState("The template must be a rendered or accepted edit")
        if template.batch_id is not None:
            raise jobs_service.InvalidState("A batch item cannot be a template")
        running = session.scalar(
            select(Batch.id).where(
                Batch.owner_id == owner_id,
                Batch.status.in_([BatchStatus.QUEUED.value, BatchStatus.RUNNING.value]),
            )
        )
        if running is not None:
            raise Conflict("Another batch is still running; wait or cancel it")
        profile = profiles_service.get_owned(session, owner_id, template.profile_id)
        profiles_service.require_active(profile)
        check = validate_values(session, owner_id, profile.id, body.values, template.id)
        if check.invalid:
            raise ValidationFailed(
                "Some values cannot be rendered",
                details={"invalid": [i.model_dump() for i in check.invalid]},
            )
        if not check.valid:
            raise ValidationFailed("Add at least one value")
        batch = Batch(
            owner_id=owner_id,
            profile_id=profile.id,
            template_job_id=template.id,
            name=body.name.strip() if body.name and body.name.strip() else None,
            status=BatchStatus.QUEUED.value,
            total_count=len(check.valid),
            client_request_id=body.client_request_id,
        )
        session.add(batch)
        session.flush()
        for position, value in enumerate(check.valid):
            session.add(
                EditJob(
                    owner_id=owner_id,
                    profile_id=profile.id,
                    batch_id=batch.id,
                    input_file_id=template.input_file_id,
                    status=JobStatus.DETECTED.value,
                    regions=template.regions,
                    selected_region_id=template.selected_region_id,
                    selected_quad=template.selected_quad,
                    original_text=template.original_text,
                    new_text=value,
                    params=dict(template.params or {}),
                    geometry={"batch_position": position},
                    seed=template.seed,
                )
            )
        session.flush()
        task = queue.enqueue(
            session,
            owner_id=owner_id,
            task_type=TaskType.BATCH_RUN,
            subject_type=TaskSubject.BATCH,
            subject_id=batch.id,
            payload={"batch_id": batch.id},
        )
    return to_out(session, batch), task


def list_batches(session: Session, owner_id: str, limit: int = 50) -> list[BatchOut]:
    rows = session.scalars(
        select(Batch)
        .where(Batch.owner_id == owner_id)
        .order_by(Batch.created_at.desc(), Batch.id.desc())
        .limit(limit)
    ).all()
    return [to_out(session, b) for b in rows]


def get_batch(session: Session, owner_id: str, batch_id: str) -> BatchOut:
    return to_out(session, _owned(session, owner_id, batch_id))


def list_items(
    session: Session,
    owner_id: str,
    batch_id: str,
    *,
    statuses: Sequence[str] | None = None,
    quality: Sequence[str] | None = None,
) -> list[EditJobOut]:
    """Warnings first (fail, warn, pass), then input order (PRD US-42)."""
    _owned(session, owner_id, batch_id)
    items = _items(session, batch_id)
    if statuses:
        items = [j for j in items if j.status in statuses]
    if quality:
        items = [j for j in items if j.quality_overall in quality]
    items.sort(key=lambda j: _QUALITY_ORDER.get(j.quality_overall, 3))
    return [jobs_service.to_out(session, j) for j in items]


def cancel(session: Session, owner_id: str, batch_id: str) -> BatchOut:
    """Stop rendering; finished items are kept. Idempotent."""
    with transaction(session):
        batch = _owned(session, owner_id, batch_id)
        if batch.status in (BatchStatus.QUEUED.value, BatchStatus.RUNNING.value):
            task = jobs_repo.latest_task(session, batch.id, TaskType.BATCH_RUN)
            if task is not None and task.status in (
                TaskStatus.QUEUED.value,
                TaskStatus.RUNNING.value,
            ):
                task.cancel_requested = 1
                if task.status == TaskStatus.QUEUED.value:
                    task.status = TaskStatus.CANCELLED.value
            batch.status = BatchStatus.CANCELLED.value
            batch.finished_at = utcnow()
    return to_out(session, batch)


def accept_passed(session: Session, owner_id: str, batch_id: str) -> int:
    with transaction(session):
        _owned(session, owner_id, batch_id)
        accepted = 0
        for job in _items(session, batch_id):
            if job.status == JobStatus.RENDERED.value and job.quality_overall == "pass":
                learning.on_accept(session, job)
                job.status = JobStatus.ACCEPTED.value
                job.accepted_at = utcnow()
                accepted += 1
        if accepted:
            audit.record(
                session,
                user_id=owner_id,
                action=AuditAction.JOB_ACCEPTED,
                subject=("batch", batch_id),
                details={"accepted": accepted, "bulk": True},
            )
    return accepted


def request_export(session: Session, owner_id: str, batch_id: str) -> Any:
    with transaction(session):
        batch = _owned(session, owner_id, batch_id)
        if not any(j.status == JobStatus.ACCEPTED.value for j in _items(session, batch.id)):
            raise jobs_service.InvalidState("Accept at least one item before exporting")
        return queue.enqueue(
            session,
            owner_id=owner_id,
            task_type=TaskType.BATCH_EXPORT,
            subject_type=TaskSubject.BATCH,
            subject_id=batch.id,
            payload={"batch_id": batch.id},
        )


# ---------------------------------------------------------------- tasks


def _set_batch(deps: JobDeps, batch_id: str, status: BatchStatus, *, finished: bool) -> None:
    with deps.db.session() as session:
        batch = session.get(Batch, batch_id)
        if batch is None:
            return
        if batch.status == BatchStatus.CANCELLED.value and status != BatchStatus.CANCELLED:
            return
        batch.status = status.value
        if finished:
            batch.finished_at = utcnow()


def handle_batch_run(deps: JobDeps, ctx: TaskContext) -> None:
    batch_id = str(ctx.payload["batch_id"])
    with deps.db.session() as session:
        batch = session.get(Batch, batch_id)
        if batch is None or batch.status == BatchStatus.CANCELLED.value:
            return
        batch.status = BatchStatus.RUNNING.value
        pending = [
            (job.id, job.new_text or "", dict(job.params or {}))
            for job in _items(session, batch_id)
            if job.status == JobStatus.DETECTED.value
        ]
        total = batch.total_count
    done = total - len(pending)
    failed = 0
    try:
        for job_id, value, params in pending:
            ctx.report(done / max(total, 1), f"{done} of {total} rendered")
            try:
                render_job(deps, job_id, value, params, report=lambda _p, _m: None)
            except AppError as exc:
                failed += 1
                logger.info("Batch item failed", extra={"job_id": job_id, "code": exc.code.value})
            done += 1
    except TaskCancelled:
        _set_batch(deps, batch_id, BatchStatus.CANCELLED, finished=True)
        raise
    _set_batch(deps, batch_id, BatchStatus.COMPLETED, finished=True)
    ctx.report(
        1.0, f"{total - failed} of {total} rendered" + (f", {failed} failed" if failed else "")
    )


def _unique(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    stem, suffix = PurePath(name).stem, PurePath(name).suffix
    n = 2
    while f"{stem}_{n}{suffix}" in used:
        n += 1
    unique = f"{stem}_{n}{suffix}"
    used.add(unique)
    return unique


def handle_batch_export(deps: JobDeps, ctx: TaskContext) -> None:
    """Pack every accepted item into one ZIP. Reads happen in short sessions so progress
    updates never wait on an open write transaction (SQLite has one writer)."""
    store = deps.store
    batch_id = str(ctx.payload["batch_id"])
    with deps.db.session() as session:
        batch = session.get(Batch, batch_id)
        if batch is None:
            return
        job_ids = [j.id for j in _items(session, batch_id) if j.status == JobStatus.ACCEPTED.value]
        base = _safe_name(batch.name or "traid_batch")

    buffer = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for index, job_id in enumerate(job_ids):
            ctx.report(index / max(len(job_ids), 1), f"Packing {index + 1} of {len(job_ids)}")
            with deps.db.session() as session:
                job = session.get(EditJob, job_id)
                if job is None:
                    continue
                out = export.encode_export(session, store, job)
            archive.writestr(_unique(out.name, used), out.data)

    with deps.db.session() as session:
        batch = session.get(Batch, batch_id)
        if batch is None:
            return
        stored: StoredFile = store_generated_file(
            session,
            store,
            owner_id=batch.owner_id,
            data=buffer.getvalue(),
            kind=FileKind.BATCH_ZIP,
            mime_type=MimeType.ZIP,
            original_name=f"{base}.zip",
        )
        batch.export_file_id = stored.id
        now = utcnow()
        for job_id in job_ids:
            job = session.get(EditJob, job_id)
            if job is not None:
                job.exported_at = now
        audit.record(
            session,
            user_id=batch.owner_id,
            action=AuditAction.BATCH_EXPORTED,
            subject=("batch", batch.id),
            details={"files": len(used), "file_id": stored.id},
        )
    ctx.report(1.0, f"{len(used)} files exported")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")[:80] or "traid_batch"
