"""`app_settings` table (DATABASE.md §3.12)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, updated_at_column
from app.db.types import JsonText


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (CheckConstraint("json_valid(value)", name="value_json"),)

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JsonText())
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = updated_at_column()
