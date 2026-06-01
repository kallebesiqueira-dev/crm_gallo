"""org_invites

Adds the `org_invites` table for the multi-tenant invite flow (Phase 4
of the P0 multi-tenant rollout). The composite tenant indices that
autogenerate keeps trying to drop (it can't represent `sa.text("…DESC")`
in its model diff) are KEPT — see the comment in the
`drop_user_billing_columns` migration for the rationale.

Revision ID: 62fa86d2429c
Revises: 67d7b27d5ceb
Create Date: 2026-05-30 18:35:58.844815+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "62fa86d2429c"
down_revision: Union[str, None] = "67d7b27d5ceb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Reuse the existing enum — don't try to CREATE TYPE again.
userrole_enum = postgresql.ENUM(
    "admin", "manager", "sales_agent", "support_agent", "client",
    name="userrole", create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "org_invites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", userrole_enum, nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_org_invites_email"), "org_invites", ["email"])
    op.create_index(op.f("ix_org_invites_organization_id"), "org_invites", ["organization_id"])
    op.create_index(op.f("ix_org_invites_token"), "org_invites", ["token"], unique=True)
    # Composite index for the admin "pending invites in this org" list
    # query — order matters: org first (selectivity), then accepted_at
    # so the partial scan returns pending rows fast.
    op.create_index(
        "idx_org_invites_org_pending",
        "org_invites",
        ["organization_id", "accepted_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_org_invites_org_pending", table_name="org_invites")
    op.drop_index(op.f("ix_org_invites_token"), table_name="org_invites")
    op.drop_index(op.f("ix_org_invites_organization_id"), table_name="org_invites")
    op.drop_index(op.f("ix_org_invites_email"), table_name="org_invites")
    op.drop_table("org_invites")
