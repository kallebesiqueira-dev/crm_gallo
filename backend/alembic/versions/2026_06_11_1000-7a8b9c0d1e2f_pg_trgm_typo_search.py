"""pg_trgm extension + trigram indexes for typo-tolerant search

Revision ID: 7a8b9c0d1e2f
Revises: 5a6b7c8d9e0f
Create Date: 2026-06-11 10:00:00.000000

Adds:
- pg_trgm extension (similarity() + gin_trgm_ops)
- GIN trigram indexes on leads and customers name/email columns
- Enables fallback in the API layer: if websearch_to_tsquery returns
  0 results, the search endpoint retries with similarity() > 0.3
"""

from alembic import op

revision = "7a8b9c0d1e2f"
down_revision = "5a6b7c8d9e0f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Trigram indexes for leads — covers the most-searched columns.
    # GIN is faster for similarity searches; GIST would suit ORDER BY similarity().
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_leads_fn_trgm ON leads "
        "USING gin (first_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_leads_ln_trgm ON leads "
        "USING gin (last_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_leads_email_trgm ON leads "
        "USING gin (email gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_leads_company_trgm ON leads "
        "USING gin (company gin_trgm_ops)"
    )

    # Same for customers
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_fn_trgm ON customers "
        "USING gin (first_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_ln_trgm ON customers "
        "USING gin (last_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_email_trgm ON customers "
        "USING gin (email gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_company_trgm ON customers "
        "USING gin (company gin_trgm_ops)"
    )


def downgrade() -> None:
    for idx in [
        "ix_leads_fn_trgm", "ix_leads_ln_trgm", "ix_leads_email_trgm", "ix_leads_company_trgm",
        "ix_customers_fn_trgm", "ix_customers_ln_trgm", "ix_customers_email_trgm", "ix_customers_company_trgm",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {idx}")
    # Extension intentionally left: other migrations/functions may depend on it.
