"""Batch schemas (API.md §2 Batch, §3.7)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.db.models.enums import BatchStatus
from app.schemas.common import ApiModel, UtcTimestamp
from app.schemas.jobs import EditJobOut
from app.schemas.profiles import FileRef
from app.schemas.tasks import TaskOut

Value = Annotated[str, StringConstraints(max_length=1000)]


class BatchValidate(ApiModel):
    profile_id: Annotated[str, StringConstraints(max_length=36)]
    template_job_id: Annotated[str, StringConstraints(max_length=36)] | None = None
    values: Annotated[list[Value], Field(max_length=1000)]


class InvalidValue(ApiModel):
    value: str
    code: Literal["CHAR_NOT_IN_CHARSET", "PATTERN_MISMATCH", "GLYPH_MISSING", "VALIDATION_FAILED"]
    message: str


class BatchValidation(ApiModel):
    valid: list[str]
    invalid: list[InvalidValue]
    duplicates: list[str]


class BatchCreate(ApiModel):
    template_job_id: Annotated[str, StringConstraints(max_length=36)]
    values: Annotated[list[Value], Field(min_length=1, max_length=1000)]
    name: Annotated[str, StringConstraints(max_length=80)] | None = None
    client_request_id: Annotated[str, StringConstraints(max_length=64)] | None = None


class BatchCounts(ApiModel):
    pending: int
    rendered: int
    warn: int
    failed: int
    accepted: int
    rejected: int


class BatchOut(ApiModel):
    id: str
    profile_id: str
    template_job_id: str
    name: str | None
    status: BatchStatus
    total_count: int
    counts: BatchCounts
    export_file: FileRef | None
    created_at: UtcTimestamp
    finished_at: UtcTimestamp | None


class BatchStarted(ApiModel):
    batch: BatchOut
    task: TaskOut


class AcceptedCount(ApiModel):
    accepted: int


class BatchItems(ApiModel):
    items: list[EditJobOut]
