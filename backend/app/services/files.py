"""Storing uploaded images: validate, dedupe by content hash, write, register."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import StoredFile
from app.db.models.enums import FileKind
from app.db.transaction import transaction
from app.repositories import files as files_repo
from app.storage.filestore import FileStore, sanitize_original_name, sha256_hex
from app.storage.images import validate_image

IMAGE_UPLOAD_KINDS = frozenset({FileKind.REFERENCE, FileKind.TARGET})


@dataclass(frozen=True)
class StoredUpload:
    file: StoredFile
    created: bool  # False when identical content of the same kind was already stored


def store_image_upload(
    session: Session,
    store: FileStore,
    settings: Settings,
    *,
    owner_id: str,
    data: bytes,
    kind: FileKind,
    original_name: str | None,
) -> StoredUpload:
    """Validate an uploaded image and store it once per (owner, content, kind)."""
    if kind not in IMAGE_UPLOAD_KINDS:
        raise ValueError(f"{kind} is not an upload kind")

    info = validate_image(
        data,
        max_bytes=settings.max_upload_mb * 1024 * 1024,
        max_pixels=settings.max_pixels,
    )
    digest = sha256_hex(data)

    with transaction(session):
        existing = files_repo.get_by_hash(session, owner_id, digest, kind)
        if existing is not None:
            return StoredUpload(existing, created=False)

        # Write before inserting: a crash in between leaves only an unreferenced file,
        # which the orphan sweep removes (DATABASE.md §8). Never a row without a file.
        storage_path = store.write(data, digest, info.mime_type)
        stored = files_repo.add(
            session,
            StoredFile(
                owner_id=owner_id,
                sha256=digest,
                kind=kind.value,
                mime_type=info.mime_type.value,
                byte_size=len(data),
                width=info.width,
                height=info.height,
                dpi_x=info.dpi_x,
                dpi_y=info.dpi_y,
                has_icc=int(info.has_icc),
                storage_path=storage_path,
                original_name=sanitize_original_name(original_name),
            ),
        )
        return StoredUpload(stored, created=True)
