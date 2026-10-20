"""Edit jobs, their glyph usage, batches; glyph source job and baseline (DATABASE.md §3.6-3.9).

Revision ID: 0005_edit_jobs
Revises: 0004_profiles_glyphs
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_edit_jobs"
down_revision: str | None = "0004_profiles_glyphs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.String(24)  # ISO-8601 UTC text, see app.db.types.UtcDateTime


def upgrade() -> None:
    # batches ↔ edit_jobs reference each other; SQLite accepts the forward reference.
    op.create_table(
        "batches",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("profile_id", sa.String(), nullable=False),
        sa.Column("template_job_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(80), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("export_file_id", sa.String(), nullable=True),
        sa.Column("client_request_id", sa.String(64), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.Column("finished_at", TS, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_batches"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_batches_owner_id_users", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_batches_profile_id_profiles",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_job_id"],
            ["edit_jobs.id"],
            name="fk_batches_template_job_id_edit_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["export_file_id"],
            ["files.id"],
            name="fk_batches_export_file_id_files",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "owner_id", "client_request_id", name="uq_batches_owner_id_client_request_id"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'cancelled', 'failed')",
            name="ck_batches_status",
        ),
        sa.CheckConstraint("total_count BETWEEN 1 AND 1000", name="ck_batches_total_count"),
        sa.CheckConstraint("name IS NULL OR length(name) <= 80", name="ck_batches_name_length"),
    )
    op.create_index("ix_batches_owner_id_created_at", "batches", ["owner_id", "created_at"])

    op.create_table(
        "edit_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("profile_id", sa.String(), nullable=False),
        sa.Column("batch_id", sa.String(), nullable=True),
        sa.Column("input_file_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("regions", sa.Text(), nullable=True),
        sa.Column("selected_region_id", sa.String(16), nullable=True),
        sa.Column("selected_quad", sa.Text(), nullable=True),
        sa.Column("original_text", sa.String(64), nullable=True),
        sa.Column("new_text", sa.String(64), nullable=True),
        sa.Column("params", sa.Text(), nullable=False),
        sa.Column("geometry", sa.Text(), nullable=True),
        sa.Column("background_file_id", sa.String(), nullable=True),
        sa.Column("mask_file_id", sa.String(), nullable=True),
        sa.Column("result_file_id", sa.String(), nullable=True),
        sa.Column("quality", sa.Text(), nullable=True),
        sa.Column("quality_overall", sa.String(8), nullable=True),
        sa.Column("engine_version", sa.String(64), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("reject_reason", sa.String(300), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("accepted_at", TS, nullable=True),
        sa.Column("exported_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_edit_jobs"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_edit_jobs_owner_id_users", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_edit_jobs_profile_id_profiles",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["batches.id"], name="fk_edit_jobs_batch_id_batches", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["input_file_id"],
            ["files.id"],
            name="fk_edit_jobs_input_file_id_files",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["background_file_id"],
            ["files.id"],
            name="fk_edit_jobs_background_file_id_files",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["mask_file_id"],
            ["files.id"],
            name="fk_edit_jobs_mask_file_id_files",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["result_file_id"],
            ["files.id"],
            name="fk_edit_jobs_result_file_id_files",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'detecting', 'detected', 'rendering', 'rendered', "
            "'accepted', 'rejected', 'failed')",
            name="ck_edit_jobs_status",
        ),
        sa.CheckConstraint(
            "quality_overall IS NULL OR quality_overall IN ('pass', 'warn', 'fail')",
            name="ck_edit_jobs_quality_overall",
        ),
        sa.CheckConstraint(
            "original_text IS NULL OR length(original_text) <= 64",
            name="ck_edit_jobs_original_text",
        ),
        sa.CheckConstraint(
            "new_text IS NULL OR length(new_text) <= 64", name="ck_edit_jobs_new_text"
        ),
        sa.CheckConstraint(
            "reject_reason IS NULL OR length(reject_reason) <= 300",
            name="ck_edit_jobs_reject_reason",
        ),
        sa.CheckConstraint("json_valid(params)", name="ck_edit_jobs_params_json"),
    )
    op.create_index(
        "ix_edit_jobs_owner_id_batch_id_created_at",
        "edit_jobs",
        ["owner_id", "batch_id", "created_at"],
    )
    op.create_index(
        "ix_edit_jobs_owner_id_profile_id_status_created_at",
        "edit_jobs",
        ["owner_id", "profile_id", "status", "created_at"],
    )
    op.create_index(
        "ix_edit_jobs_batch_id_quality_overall_status",
        "edit_jobs",
        ["batch_id", "quality_overall", "status"],
    )
    op.create_index("ix_edit_jobs_owner_id_new_text", "edit_jobs", ["owner_id", "new_text"])
    op.create_index(
        "ix_edit_jobs_owner_id_original_text", "edit_jobs", ["owner_id", "original_text"]
    )

    with op.batch_alter_table("glyphs", recreate="always") as batch:
        batch.add_column(sa.Column("source_job_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("baseline_y", sa.Float(), nullable=True))
        batch.create_foreign_key(
            "fk_glyphs_source_job_id_edit_jobs",
            "edit_jobs",
            ["source_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_glyphs_one_source",
            "(source_reference_id IS NOT NULL) + (source_job_id IS NOT NULL) <= 1",
        )
        batch.create_index("ix_glyphs_source_job_id", ["source_job_id"])

    op.create_table(
        "edit_job_glyphs",
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("glyph_id", sa.String(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("job_id", "position", name="pk_edit_job_glyphs"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["edit_jobs.id"],
            name="fk_edit_job_glyphs_job_id_edit_jobs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["glyph_id"],
            ["glyphs.id"],
            name="fk_edit_job_glyphs_glyph_id_glyphs",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("source IN ('same_image', 'bank')", name="ck_edit_job_glyphs_source"),
        sa.CheckConstraint("position >= 0", name="ck_edit_job_glyphs_position"),
    )
    op.create_index("ix_edit_job_glyphs_glyph_id", "edit_job_glyphs", ["glyph_id"])


def downgrade() -> None:
    op.drop_index("ix_edit_job_glyphs_glyph_id", table_name="edit_job_glyphs")
    op.drop_table("edit_job_glyphs")
    with op.batch_alter_table("glyphs", recreate="always") as batch:
        batch.drop_index("ix_glyphs_source_job_id")
        batch.drop_constraint("ck_glyphs_one_source", type_="check")
        batch.drop_constraint("fk_glyphs_source_job_id_edit_jobs", type_="foreignkey")
        batch.drop_column("baseline_y")
        batch.drop_column("source_job_id")
    for index in (
        "ix_edit_jobs_owner_id_original_text",
        "ix_edit_jobs_owner_id_new_text",
        "ix_edit_jobs_batch_id_quality_overall_status",
        "ix_edit_jobs_owner_id_profile_id_status_created_at",
        "ix_edit_jobs_owner_id_batch_id_created_at",
    ):
        op.drop_index(index, table_name="edit_jobs")
    op.drop_index("ix_batches_owner_id_created_at", table_name="batches")
    # Break the batches ↔ edit_jobs cycle: drop edit_jobs first with FKs off.
    op.execute("PRAGMA foreign_keys=OFF")
    op.drop_table("edit_jobs")
    op.drop_table("batches")
    op.execute("PRAGMA foreign_keys=ON")
