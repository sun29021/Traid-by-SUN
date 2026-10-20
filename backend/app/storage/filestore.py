"""Content-addressed file storage inside `<data_dir>/files` (ARCHITECTURE.md §14).

Files live at `ab/cd/<sha256>.<ext>`. Client file names are never used as paths,
writes are atomic (temp file + rename), and every read is confined to the root.
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import tempfile
from pathlib import Path, PurePosixPath

from app.core.errors import ErrorCode, StorageFailure
from app.db.models.enums import MimeType

EXTENSIONS: dict[MimeType, str] = {
    MimeType.JPEG: "jpg",
    MimeType.PNG: "png",
    MimeType.TIFF: "tif",
    MimeType.ZIP: "zip",
}
_STORAGE_PATH = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}\.(jpg|png|tif|zip)$")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
MAX_NAME_LENGTH = 255


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_original_name(name: str | None) -> str | None:
    """Display-only file name: last path component, no control characters, ≤ 255 chars."""
    if not name:
        return None
    base = re.split(r"[\\/]", name)[-1]
    cleaned = _CONTROL_CHARS.sub("", base).strip()
    return cleaned[:MAX_NAME_LENGTH] or None


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def write(self, data: bytes, sha256: str, mime_type: MimeType) -> str:
        """Store `data` (whose hash is `sha256`) and return its relative storage path."""
        storage_path = f"{sha256[:2]}/{sha256[2:4]}/{sha256}.{EXTENSIONS[mime_type]}"
        target = self.resolve(storage_path)
        if target.is_file() and target.stat().st_size == len(data):
            return storage_path  # identical content already stored

        tmp_name: str | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
                tmp_name = tmp.name
                tmp.write(data)
                tmp.flush()
                os.fsync(tmp.fileno())
            Path(tmp_name).replace(target)
            tmp_name = None
        except OSError as exc:
            code = ErrorCode.DISK_FULL if exc.errno == errno.ENOSPC else ErrorCode.STORAGE_ERROR
            message = (
                "Not enough disk space" if code is ErrorCode.DISK_FULL else "Could not save file"
            )
            raise StorageFailure(message, code=code) from exc
        finally:
            if tmp_name is not None:
                Path(tmp_name).unlink(missing_ok=True)
        return storage_path

    def resolve(self, storage_path: str) -> Path:
        """Absolute path for a stored file; rejects anything that is not a storage path."""
        if not _STORAGE_PATH.fullmatch(storage_path):
            raise StorageFailure("Invalid storage path")
        path = (self.root / PurePosixPath(storage_path)).resolve()
        if not path.is_relative_to(self.root):
            raise StorageFailure("Invalid storage path")
        return path

    def read_bytes(self, storage_path: str) -> bytes:
        try:
            return self.resolve(storage_path).read_bytes()
        except FileNotFoundError as exc:
            raise StorageFailure("Stored file is missing") from exc
