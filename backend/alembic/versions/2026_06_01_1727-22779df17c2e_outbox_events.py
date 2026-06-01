"""outbox_events

Revision ID: 22779df17c2e
Revises: 1d4dca386af7
Create Date: 2026-06-01 17:27:37.140126+00:00

Transactional outbox (ADR-007). New table; no other schema changes.
Autogenerate produced 22 false-positive drop_index calls for our
partial / DESC-ordered indices — gutted in favour of an explicit
upgrade/downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "22779df17c2e"
down_revision: Union[str, None] = "1d4dca386af7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Hot path: the poller's `WHERE processed_at IS NULL ORDER BY occurred_at`
    # claim query. Partial index stays tiny (only the work queue).
    op.create_index(
        "idx_outbox_unprocessed",
        "outbox_events",
        ["occurred_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )

    # Inspection path: admin endpoint paginates by org, newest first.
    op.create_index(
        "idx_outbox_org_occurred",
        "outbox_events",
        ["organization_id", sa.text("occurred_at DESC")],
    )

    # The runtime role (`crm_app`) needs DML access. The worker is the
    # main writer but the API also INSERTs from request handlers.
    # Outbox is NOT RLS'd by design — see model docstring.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON outbox_events TO crm_app")


def downgrade() -> None:
    op.drop_index("idx_outbox_org_occurred", table_name="outbox_events")
    op.drop_index(
        "idx_outbox_unprocessed",
        table_name="outbox_events",
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.drop_table("outbox_events")
