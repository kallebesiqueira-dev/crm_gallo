"""message reaction type + context wamid

Adds a `reaction` value to the `messagetype` enum (an emoji reaction we send or a
contact taps back) and a `context_wa_message_id` column on `messages` that points
at the wamid of the message a reaction reacts to (Meta's `reaction.message_id`)
or, more generally, a quoted reply's `context.id`.

PG 12+ allows ALTER TYPE ... ADD VALUE inside a transaction as long as the new
value isn't *used* in the same transaction; this migration only declares it.
Enum values cannot be dropped in Postgres, so the enum half of downgrade is a
no-op; the column is dropped.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-09 18:30:00.000000+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'reaction'")
    op.add_column(
        "messages",
        sa.Column("context_wa_message_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_messages_context_wa_message_id",
        "messages",
        ["context_wa_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_context_wa_message_id", table_name="messages")
    op.drop_column("messages", "context_wa_message_id")
    # Postgres has no DROP VALUE for enums; leaving 'reaction' in place is
    # harmless (no rows reference it after a rollback of the app code).
