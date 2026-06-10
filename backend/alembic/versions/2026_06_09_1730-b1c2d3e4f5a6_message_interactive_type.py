"""message interactive type

Adds an `interactive` value to the `messagetype` enum so quick-reply buttons /
list menus we send AND the button_reply/list_reply a contact taps back are
persisted with an accurate type rather than landing in `unsupported`.

PG 12+ allows ALTER TYPE ... ADD VALUE inside a transaction as long as the new
value isn't *used* in the same transaction; this migration only declares it.
Enum values cannot be dropped in Postgres, so downgrade is a no-op.

Revision ID: b1c2d3e4f5a6
Revises: e1ce7433c939
Create Date: 2026-06-09 17:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "e1ce7433c939"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'interactive'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; leaving 'interactive' in place is
    # harmless (no rows reference it after a rollback of the app code).
    pass
