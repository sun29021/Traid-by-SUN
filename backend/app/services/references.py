"""Reference images: upload, list, known text, re-extract, delete (API.md §3.4)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, NotFound, ValidationFailed
from app.core.pagination import decode_cursor
from app.db.models import ReferenceImage, StoredFile, Task
from app.db.models.enums import FileKind, ReferenceStatus, TaskSubject, TaskType
from app.db.transaction import transaction
from app.repositories import files as files_repo
from app.repositories import profiles as repo
from app.repositories.pagination import split_page
from app.schemas.profiles import ReferenceOut, ReferenceUpload, UploadIssue
from app.schemas.tasks import TaskOut
from app.services import profiles as profiles_service
from app.services.files import store_image_upload
from app.services.mappers import reference_out
from app.storage.filestore import FileStore, sanitize_original_name
from app.worker import queue

MAX_FILES_PER_UPLOAD = 50
MAX_KNOWN_TEXT = 64


@dataclass(frozen=True)
class UploadedFile:
    name: str | None
    data: bytes


def _known_text(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    text = value.strip()
    if len(text) > MAX_KNOWN_TEXT or any(not c.isprintable() for c in text):
        raise ValidationFailed("Known text must be at most 64 printable characters")
    return text


def enqueue_extraction(
    session: Session, owner_id: str, profile_id: str, reference_ids: Sequence[str]
) -> Task:
    return queue.enqueue(
        session,
        owner_id=owner_id,
        task_type=TaskType.EXTRACT_GLYPHS,
        subject_type=TaskSubject.PROFILE,
        subject_id=profile_id,
        payload={"profile_id": profile_id, "reference_ids": list(reference_ids)},
    )


def upload(
    session: Session,
    store: FileStore,
    settings: Settings,
    *,
    owner_id: str,
    profile_id: str,
    files: Sequence[UploadedFile],
    known_texts: Sequence[str | None],
) -> ReferenceUpload:
    """Store every valid image, skip duplicates, report rejects, queue one extraction."""
    if not 1 <= len(files) <= MAX_FILES_PER_UPLOAD:
        raise ValidationFailed(f"Upload between 1 and {MAX_FILES_PER_UPLOAD} files at a time")
    texts = [_known_text(t) for t in known_texts] + [None] * (len(files) - len(known_texts))

    created: list[ReferenceOut] = []
    skipped: list[UploadIssue] = []
    rejected: list[UploadIssue] = []
    task: Task | None = None
    with transaction(session):
        profile = profiles_service.get_owned(session, owner_id, profile_id)
        profiles_service.require_active(profile)
        for upload_file, known_text in zip(files, texts, strict=False):
            name = sanitize_original_name(upload_file.name)
            try:
                stored = store_image_upload(
                    session,
                    store,
                    settings,
                    owner_id=owner_id,
                    data=upload_file.data,
                    kind=FileKind.REFERENCE,
                    original_name=upload_file.name,
                ).file
            except AppError as exc:
                if exc.http_status >= 500:
                    raise
                rejected.append(UploadIssue(name=name, code=exc.code.value, message=exc.message))
                continue
            if repo.find_reference(session, profile.id, stored.id) is not None:
                skipped.append(
                    UploadIssue(
                        name=name,
                        code=ErrorCode.DUPLICATE_FILE.value,
                        message="This image is already a reference of the profile",
                    )
                )
                continue
            reference = ReferenceImage(
                profile_id=profile.id,
                file_id=stored.id,
                known_text=known_text,
                status=ReferenceStatus.PENDING.value,
            )
            repo.add(session, reference)
            created.append(reference_out(reference, stored, 0))
        if created:
            task = enqueue_extraction(session, owner_id, profile.id, [r.id for r in created])
    return ReferenceUpload(
        created=created,
        skipped=skipped,
        rejected=rejected,
        task=TaskOut.model_validate(task) if task else None,
    )


def _owned(session: Session, owner_id: str, reference_id: str) -> ReferenceImage:
    reference = repo.get_reference(session, owner_id, reference_id)
    if reference is None:
        raise NotFound("Reference image not found")
    return reference


def _file(session: Session, owner_id: str, reference: ReferenceImage) -> StoredFile:
    stored = files_repo.get(session, owner_id, reference.file_id)
    if stored is None:  # pragma: no cover - FK guarantees it
        raise NotFound("Reference file not found")
    return stored


def describe(session: Session, owner_id: str, reference: ReferenceImage) -> ReferenceOut:
    counts = repo.glyph_counts_by_reference(session, [reference.id])
    return reference_out(
        reference, _file(session, owner_id, reference), counts.get(reference.id, 0)
    )


def list_references(
    session: Session,
    owner_id: str,
    profile_id: str,
    *,
    statuses: Sequence[ReferenceStatus] | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[ReferenceOut], str | None]:
    profiles_service.get_owned(session, owner_id, profile_id)
    rows = repo.list_references(
        session,
        owner_id,
        profile_id,
        statuses=[s.value for s in statuses] if statuses else None,
        cursor=decode_cursor(cursor) if cursor else None,
        limit=limit,
    )
    page, next_cursor = split_page(rows, limit)
    counts = repo.glyph_counts_by_reference(session, [r.id for r in page])
    items = [reference_out(r, _file(session, owner_id, r), counts.get(r.id, 0)) for r in page]
    return items, next_cursor


def reextract(session: Session, owner_id: str, reference_id: str) -> Task:
    with transaction(session):
        reference = _owned(session, owner_id, reference_id)
        profile = profiles_service.get_owned(session, owner_id, reference.profile_id)
        profiles_service.require_active(profile)
        reference.status = ReferenceStatus.PENDING.value
        reference.error_code = None
        return enqueue_extraction(session, owner_id, profile.id, [reference.id])


def set_known_text(
    session: Session, owner_id: str, reference_id: str, known_text: str | None
) -> tuple[ReferenceOut, Task | None]:
    """Changing the known text re-runs extraction for an already processed image."""
    task: Task | None = None
    with transaction(session):
        reference = _owned(session, owner_id, reference_id)
        new_text = _known_text(known_text)
        changed = new_text != reference.known_text
        reference.known_text = new_text
        if changed and reference.status in (
            ReferenceStatus.PROCESSED.value,
            ReferenceStatus.FAILED.value,
        ):
            task = reextract(session, owner_id, reference_id)
    return describe(session, owner_id, _owned(session, owner_id, reference_id)), task


def delete_reference(session: Session, owner_id: str, reference_id: str) -> None:
    with transaction(session):
        repo.delete_reference(session, _owned(session, owner_id, reference_id))
