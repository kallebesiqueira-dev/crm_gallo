"""add business plan to the plan enum

Revision ID: c1d2e3f4a5b6
Revises: 9a8b7c6d5e4f
Create Date: 2026-06-04 20:00:00

Adds the ``business`` value to the Postgres ``plan`` enum so the catalog can
offer 4 tiers (Free / Standard / Business / Premium). ``ALTER TYPE ADD VALUE``
runs in its own autocommit block — Postgres 12+ allows it inside a transaction,
but the autocommit block is the safe, portable form and avoids the "cannot run
inside a transaction block" failure on stricter setups. Positioned AFTER
``standard`` so the enum sort order matches the price ladder.

Downgrade is a deliberate no-op: Postgres has no ``DROP VALUE``, and removing
an in-use enum value would orphan rows.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c1d2e3f4a5b6"
down_revision = "9a8b7c6d5e4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE plan ADD VALUE IF NOT EXISTS 'business' AFTER 'standard'")


def downgrade() -> None:
    # Postgres cannot drop an enum value; leaving `business` in place is
    # harmless when no rows reference it. No-op by design.
    pass
