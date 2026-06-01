"""notifications — per-user in-app inbox

Per-user notification rows. Indexed for "my unread bell" lookups:
`(user_id, created_at DESC) WHERE read_at IS NULL`. The bell hits
this every page load so the partial index keeps it fast even when
historical notifications pile up before the 90-day prune cron
(P3 follow-up) runs.

Composite tenant indices that autogenerate keeps trying to drop
(sa.text("…DESC") / lower()) are KEPT — see
`drop_user_billing_columns` for the rationale.

Revision ID: 1d4dca386af7
Revises: 3639bde75ea7
Create Date: 2026-06-01 15:27:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1d4dca386af7"
down_revision: Union[str, None] = "3639bde75ea7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link_url", sa.String(length=500), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notifications_organization_id"),
        "notifications",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_user_id"),
        "notifications",
        ["user_id"],
        unique=False,
    )
    # Hot path: "give me my unread bell, newest first". Partial index
    # skips read rows entirely so even after 10k historical
    # notifications a returning user's bell render is index-only.
    op.execute(
        """
        CREATE INDEX idx_notifications_user_unread_created
          ON notifications (user_id, created_at DESC)
          WHERE read_at IS NULL;
        """
    )
    # Secondary index for the full inbox view (read + unread mixed).
    op.execute(
        """
        CREATE INDEX idx_notifications_user_created
          ON notifications (user_id, created_at DESC);
        """
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO crm_app;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notifications_user_created;")
    op.execute("DROP INDEX IF EXISTS idx_notifications_user_unread_created;")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(
        op.f("ix_notifications_organization_id"), table_name="notifications"
    )
    op.drop_table("notifications")
