"""conversation assignee (team-inbox ownership)

Adds `conversations.assignee_id` — the agent who owns a thread, NULL meaning the
thread is in the shared unassigned queue. SET NULL on the user FK so deleting an
agent drops their threads back into the queue rather than cascading them away.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-10 12:00:00.000000+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("assignee_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_assignee_id_users",
        "conversations",
        "users",
        ["assignee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversations_assignee_id", "conversations", ["assignee_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_assignee_id", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_assignee_id_users", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "assignee_id")
