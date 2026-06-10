"""conversation service window anchor

Adds `conversations.last_inbound_at` — the timestamp of the most recent INBOUND
message on a thread. It anchors WhatsApp's 24h customer-service window: free-form
(non-template) sends are only allowed while `now < last_inbound_at + 24h`.

Backfills existing rows from each conversation's latest inbound message so open
threads keep an accurate window immediately after deploy.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-10 09:00:00.000000+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_conversations_last_inbound_at", "conversations", ["last_inbound_at"]
    )
    op.execute(
        """
        UPDATE conversations c
        SET last_inbound_at = sub.max_ts
        FROM (
            SELECT conversation_id, MAX(timestamp) AS max_ts
            FROM messages
            WHERE direction = 'inbound'
            GROUP BY conversation_id
        ) sub
        WHERE c.id = sub.conversation_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_last_inbound_at", table_name="conversations")
    op.drop_column("conversations", "last_inbound_at")
