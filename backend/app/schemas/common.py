"""Shared response envelopes and field types (API.md §1.1, §1.5)."""

from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.core.clock import isoformat_utc

T = TypeVar("T")

# ISO-8601 UTC with millisecond precision and a Z suffix, e.g. 2026-10-20T14:03:11.123Z
UtcTimestamp = Annotated[datetime, PlainSerializer(isoformat_utc, return_type=str)]


class ApiModel(BaseModel):
    """Base for all API schemas: unknown fields are rejected; ORM objects can be read."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DataEnvelope(ApiModel, Generic[T]):
    data: T


class ListMeta(ApiModel):
    next_cursor: str | None
    count: int


class ListEnvelope(ApiModel, Generic[T]):
    data: list[T]
    meta: ListMeta
