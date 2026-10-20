"""System schemas (API.md §3.1, §3.2a)."""

from typing import Literal

from app.schemas.common import ApiModel


class Health(ApiModel):
    status: Literal["ok"]
    version: str


class OwnerSummary(ApiModel):
    display_name: str


class Welcome(ApiModel):
    aup_accepted: bool
    owner: OwnerSummary


class WelcomeAccept(ApiModel):
    accept_aup: Literal[True]


class WorkerStatus(ApiModel):
    running: bool
    queued: int


class StorageStatus(ApiModel):
    data_dir: str
    stored_bytes: int
    disk_free_bytes: int
    disk_total_bytes: int


class ModelStatus(ApiModel):
    name: str
    version: str
    loaded: bool
    checksum_ok: bool


class EngineStatus(ApiModel):
    ready: bool
    device: str | None
    models: list[ModelStatus]


class SystemStatus(ApiModel):
    version: str
    schema_revision: str | None
    worker: WorkerStatus
    storage: StorageStatus
    engine: EngineStatus
