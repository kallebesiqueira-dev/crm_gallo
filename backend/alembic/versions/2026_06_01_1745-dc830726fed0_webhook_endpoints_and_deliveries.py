"""webhook_endpoints_and_deliveries

Revision ID: dc830726fed0
Revises: 22779df17c2e
Create Date: 2026-06-01 17:45:00+00:00

New tables only. Autogenerate produced 22 false-positive drop_index
calls for our partial/DESC indices — gutted in favour of an explicit
upgrade/downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "dc830726fed0"
down_revision: Union[str, None] = "22779df17c2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("secret", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "enabled_events",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[\"*\"]'"),
        ),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Hot path: fanout lookup-by-org. Partial-active variant excludes
    # paused endpoints so the dispatcher doesn't filter post-query.
    op.create_index(
        "idx_webhook_endpoints_org_active",
        "webhook_endpoints",
        ["organization_id"],
        postgresql_where=sa.text("paused_at IS NULL"),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("endpoint_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("response_body_excerpt", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "scheduled_for",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["endpoint_id"], ["webhook_endpoints.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_webhook_deliveries_endpoint_scheduled",
        "webhook_deliveries",
        ["endpoint_id", sa.text("scheduled_for DESC")],
    )
    op.create_index(
        "idx_webhook_deliveries_event",
        "webhook_deliveries",
        ["event_id", "endpoint_id"],
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON webhook_endpoints TO crm_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON webhook_deliveries TO crm_app"
    )


def downgrade() -> None:
    op.drop_index(
        "idx_webhook_deliveries_event", table_name="webhook_deliveries"
    )
    op.drop_index(
        "idx_webhook_deliveries_endpoint_scheduled", table_name="webhook_deliveries"
    )
    op.drop_table("webhook_deliveries")
    op.drop_index(
        "idx_webhook_endpoints_org_active",
        table_name="webhook_endpoints",
        postgresql_where=sa.text("paused_at IS NULL"),
    )
    op.drop_table("webhook_endpoints")
