"""`profiles`, `reference_images` and `glyphs` (DATABASE.md §3.4-3.6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, id_column, updated_at_column
from app.db.models.enums import (
    Alignment,
    EngineKind,
    GlyphStatus,
    ReferenceStatus,
    SpacingMode,
    SurfaceType,
    check_in,
)
from app.db.types import JsonText, UtcDateTime

DEFAULT_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-/# "


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        UniqueConstraint("owner_id", "name"),
        CheckConstraint(check_in("surface_type", SurfaceType), name="surface_type"),
        CheckConstraint(check_in("alignment", Alignment), name="alignment"),
        CheckConstraint(check_in("spacing_mode", SpacingMode), name="spacing_mode"),
        CheckConstraint(check_in("engine", EngineKind), name="engine"),
        CheckConstraint("length(name) BETWEEN 1 AND 60", name="name_length"),
        CheckConstraint("length(charset) BETWEEN 1 AND 96", name="charset_length"),
        CheckConstraint("pattern_strict IN (0, 1)", name="pattern_strict"),
        CheckConstraint("use_auto_glyphs IN (0, 1)", name="use_auto_glyphs"),
        CheckConstraint("ready_threshold BETWEEN 1 AND 20", name="ready_threshold"),
        CheckConstraint("json_valid(learned_params)", name="learned_params_json"),
        Index(
            "ix_profiles_owner_id_archived_at_updated_at", "owner_id", "archived_at", "updated_at"
        ),
    )

    id: Mapped[str] = id_column()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(String(500))
    surface_type: Mapped[str] = mapped_column(String(16), default=SurfaceType.PRINT.value)
    charset: Mapped[str] = mapped_column(String(96), default=DEFAULT_CHARSET)
    token_pattern: Mapped[str | None] = mapped_column(String(200))
    pattern_strict: Mapped[int] = mapped_column(Integer, default=0)
    alignment: Mapped[str] = mapped_column(String(8), default=Alignment.AUTO.value)
    spacing_mode: Mapped[str] = mapped_column(String(16), default=SpacingMode.AUTO.value)
    ready_threshold: Mapped[int] = mapped_column(Integer, default=3)
    use_auto_glyphs: Mapped[int] = mapped_column(Integer, default=0)
    engine: Mapped[str] = mapped_column(String(32), default=EngineKind.GLYPH_TRANSPLANT.value)
    learned_params: Mapped[dict[str, Any]] = mapped_column(JsonText(), default=dict)
    typical_region: Mapped[dict[str, Any] | None] = mapped_column(JsonText())
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JsonText())
    archived_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ReferenceImage(Base):
    __tablename__ = "reference_images"
    __table_args__ = (
        UniqueConstraint("profile_id", "file_id"),
        CheckConstraint(check_in("status", ReferenceStatus), name="status"),
        CheckConstraint("known_text IS NULL OR length(known_text) <= 64", name="known_text"),
        Index("ix_reference_images_profile_id_created_at", "profile_id", "created_at"),
        Index("ix_reference_images_profile_id_status", "profile_id", "status"),
    )

    id: Mapped[str] = id_column()
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"))
    known_text: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=ReferenceStatus.PENDING.value)
    error_code: Mapped[str | None] = mapped_column(String(64))
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JsonText())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Glyph(Base):
    __tablename__ = "glyphs"
    __table_args__ = (
        CheckConstraint(check_in("status", GlyphStatus), name="status"),
        CheckConstraint("length(char) = 1", name="char_length"),
        CheckConstraint("cap_height_px > 0", name="cap_height_px"),
        CheckConstraint("stroke_width_px >= 0", name="stroke_width_px"),
        CheckConstraint("blur_sigma >= 0", name="blur_sigma"),
        CheckConstraint("noise_sigma >= 0", name="noise_sigma"),
        CheckConstraint("bg_luma BETWEEN 0 AND 1", name="bg_luma"),
        CheckConstraint("contrast BETWEEN 0 AND 1", name="contrast"),
        CheckConstraint("angle_deg BETWEEN -90 AND 90", name="angle_deg"),
        CheckConstraint(
            "light_dir_deg IS NULL OR (light_dir_deg >= 0 AND light_dir_deg < 360)",
            name="light_dir_deg",
        ),
        CheckConstraint("ocr_confidence BETWEEN 0 AND 1", name="ocr_confidence"),
        CheckConstraint("quality_score BETWEEN 0 AND 1", name="quality_score"),
        CheckConstraint(
            "use_count >= 0 AND accept_count >= 0 AND reject_count >= 0", name="counters"
        ),
        CheckConstraint("json_valid(source_quad)", name="source_quad_json"),
        CheckConstraint(
            "(source_reference_id IS NOT NULL) + (source_job_id IS NOT NULL) <= 1",
            name="one_source",
        ),
        Index(
            "ix_glyphs_profile_id_char_status_quality_score",
            "profile_id",
            "char",
            "status",
            "quality_score",
        ),
        Index("ix_glyphs_source_reference_id", "source_reference_id"),
        Index("ix_glyphs_source_job_id", "source_job_id"),
    )

    id: Mapped[str] = id_column()
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    source_reference_id: Mapped[str | None] = mapped_column(
        ForeignKey("reference_images.id", ondelete="CASCADE")
    )
    # Glyph harvested from an accepted job's original pixels (Phase 11).
    source_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("edit_jobs.id", ondelete="SET NULL")
    )
    crop_file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"))
    char: Mapped[str] = mapped_column(String(1))
    status: Mapped[str] = mapped_column(String(16), default=GlyphStatus.AUTO.value)
    source_quad: Mapped[list[list[float]]] = mapped_column(JsonText())
    cap_height_px: Mapped[float] = mapped_column(Float)
    stroke_width_px: Mapped[float] = mapped_column(Float)
    blur_sigma: Mapped[float] = mapped_column(Float)
    noise_sigma: Mapped[float] = mapped_column(Float)
    ink_color: Mapped[str] = mapped_column(String(7))
    bg_luma: Mapped[float] = mapped_column(Float)
    contrast: Mapped[float] = mapped_column(Float)
    angle_deg: Mapped[float] = mapped_column(Float)
    light_dir_deg: Mapped[float | None] = mapped_column(Float)
    ocr_confidence: Mapped[float] = mapped_column(Float)
    quality_score: Mapped[float] = mapped_column(Float)
    baseline_y: Mapped[float | None] = mapped_column(Float)  # text baseline in the crop (px)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    accept_count: Mapped[int] = mapped_column(Integer, default=0)
    reject_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
