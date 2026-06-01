"""deal_version_for_optimistic_locking

Revision ID: 4d3d59906702
Revises: fb4c1a3697b9
Create Date: 2026-06-01 18:29:42.747919+00:00

TD-12. Add `version int NOT NULL DEFAULT 0` to `deals` so the
update / move endpoints can compare-and-set against an `If-Match`
header. v1 ships with the header optional; a missing header logs a
warning so we can see frontend coverage before flipping to strict.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d3d59906702"
down_revision: Union[str, None] = "fb4c1a3697b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "deals",
        sa.Column(
            "version", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    # Drop the server_default — going forward, the application owns
    # the value via the model's `default=0`. Server_default stays in
    # the DB schema for ANY existing rows that arrive via raw SQL.
    # (Keeping it permanently is fine too; this is hygiene.)


def downgrade() -> None:
    op.drop_column("deals", "version")
