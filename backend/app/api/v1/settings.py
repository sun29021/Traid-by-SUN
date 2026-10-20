"""Settings and backups (API.md §3.1, §3.10)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from pydantic import RootModel

from app.api.deps import AcceptedUserDep, SessionDep, SettingsDep, allowed_query_params
from app.db.models.enums import TaskSubject, TaskType
from app.schemas.common import ApiModel, DataEnvelope
from app.schemas.tasks import TaskOut
from app.services import app_settings
from app.services import backup as backup_service
from app.worker import queue

router = APIRouter(tags=["settings"], dependencies=[Depends(allowed_query_params())])


class SettingsPatch(RootModel[dict[str, Any]]):
    """Any subset of the setting keys."""


class BackupOut(ApiModel):
    name: str
    kind: str
    byte_size: int
    created_at: str
    schema_revision: str | None
    file_count: int
    integrity_ok: bool | None
    download_url: str


@router.get("/settings", response_model=DataEnvelope[dict[str, Any]])
def get_settings(_: AcceptedUserDep, session: SessionDep) -> DataEnvelope[dict[str, Any]]:
    """All settings with defaults applied."""
    return DataEnvelope(data=app_settings.all_settings(session))


@router.patch("/settings", response_model=DataEnvelope[dict[str, Any]])
def patch_settings(
    body: SettingsPatch, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[dict[str, Any]]:
    return DataEnvelope(data=app_settings.update(session, user.id, body.root))


@router.get("/system/backups", response_model=DataEnvelope[list[BackupOut]])
def list_backups(_: AcceptedUserDep, settings: SettingsDep) -> DataEnvelope[list[BackupOut]]:
    """Newest first, with the integrity check result of each."""
    return DataEnvelope(
        data=[
            BackupOut(**vars(b), download_url=f"/api/v1/system/backups/{b.name}")
            for b in backup_service.list_backups(settings.data_dir)
        ]
    )


@router.post(
    "/system/backups", response_model=DataEnvelope[TaskOut], status_code=status.HTTP_202_ACCEPTED
)
def start_backup(user: AcceptedUserDep, session: SessionDep) -> DataEnvelope[TaskOut]:
    task = queue.enqueue(
        session,
        owner_id=user.id,
        task_type=TaskType.BACKUP,
        subject_type=TaskSubject.SYSTEM,
        subject_id=None,
        payload={},
    )
    return DataEnvelope(data=TaskOut.model_validate(task))


@router.get("/system/backups/{name}", response_class=FileResponse)
def download_backup(name: str, _: AcceptedUserDep, settings: SettingsDep) -> FileResponse:
    path = backup_service.backup_path(settings.data_dir, name)
    return FileResponse(path, media_type="application/zip", filename=name)
