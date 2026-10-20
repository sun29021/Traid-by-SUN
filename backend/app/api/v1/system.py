"""Health and system endpoints (API.md §3.1)."""

from fastapi import APIRouter

from app import __version__
from app.schemas.common import DataEnvelope
from app.schemas.system import Health

router = APIRouter(tags=["system"])


@router.get("/health", response_model=DataEnvelope[Health])
def health() -> DataEnvelope[Health]:
    """Public liveness check. Returns no sensitive information."""
    return DataEnvelope(data=Health(status="ok", version=__version__))
