"""Style Profiles, reference images and the glyph bank (DATABASE.md §3.4-3.6).

Revision ID: 0004_profiles_glyphs
Revises: 0003_local_owner
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_profiles_glyphs"
down_revision: str | None = "0003_local_owner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.String(24)  # ISO-8601 UTC text, see app.db.types.UtcDateTime


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("surface_type", sa.String(16), nullable=False),
        sa.Column("charset", sa.String(96), nullable=False),
        sa.Column("token_pattern", sa.String(200), nullable=True),
        sa.Column("pattern_strict", sa.Integer(), nullable=False),
        sa.Column("alignment", sa.String(8), nullable=False),
        sa.Column("spacing_mode", sa.String(16), nullable=False),
        sa.Column("ready_threshold", sa.Integer(), nullable=False),
        sa.Column("use_auto_glyphs", sa.Integer(), nullable=False),
        sa.Column("engine", sa.String(32), nullable=False),
        sa.Column("learned_params", sa.Text(), nullable=False),
        sa.Column("typical_region", sa.Text(), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("archived_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_profiles"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_profiles_owner_id_users", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("owner_id", "name", name="uq_profiles_owner_id_name"),
        sa.CheckConstraint(
            "surface_type IN ('print', 'paint', 'laser_mark', 'engraved')",
            name="ck_profiles_surface_type",
        ),
        sa.CheckConstraint(
            "alignment IN ('auto', 'left', 'center', 'right')", name="ck_profiles_alignment"
        ),
        sa.CheckConstraint(
            "spacing_mode IN ('auto', 'monospace', 'proportional')",
            name="ck_profiles_spacing_mode",
        ),
        sa.CheckConstraint("engine IN ('glyph_transplant')", name="ck_profiles_engine"),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 60", name="ck_profiles_name_length"),
        sa.CheckConstraint("length(charset) BETWEEN 1 AND 96", name="ck_profiles_charset_length"),
        sa.CheckConstraint("pattern_strict IN (0, 1)", name="ck_profiles_pattern_strict"),
        sa.CheckConstraint("use_auto_glyphs IN (0, 1)", name="ck_profiles_use_auto_glyphs"),
        sa.CheckConstraint("ready_threshold BETWEEN 1 AND 20", name="ck_profiles_ready_threshold"),
        sa.CheckConstraint("json_valid(learned_params)", name="ck_profiles_learned_params_json"),
    )
    op.create_index(
        "ix_profiles_owner_id_archived_at_updated_at",
        "profiles",
        ["owner_id", "archived_at", "updated_at"],
    )

    op.create_table(
        "reference_images",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("profile_id", sa.String(), nullable=False),
        sa.Column("file_id", sa.String(), nullable=False),
        sa.Column("known_text", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reference_images"),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_reference_images_profile_id_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name="fk_reference_images_file_id_files",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("profile_id", "file_id", name="uq_reference_images_profile_id_file_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'processed', 'failed')",
            name="ck_reference_images_status",
        ),
        sa.CheckConstraint(
            "known_text IS NULL OR length(known_text) <= 64",
            name="ck_reference_images_known_text",
        ),
    )
    op.create_index(
        "ix_reference_images_profile_id_created_at",
        "reference_images",
        ["profile_id", "created_at"],
    )
    op.create_index(
        "ix_reference_images_profile_id_status", "reference_images", ["profile_id", "status"]
    )

    op.create_table(
        "glyphs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("profile_id", sa.String(), nullable=False),
        sa.Column("source_reference_id", sa.String(), nullable=True),
        sa.Column("crop_file_id", sa.String(), nullable=False),
        sa.Column("char", sa.String(1), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_quad", sa.Text(), nullable=False),
        sa.Column("cap_height_px", sa.Float(), nullable=False),
        sa.Column("stroke_width_px", sa.Float(), nullable=False),
        sa.Column("blur_sigma", sa.Float(), nullable=False),
        sa.Column("noise_sigma", sa.Float(), nullable=False),
        sa.Column("ink_color", sa.String(7), nullable=False),
        sa.Column("bg_luma", sa.Float(), nullable=False),
        sa.Column("contrast", sa.Float(), nullable=False),
        sa.Column("angle_deg", sa.Float(), nullable=False),
        sa.Column("light_dir_deg", sa.Float(), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("accept_count", sa.Integer(), nullable=False),
        sa.Column("reject_count", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_glyphs"),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_glyphs_profile_id_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_reference_id"],
            ["reference_images.id"],
            name="fk_glyphs_source_reference_id_reference_images",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["crop_file_id"],
            ["files.id"],
            name="fk_glyphs_crop_file_id_files",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status IN ('auto', 'confirmed', 'rejected')", name="ck_glyphs_status"),
        sa.CheckConstraint("length(char) = 1", name="ck_glyphs_char_length"),
        sa.CheckConstraint("cap_height_px > 0", name="ck_glyphs_cap_height_px"),
        sa.CheckConstraint("stroke_width_px >= 0", name="ck_glyphs_stroke_width_px"),
        sa.CheckConstraint("blur_sigma >= 0", name="ck_glyphs_blur_sigma"),
        sa.CheckConstraint("noise_sigma >= 0", name="ck_glyphs_noise_sigma"),
        sa.CheckConstraint("bg_luma BETWEEN 0 AND 1", name="ck_glyphs_bg_luma"),
        sa.CheckConstraint("contrast BETWEEN 0 AND 1", name="ck_glyphs_contrast"),
        sa.CheckConstraint("angle_deg BETWEEN -90 AND 90", name="ck_glyphs_angle_deg"),
        sa.CheckConstraint(
            "light_dir_deg IS NULL OR (light_dir_deg >= 0 AND light_dir_deg < 360)",
            name="ck_glyphs_light_dir_deg",
        ),
        sa.CheckConstraint("ocr_confidence BETWEEN 0 AND 1", name="ck_glyphs_ocr_confidence"),
        sa.CheckConstraint("quality_score BETWEEN 0 AND 1", name="ck_glyphs_quality_score"),
        sa.CheckConstraint(
            "use_count >= 0 AND accept_count >= 0 AND reject_count >= 0",
            name="ck_glyphs_counters",
        ),
        sa.CheckConstraint("json_valid(source_quad)", name="ck_glyphs_source_quad_json"),
    )
    op.create_index(
        "ix_glyphs_profile_id_char_status_quality_score",
        "glyphs",
        ["profile_id", "char", "status", "quality_score"],
    )
    op.create_index("ix_glyphs_source_reference_id", "glyphs", ["source_reference_id"])


def downgrade() -> None:
    op.drop_index("ix_glyphs_source_reference_id", table_name="glyphs")
    op.drop_index("ix_glyphs_profile_id_char_status_quality_score", table_name="glyphs")
    op.drop_table("glyphs")
    op.drop_index("ix_reference_images_profile_id_status", table_name="reference_images")
    op.drop_index("ix_reference_images_profile_id_created_at", table_name="reference_images")
    op.drop_table("reference_images")
    op.drop_index("ix_profiles_owner_id_archived_at_updated_at", table_name="profiles")
    op.drop_table("profiles")
