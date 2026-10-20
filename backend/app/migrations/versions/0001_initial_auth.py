"""Initial auth tables: users, sessions, audit_events (append-only), app_settings.

Revision ID: 0001_initial_auth
Revises:
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_auth"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.String(24)  # ISO-8601 UTC text, see app.db.types.UtcDateTime

# Audit rows are immutable. The only allowed UPDATE is the FK action
# `ON DELETE SET NULL` clearing user_id when a user is deleted.
AUDIT_NO_UPDATE = """
CREATE TRIGGER trg_audit_events_no_update
BEFORE UPDATE ON audit_events
WHEN NOT (
    OLD.user_id IS NOT NULL AND NEW.user_id IS NULL
    AND NEW.id = OLD.id AND NEW.action = OLD.action
    AND NEW.subject_type IS OLD.subject_type AND NEW.subject_id IS OLD.subject_id
    AND NEW.details = OLD.details AND NEW.created_at = OLD.created_at
)
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END
"""

AUDIT_NO_DELETE = """
CREATE TRIGGER trg_audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END
"""


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(60), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", TS, nullable=True),
        sa.Column("aup_accepted_at", TS, nullable=True),
        sa.Column("last_login_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.CheckConstraint("role IN ('owner', 'editor')", name="ck_users_role"),
        sa.CheckConstraint("is_active IN (0, 1)", name="ck_users_is_active"),
        sa.CheckConstraint("failed_login_count >= 0", name="ck_users_failed_login_count"),
        sa.CheckConstraint("length(username) BETWEEN 3 AND 32", name="ck_users_username_length"),
        sa.CheckConstraint("username = lower(username)", name="ck_users_username_lowercase"),
        sa.CheckConstraint(
            "length(display_name) BETWEEN 1 AND 60", name="ck_users_display_name_length"
        ),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_secret", sa.String(64), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_seen_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS, nullable=True),
        sa.Column("user_agent", sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id_revoked_at", "sessions", ["user_id", "revoked_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=True),
        sa.Column("subject_id", sa.String(36), nullable=True),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_audit_events_user_id_users", ondelete="SET NULL"
        ),
        sa.CheckConstraint("json_valid(details)", name="ck_audit_events_details_json"),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.execute(AUDIT_NO_UPDATE)
    op.execute(AUDIT_NO_DELETE)

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_app_settings"),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_app_settings_updated_by_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("json_valid(value)", name="ck_app_settings_value_json"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_sessions_user_id_revoked_at", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
