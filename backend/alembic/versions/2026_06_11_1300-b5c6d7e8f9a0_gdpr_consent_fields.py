"""Add contact_consent_at and consent_source to leads and customers (GDPR §5)

Revision ID: b5c6d7e8f9a0
Revises: 9c0d1e2f3a4b
Create Date: 2026-06-11 13:00:00.000000
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "9c0d1e2f3a4b"
branch_labels = None
depends_on = None

_CONSENT_SOURCES = (
    "web_form",
    "import",
    "manual",
    "whatsapp",
    "api",
    "other",
)


def upgrade() -> None:
    # Create enum
    op.execute(
        "CREATE TYPE consentsource AS ENUM ("
        "'web_form','import','manual','whatsapp','api','other'"
        ")"
    )

    # leads
    op.add_column(
        "leads",
        sa.Column(
            "contact_consent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "leads",
        sa.Column(
            "consent_source",
            sa.Enum(*_CONSENT_SOURCES, name="consentsource", create_type=False),
            nullable=True,
        ),
    )

    # customers
    op.add_column(
        "customers",
        sa.Column(
            "contact_consent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "customers",
        sa.Column(
            "consent_source",
            sa.Enum(*_CONSENT_SOURCES, name="consentsource", create_type=False),
            nullable=True,
        ),
    )

    # Partial index: quickly find contacts with (or without) consent
    op.create_index(
        "ix_leads_consent_at",
        "leads",
        ["organization_id", "contact_consent_at"],
        postgresql_where=sa.text("contact_consent_at IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_customers_consent_at",
        "customers",
        ["organization_id", "contact_consent_at"],
        postgresql_where=sa.text("contact_consent_at IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_customers_consent_at")
    op.drop_index("ix_leads_consent_at")
    op.drop_column("customers", "consent_source")
    op.drop_column("customers", "contact_consent_at")
    op.drop_column("leads", "consent_source")
    op.drop_column("leads", "contact_consent_at")
    op.execute("DROP TYPE consentsource")
