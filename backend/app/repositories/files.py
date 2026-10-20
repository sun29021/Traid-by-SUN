"""Data access for `files`. Every read is scoped by owner (DATABASE.md §7)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import StoredFile
from app.db.models.enums import FileKind


def get(session: Session, owner_id: str, file_id: str) -> StoredFile | None:
    return session.scalar(
        select(StoredFile).where(StoredFile.id == file_id, StoredFile.owner_id == owner_id)
    )


def get_by_hash(session: Session, owner_id: str, sha256: str, kind: FileKind) -> StoredFile | None:
    return session.scalar(
        select(StoredFile).where(
            StoredFile.owner_id == owner_id,
            StoredFile.sha256 == sha256,
            StoredFile.kind == kind.value,
        )
    )


def total_bytes(session: Session, owner_id: str) -> int:
    return (
        session.scalar(
            select(func.coalesce(func.sum(StoredFile.byte_size), 0)).where(
                StoredFile.owner_id == owner_id
            )
        )
        or 0
    )


def add(session: Session, stored_file: StoredFile) -> StoredFile:
    session.add(stored_file)
    session.flush()
    return stored_file
