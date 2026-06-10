"""lead_version_column

Add `version` integer column to `leads` for optimistic locking (§330).
Mirrors the existing pattern on `customers`, `deals`, and `tasks`.
Backfill = 0 (all existing rows get the same initial version).

Revision ID: 5a6b7c8d9e0f
Revises: 9f8e7d6c5b4a
Create Date: 2026-06-10 22:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5a6b7c8d9e0f"
down_revision: Union[str, None] = "9f8e7d6c5b4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("leads", "version")
