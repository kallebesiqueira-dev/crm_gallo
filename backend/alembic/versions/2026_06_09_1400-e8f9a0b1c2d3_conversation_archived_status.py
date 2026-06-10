"""conversation archived status

Adds an `archived` value to the `conversationstatus` enum so an agent can file
a thread away (hidden from the default inbox, and NOT auto-reopened on a new
inbound message — that is the distinction from `closed`).

PG 12+ allows ALTER TYPE ... ADD VALUE inside a transaction as long as the new
value isn't *used* in the same transaction; this migration only declares it.
Enum values cannot be dropped in Postgres, so downgrade is a no-op.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-06-09 14:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE conversationstatus ADD VALUE IF NOT EXISTS 'archived'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; leaving 'archived' in place is
    # harmless (no rows reference it after a rollback of the app code).
    pass
