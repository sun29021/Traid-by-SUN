"""Housekeeping run at startup: remove derived files nothing refers to (DATABASE.md §8).

Conservative on purpose: only kinds Traid itself produces and can always produce again
(`mask`, `result`, `background`, `glyph`), only rows older than `min_age`, and only
when no table references them. Uploads, exports, ZIPs and backups are never swept.
A disk file is deleted only when no remaining row points at the same storage path.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select, union
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.db.models import Batch, EditJob, Glyph, ReferenceImage, StoredFile
from app.db.models.enums import FileKind
from app.storage.filestore import FileStore

logger = logging.getLogger("traid.maintenance")

SWEPT_KINDS = (FileKind.MASK, FileKind.RESULT, FileKind.BACKGROUND, FileKind.GLYPH)


def sweep_orphans(
    session: Session, store: FileStore, *, min_age: timedelta = timedelta(hours=1)
) -> int:
    referenced = union(
        select(ReferenceImage.file_id),
        select(Glyph.crop_file_id),
        select(EditJob.input_file_id),
        select(EditJob.result_file_id).where(EditJob.result_file_id.is_not(None)),
        select(EditJob.mask_file_id).where(EditJob.mask_file_id.is_not(None)),
        select(EditJob.background_file_id).where(EditJob.background_file_id.is_not(None)),
        select(Batch.export_file_id).where(Batch.export_file_id.is_not(None)),
    ).subquery()
    cutoff = utcnow() - min_age
    orphans = session.scalars(
        select(StoredFile).where(
            StoredFile.kind.in_([k.value for k in SWEPT_KINDS]),
            StoredFile.created_at < cutoff,
            StoredFile.id.not_in(select(referenced.c[0])),
        )
    ).all()
    removed = 0
    for stored in orphans:
        path = stored.storage_path
        session.delete(stored)
        session.flush()
        still_used = session.scalar(
            select(StoredFile.id).where(StoredFile.storage_path == path).limit(1)
        )
        if still_used is None:
            try:
                store.resolve(path).unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not delete an orphaned file", extra={"file_id": stored.id})
        removed += 1
    if removed:
        logger.info("Orphaned files removed", extra={"count": removed})
    return removed
