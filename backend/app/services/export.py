"""Exporting an accepted job (PRD FR-E11, API.md §3.6).

Same format, dimensions, DPI and ICC profile as the input unless the owner asks for
another format. JPEG is re-encoded with the source's own quantisation tables (or a
fixed quality, per setting). Camera EXIF is never copied. Unless the owner turned it
off, the file carries a Traid edit marker in its metadata (PRD D-06).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import PurePath

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app import __version__
from app.core.clock import utcnow
from app.core.errors import NotFound
from app.db.models import EditJob
from app.db.models.enums import FileKind, JobStatus, MimeType
from app.db.transaction import transaction
from app.engine.io import decode_image, encode_image
from app.engine.metadata import ImageDetails
from app.engine.types import DecodedImage, ImageFormat
from app.repositories import files as files_repo
from app.schemas.jobs import ExportMetadata, ExportOut, ExportRequest
from app.services import app_settings, audit
from app.services.audit import AuditAction
from app.services.files import store_generated_file
from app.services.jobs import InvalidState, get_owned
from app.services.mappers import file_ref
from app.storage.filestore import FileStore

_FORMATS: dict[str, ImageFormat] = {"jpeg": "JPEG", "png": "PNG", "tiff": "TIFF"}
_MIME: dict[ImageFormat, MimeType] = {
    "JPEG": MimeType.JPEG,
    "PNG": MimeType.PNG,
    "TIFF": MimeType.TIFF,
}
_EXTENSION: dict[ImageFormat, str] = {"JPEG": ".jpg", "PNG": ".png", "TIFF": ".tif"}
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def marker_text(engine_version: str | None) -> str:
    return f"Traid {__version__} — edited image ({engine_version or 'glyph_transplant'})"


def _safe(value: str, fallback: str) -> str:
    cleaned = _UNSAFE.sub("_", value).strip("._")
    return cleaned[:80] or fallback


def download_name(
    pattern: str, *, template: str | None, token: str | None, fmt: ImageFormat
) -> str:
    stem = PurePath(template).stem if template else "image"
    name = (
        pattern.replace("{template}", _safe(stem, "image"))
        .replace("{token}", _safe(token or "", "token"))
        .replace("{date}", utcnow().strftime("%Y%m%d"))
        .replace("{n}", "1")
    )
    return _safe(name, "traid_export") + _EXTENSION[fmt]


def _clean(value: str | None, *, multiline: bool = False) -> str:
    """Trim and drop control characters (newlines kept only in long text)."""
    text = (value or "").strip()
    allowed = {"\n"} if multiline else set()
    return "".join(c for c in text if c.isprintable() or c in allowed)


def image_details(session: Session, metadata: ExportMetadata | None) -> ImageDetails:
    """The request's fields; author and copyright fall back to the saved defaults
    (None = use the default, "" = leave empty)."""
    m = metadata or ExportMetadata()
    author = (
        m.author
        if m.author is not None
        else str(app_settings.get(session, "export.default_author"))
    )
    copyright_text = (
        m.copyright
        if m.copyright is not None
        else str(app_settings.get(session, "export.default_copyright"))
    )
    keywords = tuple(dict.fromkeys(k for k in (_clean(k) for k in m.keywords or []) if k))
    return ImageDetails(
        title=_clean(m.title),
        description=_clean(m.description, multiline=True),
        author=_clean(author),
        copyright=_clean(copyright_text),
        keywords=keywords,
        comment=_clean(m.comment, multiline=True),
    )


def jpeg_quality(mode: str) -> int | None:
    """`match_source` → None (source tables); `fixed:<60-100>` → that quality."""
    if mode.startswith("fixed:"):
        value = int(mode.split(":", 1)[1])
        if 60 <= value <= 100:
            return value
    return None


@dataclass(frozen=True)
class EncodedExport:
    data: bytes
    name: str
    fmt: ImageFormat
    decoded: DecodedImage
    quality: int | None
    marker: bool


def encode_export(
    session: Session,
    store: FileStore,
    job: EditJob,
    *,
    format_choice: str | None = None,
    filename_pattern: str | None = None,
    metadata: ExportMetadata | None = None,
) -> EncodedExport:
    """The accepted job's result encoded like its input (shared by single and ZIP export)."""
    if job.status != JobStatus.ACCEPTED.value:
        raise InvalidState("Only accepted results can be exported")
    source = files_repo.get(session, job.owner_id, job.input_file_id)
    result = (
        files_repo.get(session, job.owner_id, job.result_file_id) if job.result_file_id else None
    )
    if source is None or result is None:
        raise NotFound("The job's files are missing")

    decoded = decode_image(store.read_bytes(source.storage_path))
    with Image.open(io.BytesIO(store.read_bytes(result.storage_path))) as image:
        rendered = np.asarray(image.convert("RGB")).copy()

    choice = format_choice or str(app_settings.get(session, "export.default_format"))
    fmt: ImageFormat = decoded.format if choice == "original" else _FORMATS[choice]
    quality = jpeg_quality(str(app_settings.get(session, "export.jpeg_quality_mode")))
    marker = (
        marker_text(job.engine_version)
        if app_settings.get(session, "export.metadata_marker")
        else None
    )
    details = image_details(session, metadata)
    data = encode_image(
        rendered, decoded, fmt=fmt, jpeg_quality=quality, marker=marker, details=details
    )
    pattern = filename_pattern or str(app_settings.get(session, "export.filename_pattern"))
    name = download_name(pattern, template=source.original_name, token=job.new_text, fmt=fmt)
    return EncodedExport(data, name, fmt, decoded, quality, marker is not None)


def export_job(
    session: Session, store: FileStore, owner_id: str, job_id: str, body: ExportRequest
) -> ExportOut:
    with transaction(session):
        job = get_owned(session, owner_id, job_id)
        out = encode_export(
            session,
            store,
            job,
            format_choice=body.format,
            filename_pattern=body.filename_pattern,
            metadata=body.metadata,
        )
        stored = store_generated_file(
            session,
            store,
            owner_id=owner_id,
            data=out.data,
            kind=FileKind.EXPORT,
            mime_type=_MIME[out.fmt],
            width=out.decoded.width,
            height=out.decoded.height,
            dpi=out.decoded.dpi,
            has_icc=out.decoded.icc_profile is not None,
            jpeg_quality_est=(
                (out.quality or out.decoded.jpeg_quality_est) if out.fmt == "JPEG" else None
            ),
            original_name=out.name,
        )
        job.exported_at = utcnow()
        audit.record(
            session,
            user_id=owner_id,
            action=AuditAction.JOB_EXPORTED,
            subject=("edit_job", job.id),
            details={"format": out.fmt, "file_id": stored.id, "marker": out.marker},
        )
    return ExportOut(file=file_ref(stored), download_name=out.name)
