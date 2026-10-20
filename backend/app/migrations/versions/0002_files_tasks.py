"""Stored files registry and the persisted task queue.

Revision ID: 0002_files_tasks
Revises: 0001_initial_auth
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_files_tasks"
down_revision: str | None = "0001_initial_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.String(24)  # ISO-8601 UTC text, see app.db.types.UtcDateTime

FILE_KINDS = (
    "'reference', 'target', 'glyph', 'mask', 'background', 'result', "
    "'export', 'batch_zip', 'backup', 'thumbnail'"
)
MIME_TYPES = "'image/jpeg', 'image/png', 'image/tiff', 'application/zip'"
TASK_TYPES = "'extract_glyphs', 'detect', 'render', 'batch_run', 'batch_export', 'backup'"
TASK_SUBJECTS = "'profile', 'reference_image', 'edit_job', 'batch', 'system'"
TASK_STATUSES = "'queued', 'running', 'succeeded', 'failed', 'cancelled'"


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("mime_type", sa.String(32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("dpi_x", sa.Float(), nullable=True),
        sa.Column("dpi_y", sa.Float(), nullable=True),
        sa.Column("has_icc", sa.Integer(), nullable=False),
        sa.Column("jpeg_quality_est", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(255), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_files"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_files_owner_id_users", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("owner_id", "sha256", "kind", name="uq_files_owner_id_sha256_kind"),
        sa.CheckConstraint(f"kind IN ({FILE_KINDS})", name="ck_files_kind"),
        sa.CheckConstraint(f"mime_type IN ({MIME_TYPES})", name="ck_files_mime_type"),
        sa.CheckConstraint("byte_size > 0", name="ck_files_byte_size"),
        sa.CheckConstraint("width IS NULL OR width > 0", name="ck_files_width"),
        sa.CheckConstraint("height IS NULL OR height > 0", name="ck_files_height"),
        sa.CheckConstraint("has_icc IN (0, 1)", name="ck_files_has_icc"),
        sa.CheckConstraint(
            "jpeg_quality_est IS NULL OR jpeg_quality_est BETWEEN 1 AND 100",
            name="ck_files_jpeg_quality_est",
        ),
        sa.CheckConstraint("length(sha256) = 64", name="ck_files_sha256_length"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("message", sa.String(200), nullable=True),
        sa.Column("cancel_requested", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("started_at", TS, nullable=True),
        sa.Column("finished_at", TS, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_tasks_owner_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint(f"type IN ({TASK_TYPES})", name="ck_tasks_type"),
        sa.CheckConstraint(f"subject_type IN ({TASK_SUBJECTS})", name="ck_tasks_subject_type"),
        sa.CheckConstraint(f"status IN ({TASK_STATUSES})", name="ck_tasks_status"),
        sa.CheckConstraint("progress BETWEEN 0 AND 1", name="ck_tasks_progress"),
        sa.CheckConstraint("cancel_requested IN (0, 1)", name="ck_tasks_cancel_requested"),
        sa.CheckConstraint("json_valid(payload)", name="ck_tasks_payload_json"),
    )
    op.create_index("ix_tasks_status_created_at", "tasks", ["status", "created_at"])
    op.create_index(
        "ix_tasks_subject_type_subject_id_status",
        "tasks",
        ["subject_type", "subject_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_subject_type_subject_id_status", table_name="tasks")
    op.drop_index("ix_tasks_status_created_at", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("files")
