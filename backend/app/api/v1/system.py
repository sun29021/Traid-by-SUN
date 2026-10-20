"""Health, system status and first-run Welcome (API.md §3.1, §3.2a)."""

from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import (
    CurrentUserDep,
    ModelRegistryDep,
    SessionDep,
    SettingsDep,
    TaskRunnerDep,
    allowed_query_params,
)
from app.schemas.common import DataEnvelope
from app.schemas.system import Health, OwnerSummary, SystemStatus, Welcome, WelcomeAccept
from app.services import owner as owner_service
from app.services import system as system_service

router = APIRouter(tags=["system"], dependencies=[Depends(allowed_query_params())])


@router.get("/health", response_model=DataEnvelope[Health])
def health() -> DataEnvelope[Health]:
    """Public liveness check. Returns no sensitive information."""
    return DataEnvelope(data=Health(status="ok", version=__version__))


@router.get("/system/status", response_model=DataEnvelope[SystemStatus])
def system_status(
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    runner: TaskRunnerDep,
    models: ModelRegistryDep,
) -> DataEnvelope[SystemStatus]:
    status = system_service.get_status(
        session, settings, models, owner_id=user.id, worker_running=runner.is_running
    )
    return DataEnvelope(data=status)


@router.get("/system/welcome", response_model=DataEnvelope[Welcome])
def get_welcome(user: CurrentUserDep) -> DataEnvelope[Welcome]:
    return DataEnvelope(
        data=Welcome(
            aup_accepted=user.aup_accepted,
            owner=OwnerSummary(display_name=user.display_name),
        )
    )


@router.post("/system/welcome", response_model=DataEnvelope[Welcome])
def accept_welcome(
    _: WelcomeAccept, user: CurrentUserDep, session: SessionDep
) -> DataEnvelope[Welcome]:
    owner = owner_service.accept_aup(session, user.id)
    return DataEnvelope(
        data=Welcome(aup_accepted=True, owner=OwnerSummary(display_name=owner.display_name))
    )
