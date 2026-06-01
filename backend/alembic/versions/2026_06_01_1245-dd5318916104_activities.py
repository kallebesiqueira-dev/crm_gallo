"""activities — user-facing event timeline

Creates the `activities` table backing the entity detail page
timelines (lead / customer / deal). Separate from `audit_logs` —
see the model docstring for the distinction.

The composite tenant indices that autogenerate keeps trying to drop
(`sa.text("…DESC")` / `lower(...)` not representable in the model
diff) are KEPT — see the comment in the `drop_user_billing_columns`
migration for the rationale.

Revision ID: dd5318916104
Revises: ddd83138c832
Create Date: 2026-06-01 12:45:35.182971+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "dd5318916104"
down_revision: Union[str, None] = "ddd83138c832"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_activities_organization_id"),
        "activities",
        ["organization_id"],
        unique=False,
    )
    # The "give me the timeline for THIS entity, newest first" query
    # runs on every detail page open. This composite makes it an
    # index-only seek.
    op.execute(
        """
        CREATE INDEX idx_activities_entity_created
          ON activities (organization_id, entity_type, entity_id, created_at DESC);
        """
    )

    # crm_app (runtime role) needs CRUD on the new table. Default
    # privileges from f5fde59e0dc8 should cover this for tables crm
    # creates, but explicit GRANT is idempotent and removes any
    # ordering ambiguity.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON activities TO crm_app;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_activities_entity_created;")
    op.drop_index(op.f("ix_activities_organization_id"), table_name="activities")
    op.drop_table("activities")
