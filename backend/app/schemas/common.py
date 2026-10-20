"""Shared response envelopes (API.md §1.1)."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiModel(BaseModel):
    """Base for all API schemas: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class DataEnvelope(ApiModel, Generic[T]):
    data: T
