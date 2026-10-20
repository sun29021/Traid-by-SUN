"""Task handler registry. Handlers get their dependencies through a closure."""

from collections.abc import Mapping
from functools import partial

from app.db.models.enums import TaskType
from app.services.extraction import ExtractionDeps, handle_extract_glyphs
from app.services.job_engine import JobDeps, handle_detect, handle_render
from app.worker.runner import Handler


def create_handlers(extraction: ExtractionDeps, jobs: JobDeps) -> Mapping[TaskType, Handler]:
    return {
        TaskType.EXTRACT_GLYPHS: partial(handle_extract_glyphs, extraction),
        TaskType.DETECT: partial(handle_detect, jobs),
        TaskType.RENDER: partial(handle_render, jobs),
    }
