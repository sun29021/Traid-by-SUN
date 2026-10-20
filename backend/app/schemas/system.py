"""System schemas."""

from typing import Literal

from app.schemas.common import ApiModel


class Health(ApiModel):
    status: Literal["ok"]
    version: str
