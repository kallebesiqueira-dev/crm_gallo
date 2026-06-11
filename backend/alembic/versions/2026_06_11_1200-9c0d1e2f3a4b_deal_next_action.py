"""Add next_action_type and next_action_at to deals

Revision ID: 9c0d1e2f3a4b
Revises: 8b9c0d1e2f3a
Create Date: 2026-06-11 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "9c0d1e2f3a4b"
down_revision = "8b9c0d1e2f3a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE nextactiontype AS ENUM (
            'call', 'whatsapp', 'email', 'proposal', 'meeting',
            'follow_up', 'contract', 'chase', 'other'
        )
        """
    )
    op.add_column(
        "deals",
        sa.Column(
            "next_action_type",
            sa.Enum(name="nextactiontype", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "deals",
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        CREATE INDEX ix_deals_next_action_at
        ON deals (organization_id, next_action_at)
        WHERE next_action_at IS NOT NULL AND deleted_at IS NULL
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON deals TO crm_app")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_deals_next_action_at")
    op.drop_column("deals", "next_action_at")
    op.drop_column("deals", "next_action_type")
    op.execute("DROP TYPE IF EXISTS nextactiontype")
