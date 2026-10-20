"""Settings, backups, pre-migration backup and the orphan sweep (Phase 13)."""

import io
import sqlite3
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.engine import Database, alembic_config
from app.db.models import StoredFile
from app.db.models.enums import FileKind, MimeType
from app.services import backup as backups
from app.services.backup_task import backup_before_migration
from app.services.files import store_generated_png
from app.services.maintenance import sweep_orphans
from app.storage.filestore import FileStore
from app.worker.runner import TaskRunner
from tests.factories import png_bytes
from tests.fixtures.generate import make_token_image


def _run_tasks(client: TestClient) -> None:
    runner: TaskRunner = client.app.state.task_runner  # type: ignore[attr-defined]
    while runner.run_once():
        pass


# ---------------------------------------------------------------- settings


def test_settings_defaults_update_and_audit(accepted_client: TestClient) -> None:
    defaults = accepted_client.get("/api/v1/settings").json()["data"]
    assert defaults["export.default_format"] == "original"
    assert defaults["export.metadata_marker"] is True

    response = accepted_client.patch(
        "/api/v1/settings",
        json={"export.default_format": "png", "export.jpeg_quality_mode": "fixed:90"},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["export.default_format"] == "png"
    assert data["export.jpeg_quality_mode"] == "fixed:90"
    events = accepted_client.get("/api/v1/audit?action=settings.updated").json()["data"]
    assert events[0]["details"]["keys"] == ["export.default_format", "export.jpeg_quality_mode"]


@pytest.mark.parametrize(
    "body",
    [
        {"export.default_format": "gif"},
        {"export.filename_pattern": "../evil"},
        {"export.filename_pattern": "{template}_{secret}"},
        {"export.metadata_marker": "yes"},
        {"export.jpeg_quality_mode": "fixed:30"},
        {"storage.backup_retention": 0},
        {"storage.backup_retention": True},
        {"unknown.key": 1},
    ],
)
def test_invalid_settings_are_rejected(
    accepted_client: TestClient, body: dict[str, object]
) -> None:
    response = accepted_client.patch("/api/v1/settings", json=body)

    assert response.status_code == 422, body
    assert accepted_client.get("/api/v1/settings").json()["data"]["storage.backup_retention"] == 10


# ---------------------------------------------------------------- backups


def test_backup_task_list_download_and_integrity(
    accepted_client: TestClient, settings: Settings
) -> None:
    response = accepted_client.post("/api/v1/system/backups")
    assert response.status_code == 202
    assert response.json()["data"]["type"] == "backup"
    _run_tasks(accepted_client)

    listed = accepted_client.get("/api/v1/system/backups").json()["data"]
    assert len(listed) == 1
    backup = listed[0]
    assert backup["kind"] == "manual" and backup["integrity_ok"] is True
    assert backup["schema_revision"] == "0005_edit_jobs"

    download = accepted_client.get(backup["download_url"])
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = archive.namelist()
        assert "traid.db" in names and "manifest.json" in names
    events = accepted_client.get("/api/v1/audit?action=backup.created").json()["data"]
    assert events[0]["details"]["integrity_ok"] is True


def test_backup_names_cannot_escape_the_folder(accepted_client: TestClient) -> None:
    for name in ("..%2Ftraid.db", "traid.db", "traid-20260101-000000.zip"):
        assert accepted_client.get(f"/api/v1/system/backups/{name}").status_code == 404


def test_retention_keeps_the_newest(settings: Settings) -> None:
    data_dir = settings.data_dir
    (data_dir / "files").mkdir(parents=True)
    for day in range(1, 5):
        backups.create_backup(data_dir, retention=2, now=datetime(2026, 10, day, tzinfo=UTC))

    names = [b.name for b in backups.list_backups(data_dir)]
    assert names == ["traid-20261004-000000.zip", "traid-20261003-000000.zip"]


def test_backup_restores_to_a_working_database(settings: Settings, tmp_path: Path) -> None:
    db = Database.from_settings(settings)
    try:
        command.upgrade(alembic_config(db.engine), "head")
    finally:
        db.dispose()
    store = FileStore(settings.data_dir / "files")
    store.write(b"hello", "a" * 64, MimeType.PNG)

    info = backups.create_backup(settings.data_dir, schema_revision="0005_edit_jobs")

    restored = tmp_path / "restored"
    with zipfile.ZipFile(backups.backups_dir(settings.data_dir) / info.name) as archive:
        archive.extractall(restored)
    with sqlite3.connect(restored / "traid.db") as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert "edit_jobs" in tables
    assert (restored / "files" / "aa" / "aa" / f"{'a' * 64}.png").read_bytes() == b"hello"
    assert info.file_count == 1


def test_pre_migration_backup_only_when_upgrading(settings: Settings) -> None:
    db = Database.from_settings(settings)
    try:
        assert backup_before_migration(db, settings.data_dir) is None  # no database yet
        command.upgrade(alembic_config(db.engine), "0004_profiles_glyphs")
        path = backup_before_migration(db, settings.data_dir)
        assert path is not None and path.name.startswith("pre-migrate-0004_profiles_glyphs-")
        assert backups.verify_backup(path)
        command.upgrade(alembic_config(db.engine), "head")
        assert backup_before_migration(db, settings.data_dir) is None  # up to date
    finally:
        db.dispose()


# ---------------------------------------------------------------- orphan sweep


def test_sweep_removes_only_old_unreferenced_derived_files(settings: Settings) -> None:
    db = Database.from_settings(settings)
    try:
        command.upgrade(alembic_config(db.engine), "head")
        store = FileStore(settings.data_dir / "files")
        image = png_bytes(make_token_image("A7", "print", seed=1, canvas=(64, 48)).image)
        with db.session() as session:
            mask = store_generated_png(
                session,
                store,
                owner_id=_owner(session),
                data=image,
                kind=FileKind.MASK,
                width=64,
                height=48,
            )
            export = store_generated_png(
                session,
                store,
                owner_id=_owner(session),
                data=image,
                kind=FileKind.EXPORT,
                width=64,
                height=48,
            )
            mask_id, export_id, path = mask.id, export.id, mask.storage_path
        with db.session() as session:
            assert sweep_orphans(session, store) == 0  # too new
        with db.session() as session:
            assert sweep_orphans(session, store, min_age=timedelta(0)) == 1
        with db.session() as session:
            assert session.get(StoredFile, mask_id) is None
            assert session.get(StoredFile, export_id) is not None  # exports are kept
        # The export row still points at the same bytes, so the disk file stays.
        assert store.resolve(path).is_file()
    finally:
        db.dispose()


def _owner(session: object) -> str:
    from app.services.owner import ensure_local_owner

    return ensure_local_owner(session).id  # type: ignore[arg-type]
