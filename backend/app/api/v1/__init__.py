"""Version 1 of the Traid HTTP API (API.md)."""

from fastapi import APIRouter

from app.api.v1 import audit, system, tasks

router = APIRouter(prefix="/api/v1")
router.include_router(system.router)
router.include_router(tasks.router)
router.include_router(audit.router)
