"""Task handler registry. Each phase registers its handlers here (e.g. Phase 5: extract_glyphs)."""

from collections.abc import Mapping

from app.db.models.enums import TaskType
from app.worker.runner import Handler

HANDLERS: Mapping[TaskType, Handler] = {}
