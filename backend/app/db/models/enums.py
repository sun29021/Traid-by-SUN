"""Enumerations stored as TEXT with CHECK constraints (DATABASE.md §3)."""

from enum import StrEnum


class UserRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"


class FileKind(StrEnum):
    REFERENCE = "reference"
    TARGET = "target"
    GLYPH = "glyph"
    MASK = "mask"
    BACKGROUND = "background"
    RESULT = "result"
    EXPORT = "export"
    BATCH_ZIP = "batch_zip"
    BACKUP = "backup"
    THUMBNAIL = "thumbnail"


class MimeType(StrEnum):
    JPEG = "image/jpeg"
    PNG = "image/png"
    TIFF = "image/tiff"
    ZIP = "application/zip"


class TaskType(StrEnum):
    EXTRACT_GLYPHS = "extract_glyphs"
    DETECT = "detect"
    RENDER = "render"
    BATCH_RUN = "batch_run"
    BATCH_EXPORT = "batch_export"
    BACKUP = "backup"


class TaskSubject(StrEnum):
    PROFILE = "profile"
    REFERENCE_IMAGE = "reference_image"
    EDIT_JOB = "edit_job"
    BATCH = "batch"
    SYSTEM = "system"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_active(self) -> bool:
        return self in (TaskStatus.QUEUED, TaskStatus.RUNNING)


class SurfaceType(StrEnum):
    PRINT = "print"
    PAINT = "paint"
    LASER_MARK = "laser_mark"
    ENGRAVED = "engraved"

    @property
    def blend_mode(self) -> str:
        """Ink model for print/paint, relief model for laser marks and engraving."""
        return "ink" if self in (SurfaceType.PRINT, SurfaceType.PAINT) else "relief"


class Alignment(StrEnum):
    AUTO = "auto"
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class SpacingMode(StrEnum):
    AUTO = "auto"
    MONOSPACE = "monospace"
    PROPORTIONAL = "proportional"


class EngineKind(StrEnum):
    GLYPH_TRANSPLANT = "glyph_transplant"


class ReferenceStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class GlyphStatus(StrEnum):
    AUTO = "auto"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


def check_in(column: str, values: type[StrEnum]) -> str:
    """SQL for `column IN ('a', 'b', …)` built from an enum, so DB and code never drift."""
    quoted = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({quoted})"
