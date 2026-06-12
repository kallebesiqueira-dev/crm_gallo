"""org_retention_months

GDPR retention policy knob (plan.md §5): `organizations.retention_months`
— months of lead inactivity after which the worker's daily sweep
anonymizes the record via the same erasure path as POST /forget.
NULL (the default for every existing org) = retention disabled; this
migration changes no behavior until an admin opts in through
PATCH /api/gdpr/settings.

`organizations` is not RLS'd (it's the tenant root), so a plain
ADD COLUMN suffices.

Revision ID: 3e4f5a6b7c8d
Revises: c6d7e8f9a0b1
Create Date: 2026-06-12 09:00:00.000000+00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "3e4f5a6b7c8d"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("retention_months", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "retention_months")
