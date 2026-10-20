"""Backups of the database and stored files (DATABASE.md §11).

A backup is `data/backups/traid-YYYYMMDD-HHMMSS.zip` holding a consistent copy of the
database (SQLite online backup API, safe while Traid runs), every stored file and a
`manifest.json`. After writing, the zipped database is re-opened and checked with
`PRAGMA integrity_check`; the result is kept next to the ZIP in `<name>.json`.
Traid never uploads backups anywhere.

Restore: stop Traid, move `data/` aside, unzip the backup into a new `data/` (the
archive holds `traid.db` and `files/`), start Traid. Migrations bring an older schema
up to date.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app import __version__
from app.core.errors import NotFound

BackupKind = Literal["manual", "pre-migrate"]
NAME_PATTERN = re.compile(r"^(traid|pre-migrate-[0-9a-z_]+)-\d{8}-\d{6}(-\d+)?\.zip$")
DB_FILENAME = "traid.db"
PRE_MIGRATE_KEEP = 3


@dataclass(frozen=True)
class BackupInfo:
    name: str
    kind: BackupKind
    byte_size: int
    created_at: str
    schema_revision: str | None
    file_count: int
    integrity_ok: bool | None


def backups_dir(data_dir: Path) -> Path:
    return data_dir / "backups"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unique_path(folder: Path, stem: str) -> Path:
    path = folder / f"{stem}.zip"
    n = 2
    while path.exists():
        path = folder / f"{stem}-{n}.zip"
        n += 1
    return path


def _integrity(db_path: Path) -> bool:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return bool(row and row[0] == "ok")
    finally:
        connection.close()


def create_backup(
    data_dir: Path,
    *,
    kind: BackupKind = "manual",
    schema_revision: str | None = None,
    retention: int = 10,
    now: datetime | None = None,
) -> BackupInfo:
    folder = backups_dir(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    stamp = moment.strftime("%Y%m%d-%H%M%S")
    prefix = "traid" if kind == "manual" else f"pre-migrate-{(schema_revision or 'none').lower()}"
    target = _unique_path(folder, f"{prefix}-{stamp}")
    files_dir = data_dir / "files"

    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        copy = Path(tmp) / DB_FILENAME
        source_db = data_dir / DB_FILENAME
        if source_db.is_file():
            source = sqlite3.connect(source_db)
            destination = sqlite3.connect(copy)
            try:
                source.backup(destination)  # consistent snapshot, even under writes
            finally:
                destination.close()
                source.close()
        stored = (
            sorted(p for p in files_dir.rglob("*") if p.is_file()) if files_dir.is_dir() else []
        )
        manifest = {
            "app_version": __version__,
            "schema_revision": schema_revision,
            "kind": kind,
            "created_at": moment.isoformat().replace("+00:00", "Z"),
            "file_count": len(stored),
            "db_sha256": _sha256(copy) if copy.is_file() else None,
        }
        partial = target.with_suffix(".partial")
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if copy.is_file():
                archive.write(copy, DB_FILENAME)
            for path in stored:
                archive.write(path, f"files/{path.relative_to(files_dir).as_posix()}")
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        partial.replace(target)

    ok = verify_backup(target)
    info = BackupInfo(
        name=target.name,
        kind=kind,
        byte_size=target.stat().st_size,
        created_at=str(manifest["created_at"]),
        schema_revision=schema_revision,
        file_count=len(stored),
        integrity_ok=ok,
    )
    target.with_suffix(".json").write_text(json.dumps(asdict(info), indent=2), encoding="utf-8")
    apply_retention(data_dir, retention)
    return info


def verify_backup(path: Path) -> bool:
    """Re-open the zipped database and run PRAGMA integrity_check."""
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as tmp:
        if DB_FILENAME not in archive.namelist():
            return False
        archive.extract(DB_FILENAME, tmp)
        return _integrity(Path(tmp) / DB_FILENAME)


def list_backups(data_dir: Path) -> list[BackupInfo]:
    folder = backups_dir(data_dir)
    if not folder.is_dir():
        return []
    items = []
    for path in folder.glob("*.zip"):
        if not NAME_PATTERN.fullmatch(path.name):
            continue
        sidecar = path.with_suffix(".json")
        if sidecar.is_file():
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            items.append(BackupInfo(**{**data, "byte_size": path.stat().st_size}))
        else:
            created = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            items.append(
                BackupInfo(
                    name=path.name,
                    kind="pre-migrate" if path.name.startswith("pre-migrate") else "manual",
                    byte_size=path.stat().st_size,
                    created_at=created.isoformat().replace("+00:00", "Z"),
                    schema_revision=None,
                    file_count=0,
                    integrity_ok=None,
                )
            )
    return sorted(items, key=lambda b: b.created_at, reverse=True)


def apply_retention(data_dir: Path, keep_manual: int) -> None:
    """Keep the newest `keep_manual` manual and the newest 3 pre-migration backups."""
    backups = list_backups(data_dir)
    for kind, keep in (("manual", keep_manual), ("pre-migrate", PRE_MIGRATE_KEEP)):
        for old in [b for b in backups if b.kind == kind][max(keep, 1) :]:
            path = backups_dir(data_dir) / old.name
            path.unlink(missing_ok=True)
            path.with_suffix(".json").unlink(missing_ok=True)


def backup_path(data_dir: Path, name: str) -> Path:
    """The ZIP for a listed backup name (strict pattern: no path traversal)."""
    if not NAME_PATTERN.fullmatch(name):
        raise NotFound("Backup not found")
    path = backups_dir(data_dir) / name
    if not path.is_file():
        raise NotFound("Backup not found")
    return path
