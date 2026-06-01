"""drop_user_billing_columns

Removes the billing fields from `users` now that Organization is the
source of truth for plan / billing_cycle / stripe_* (see ADR-013 +
Phase 3 of the multi-tenant rollout).

Backfill (default-workspace inheriting from the oldest admin) already ran
in `bcac4a2cdbfa_multi_tenant_organizations`, so this migration is a
pure DROP — no data movement. Composite tenant indices created in the
previous migration are KEPT (Alembic's autogenerate flagged them for
removal because it can't represent `sa.text("…DESC")` in its model
diff; we override the autogen output here).

Revision ID: 67d7b27d5ceb
Revises: bcac4a2cdbfa
Create Date: 2026-05-30 18:24:10.601123+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "67d7b27d5ceb"
down_revision: Union[str, None] = "bcac4a2cdbfa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Single-column indices alembic created earlier when these columns
    # lived on `users` — must drop before dropping the columns.
    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_index("ix_users_stripe_subscription_id", table_name="users")

    # Drop billing columns. Order doesn't matter for Postgres but we
    # group them by concern for readability.
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "trial_ends_at")
    op.drop_column("users", "plan_canceled_at")
    op.drop_column("users", "plan_renewed_at")
    op.drop_column("users", "plan_started_at")
    op.drop_column("users", "billing_cycle")
    op.drop_column("users", "plan")


def downgrade() -> None:
    # Re-create the columns with the same shape they had pre-Phase 3.
    # Data is NOT restored — billing rows live on `organizations` now.
    # Anyone reverting this past Phase 3 has to write a separate backfill
    # to copy org.* → user.*.
    op.add_column(
        "users",
        sa.Column(
            "plan",
            postgresql.ENUM("free", "standard", "premium", name="plan", create_type=False),
            server_default=sa.text("'free'::plan"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "billing_cycle",
            postgresql.ENUM("monthly", "yearly", name="billingcycle", create_type=False),
            server_default=sa.text("'monthly'::billingcycle"),
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("plan_started_at", postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("plan_renewed_at", postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("plan_canceled_at", postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("trial_ends_at", postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True))
    op.create_index("ix_users_stripe_customer_id", "users", ["stripe_customer_id"])
    op.create_index("ix_users_stripe_subscription_id", "users", ["stripe_subscription_id"])
