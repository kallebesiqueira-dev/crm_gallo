"""user_display_currency

Launch roadmap #1 (multi-currency): `users.display_currency` — each user's
preferred currency for money figures across the UI. Display-only; the
frontend converts EUR-canonical figures client-side using /api/fx/rates.
Stored amounts never change (ADR-015). Backfills every existing user to EUR
(today's behavior), so nothing changes until a user picks CHF/GBP/USD.

Reuses the existing `currency` PG enum (create_type=False), like
5b6c7d8e9f0a. Hand-written; single head at authoring time: e7c8d9a0b1f2.

Revision ID: f8a9b0c1d2e3
Revises: e7c8d9a0b1f2
Create Date: 2026-06-15 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "e7c8d9a0b1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "display_currency",
            sa.Enum(name="currency", create_type=False),
            nullable=False,
            server_default="EUR",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "display_currency")
