"""Request dependencies: DB session, current user, Acceptable Use gate, query helpers.

Traid runs without sign-in (PRD D-03): the current user is always the single local
owner created at startup. Routers still depend on `current_user` so ownership checks
stay in place and a future sign-in only has to change this module.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, TypeVar

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorCode, Forbidden, Unauthorized, ValidationFailed
from app.db.engine import Database
from app.engine.models import ModelRegistry
from app.repositories import users as users_repo
from app.storage.filestore import FileStore
from app.worker.runner import TaskRunner

E = TypeVar("E", bound=StrEnum)


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_database(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def get_file_store(request: Request) -> FileStore:
    store: FileStore = request.app.state.file_store
    return store


def get_task_runner(request: Request) -> TaskRunner:
    runner: TaskRunner = request.app.state.task_runner
    return runner


def get_model_registry(request: Request) -> ModelRegistry:
    registry: ModelRegistry = request.app.state.models
    return registry


def get_session(db: Annotated[Database, Depends(get_database)]) -> Iterator[Session]:
    with db.session_factory() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
SessionDep = Annotated[Session, Depends(get_session)]
TaskRunnerDep = Annotated[TaskRunner, Depends(get_task_runner)]
ModelRegistryDep = Annotated[ModelRegistry, Depends(get_model_registry)]


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: str
    display_name: str
    aup_accepted: bool


def current_user(request: Request, session: SessionDep) -> CurrentUser:
    user = users_repo.get(session, request.app.state.owner_id)
    if user is None or not user.is_active:
        raise Unauthorized("The local owner account is missing; restart Traid")
    return CurrentUser(
        id=user.id,
        role=user.role,
        display_name=user.display_name,
        aup_accepted=user.aup_accepted_at is not None,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]


def require_aup(user: CurrentUserDep) -> CurrentUser:
    if not user.aup_accepted:
        raise Forbidden(
            "Acknowledge the Acceptable Use notice first",
            details={"reason": "aup_required"},
        )
    return user


AcceptedUserDep = Annotated[CurrentUser, Depends(require_aup)]


def allowed_query_params(*names: str) -> Callable[[Request], None]:
    """Reject unknown query parameters with 422 (API.md §1.5)."""
    allowed = frozenset(names)

    def check(request: Request) -> None:
        unknown = sorted(set(request.query_params) - allowed)
        if unknown:
            raise ValidationFailed(
                "Unknown query parameter",
                details={
                    "fields": [
                        {
                            "path": name,
                            "code": ErrorCode.VALIDATION_FAILED.value,
                            "message": "Unknown query parameter",
                        }
                        for name in unknown
                    ]
                },
            )

    return check


def parse_csv_enum(value: str | None, enum: type[E], field: str) -> list[E] | None:
    """`a,b,c` → [Enum.A, …]; None when absent; 422 naming the bad value otherwise."""
    if value is None or not value.strip():
        return None
    items: list[E] = []
    for raw in value.split(","):
        try:
            items.append(enum(raw.strip()))
        except ValueError as exc:
            allowed = ", ".join(member.value for member in enum)
            raise ValidationFailed(
                f"Invalid {field} value",
                details={
                    "fields": [
                        {
                            "path": field,
                            "code": ErrorCode.VALIDATION_FAILED.value,
                            "message": f"'{raw.strip()}' is not one of: {allowed}",
                        }
                    ]
                },
            ) from exc
    return items
