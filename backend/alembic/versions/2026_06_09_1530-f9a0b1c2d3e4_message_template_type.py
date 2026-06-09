"""message template type

Adds a `template` value to the `messagetype` enum so an outbound row that sends
a pre-approved WhatsApp message template (business-initiated, outside the 24h
window) is persisted with an accurate type rather than masquerading as `text`.

PG 12+ allows ALTER TYPE ... ADD VALUE inside a transaction as long as the new
value isn't *used* in the same transaction; this migration only declares it.
Enum values cannot be dropped in Postgres, so downgrade is a no-op.

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-06-09 15:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'template'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; leaving 'template' in place is
    # harmless (no rows reference it after a rollback of the app code).
    pass
