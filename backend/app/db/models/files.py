"""`files` table — registry of every stored binary (DATABASE.md §3.3)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, id_column
from app.db.models.enums import FileKind, MimeType, check_in


class StoredFile(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("owner_id", "sha256", "kind"),
        CheckConstraint(check_in("kind", FileKind), name="kind"),
        CheckConstraint(check_in("mime_type", MimeType), name="mime_type"),
        CheckConstraint("byte_size > 0", name="byte_size"),
        CheckConstraint("width IS NULL OR width > 0", name="width"),
        CheckConstraint("height IS NULL OR height > 0", name="height"),
        CheckConstraint("has_icc IN (0, 1)", name="has_icc"),
        CheckConstraint(
            "jpeg_quality_est IS NULL OR jpeg_quality_est BETWEEN 1 AND 100",
            name="jpeg_quality_est",
        ),
        CheckConstraint("length(sha256) = 64", name="sha256_length"),
    )

    id: Mapped[str] = id_column()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    sha256: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    mime_type: Mapped[str] = mapped_column(String(32))
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    dpi_x: Mapped[float | None] = mapped_column(Float)
    dpi_y: Mapped[float | None] = mapped_column(Float)
    has_icc: Mapped[int] = mapped_column(Integer, default=0)
    jpeg_quality_est: Mapped[int | None] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = created_at_column()
