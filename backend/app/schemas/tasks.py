"""Task schema (API.md §1.7)."""

from app.db.models.enums import TaskStatus, TaskSubject, TaskType
from app.schemas.common import ApiModel, UtcTimestamp


class TaskOut(ApiModel):
    id: str
    type: TaskType
    subject_type: TaskSubject
    subject_id: str | None
    status: TaskStatus
    progress: float
    message: str | None
    error_code: str | None
    created_at: UtcTimestamp
    started_at: UtcTimestamp | None
    finished_at: UtcTimestamp | None
