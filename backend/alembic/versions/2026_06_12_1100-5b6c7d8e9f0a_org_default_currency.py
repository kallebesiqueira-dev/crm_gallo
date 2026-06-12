"""org_default_currency

plan.md §6: `organizations.default_currency` — the currency new
deals/quotes get when the create payload omits the field. Backfills
every existing org to EUR (today's hardcoded behavior), so nothing
changes until an admin picks CHF/GBP/USD in the org settings.

Reuses the existing `currency` PG enum (created with the deals
table) — create_type=False.

Revision ID: 5b6c7d8e9f0a
Revises: 3e4f5a6b7c8d
Create Date: 2026-06-12 11:00:00.000000+00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "5b6c7d8e9f0a"
down_revision = "3e4f5a6b7c8d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "default_currency",
            sa.Enum(name="currency", create_type=False),
            nullable=False,
            server_default="EUR",
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "default_currency")
