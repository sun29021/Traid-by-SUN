"""`users` and `sessions` tables (DATABASE.md §3.1, §3.2)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, id_column, updated_at_column
from app.db.models.enums import UserRole, check_in
from app.db.types import UtcDateTime


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(check_in("role", UserRole), name="role"),
        CheckConstraint("is_active IN (0, 1)", name="is_active"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count"),
        CheckConstraint("length(username) BETWEEN 3 AND 32", name="username_length"),
        CheckConstraint("username = lower(username)", name="username_lowercase"),
        CheckConstraint("length(display_name) BETWEEN 1 AND 60", name="display_name_length"),
    )

    id: Mapped[str] = id_column()
    username: Mapped[str] = mapped_column(String(32), unique=True)
    display_name: Mapped[str] = mapped_column(String(60))
    # NULL in local mode (no sign-in, PRD D-03).
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default=UserRole.OWNER.value)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime())
    aup_accepted_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    last_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class UserSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id_revoked_at", "user_id", "revoked_at"),)

    id: Mapped[str] = id_column()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_secret: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_column()
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime())
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    user_agent: Mapped[str | None] = mapped_column(String(200))
