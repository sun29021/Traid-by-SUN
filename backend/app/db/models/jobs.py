"""`batches`, `edit_jobs` and `edit_job_glyphs` (DATABASE.md §3.7-3.9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, id_column, updated_at_column
from app.db.models.enums import BatchStatus, GlyphSourceKind, JobStatus, QualityStatus, check_in
from app.db.types import JsonText, UtcDateTime


class Batch(Base):
    """Many tokens rendered from one template job (used from Phase 12)."""

    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint("owner_id", "client_request_id"),
        CheckConstraint(check_in("status", BatchStatus), name="status"),
        CheckConstraint("total_count BETWEEN 1 AND 1000", name="total_count"),
        CheckConstraint("name IS NULL OR length(name) <= 80", name="name_length"),
        Index("ix_batches_owner_id_created_at", "owner_id", "created_at"),
    )

    id: Mapped[str] = id_column()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    template_job_id: Mapped[str] = mapped_column(
        ForeignKey("edit_jobs.id", ondelete="RESTRICT", use_alter=True)
    )
    name: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default=BatchStatus.QUEUED.value)
    total_count: Mapped[int] = mapped_column(Integer)
    export_file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    client_request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class EditJob(Base):
    __tablename__ = "edit_jobs"
    __table_args__ = (
        CheckConstraint(check_in("status", JobStatus), name="status"),
        CheckConstraint(
            "quality_overall IS NULL OR " + check_in("quality_overall", QualityStatus),
            name="quality_overall",
        ),
        CheckConstraint(
            "original_text IS NULL OR length(original_text) <= 64", name="original_text"
        ),
        CheckConstraint("new_text IS NULL OR length(new_text) <= 64", name="new_text"),
        CheckConstraint(
            "reject_reason IS NULL OR length(reject_reason) <= 300", name="reject_reason"
        ),
        CheckConstraint("json_valid(params)", name="params_json"),
        Index("ix_edit_jobs_owner_id_batch_id_created_at", "owner_id", "batch_id", "created_at"),
        Index(
            "ix_edit_jobs_owner_id_profile_id_status_created_at",
            "owner_id",
            "profile_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_edit_jobs_batch_id_quality_overall_status", "batch_id", "quality_overall", "status"
        ),
        Index("ix_edit_jobs_owner_id_new_text", "owner_id", "new_text"),
        Index("ix_edit_jobs_owner_id_original_text", "owner_id", "original_text"),
    )

    id: Mapped[str] = id_column()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"))
    input_file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.UPLOADED.value)
    regions: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonText())
    selected_region_id: Mapped[str | None] = mapped_column(String(16))
    selected_quad: Mapped[list[list[float]] | None] = mapped_column(JsonText())
    original_text: Mapped[str | None] = mapped_column(String(64))
    new_text: Mapped[str | None] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JsonText(), default=dict)
    geometry: Mapped[dict[str, Any] | None] = mapped_column(JsonText())
    background_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )
    mask_file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    result_file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    quality: Mapped[dict[str, Any] | None] = mapped_column(JsonText())
    quality_overall: Mapped[str | None] = mapped_column(String(8))
    engine_version: Mapped[str | None] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    reject_reason: Mapped[str | None] = mapped_column(String(300))
    error_code: Mapped[str | None] = mapped_column(String(64))
    accepted_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    exported_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class EditJobGlyph(Base):
    """Which bank glyph was used at each position of the job's current render."""

    __tablename__ = "edit_job_glyphs"
    __table_args__ = (
        CheckConstraint(check_in("source", GlyphSourceKind), name="source"),
        CheckConstraint("position >= 0", name="position"),
        Index("ix_edit_job_glyphs_glyph_id", "glyph_id"),
    )

    job_id: Mapped[str] = mapped_column(
        ForeignKey("edit_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    glyph_id: Mapped[str | None] = mapped_column(ForeignKey("glyphs.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(16))
