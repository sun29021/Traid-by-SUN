"""Queries for edit jobs and their glyph usage."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.pagination import Cursor
from app.db.models import EditJob, EditJobGlyph, Glyph, Task
from app.db.models.enums import GlyphStatus, TaskStatus, TaskSubject, TaskType
from app.repositories.pagination import before


def get(session: Session, owner_id: str, job_id: str) -> EditJob | None:
    return session.scalar(select(EditJob).where(EditJob.id == job_id, EditJob.owner_id == owner_id))


def get_unscoped(session: Session, job_id: str) -> EditJob | None:
    return session.get(EditJob, job_id)


def add(session: Session, job: EditJob) -> EditJob:
    session.add(job)
    session.flush()
    return job


def list_jobs(
    session: Session,
    owner_id: str,
    *,
    profile_id: str | None,
    statuses: Sequence[str] | None,
    quality: Sequence[str] | None,
    created_from: datetime | None,
    created_to: datetime | None,
    text_prefix: str | None,
    include_batch_items: bool,
    cursor: Cursor | None,
    limit: int,
) -> Sequence[EditJob]:
    query = select(EditJob).where(EditJob.owner_id == owner_id)
    if not include_batch_items:
        query = query.where(EditJob.batch_id.is_(None))
    if profile_id:
        query = query.where(EditJob.profile_id == profile_id)
    if statuses:
        query = query.where(EditJob.status.in_(statuses))
    if quality:
        query = query.where(EditJob.quality_overall.in_(quality))
    if created_from:
        query = query.where(EditJob.created_at >= created_from)
    if created_to:
        query = query.where(EditJob.created_at < created_to)
    if text_prefix:
        escaped = text_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"{escaped}%"
        query = query.where(
            or_(
                EditJob.new_text.like(pattern, escape="\\"),
                EditJob.original_text.like(pattern, escape="\\"),
            )
        )
    if cursor is not None:
        query = query.where(before(EditJob.created_at, EditJob.id, cursor))
    query = query.order_by(EditJob.created_at.desc(), EditJob.id.desc()).limit(limit + 1)
    return session.scalars(query).all()


def usable_glyphs(session: Session, profile_id: str, use_auto: bool) -> Sequence[Glyph]:
    statuses = [GlyphStatus.CONFIRMED.value] + ([GlyphStatus.AUTO.value] if use_auto else [])
    return session.scalars(
        select(Glyph).where(Glyph.profile_id == profile_id, Glyph.status.in_(statuses))
    ).all()


def usable_chars(session: Session, profile_id: str, use_auto: bool) -> set[str]:
    statuses = [GlyphStatus.CONFIRMED.value] + ([GlyphStatus.AUTO.value] if use_auto else [])
    rows = session.scalars(
        select(Glyph.char)
        .where(Glyph.profile_id == profile_id, Glyph.status.in_(statuses))
        .distinct()
    )
    return set(rows)


def replace_job_glyphs(session: Session, job_id: str, rows: Sequence[EditJobGlyph]) -> None:
    session.execute(delete(EditJobGlyph).where(EditJobGlyph.job_id == job_id))
    session.add_all(rows)
    session.flush()


def job_glyph_ids(session: Session, job_id: str) -> list[str]:
    return [
        glyph_id
        for glyph_id in session.scalars(
            select(EditJobGlyph.glyph_id).where(
                EditJobGlyph.job_id == job_id, EditJobGlyph.glyph_id.is_not(None)
            )
        )
        if glyph_id
    ]


def bump_glyph_counters(session: Session, glyph_ids: Sequence[str], *, accepted: bool) -> None:
    if not glyph_ids:
        return
    column = Glyph.accept_count if accepted else Glyph.reject_count
    session.execute(
        update(Glyph)
        .where(Glyph.id.in_(glyph_ids))
        .values({column: column + 1})
        .execution_options(synchronize_session=False)
    )


def bump_use_counts(session: Session, glyph_ids: Sequence[str]) -> None:
    if glyph_ids:
        session.execute(
            update(Glyph)
            .where(Glyph.id.in_(glyph_ids))
            .values(use_count=Glyph.use_count + 1)
            .execution_options(synchronize_session=False)
        )


def active_task(session: Session, job_id: str, task_type: TaskType) -> Task | None:
    return session.scalar(
        select(Task)
        .where(
            Task.subject_type == TaskSubject.EDIT_JOB.value,
            Task.subject_id == job_id,
            Task.type == task_type.value,
            Task.status.in_([TaskStatus.QUEUED.value, TaskStatus.RUNNING.value]),
        )
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(1)
    )


def newer_render_queued(session: Session, job_id: str, task_id: str, created: datetime) -> bool:
    """True when a later render of the same job is waiting: this result is superseded."""
    count = session.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.subject_type == TaskSubject.EDIT_JOB.value,
            Task.subject_id == job_id,
            Task.type == TaskType.RENDER.value,
            Task.status == TaskStatus.QUEUED.value,
            Task.id != task_id,
            Task.created_at >= created,
        )
    )
    return bool(count)


def delete_job(session: Session, job: EditJob) -> None:
    session.delete(job)
    session.flush()
