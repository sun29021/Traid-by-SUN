"""Local mode without sign-in: users.password_hash becomes nullable (PRD D-03).

Revision ID: 0003_local_owner
Revises: 0002_files_tasks
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_local_owner"
down_revision: str | None = "0002_files_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    # Users without a password cannot exist in the previous schema; give them an
    # unusable marker that no password hash can ever match.
    op.execute("UPDATE users SET password_hash = '!' WHERE password_hash IS NULL")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=False)
