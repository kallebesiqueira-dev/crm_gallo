"""fulltext_search_vector_leads_customers

Revision ID: 062fbc7b628d
Revises: dc830726fed0
Create Date: 2026-06-01 18:08:12.509909+00:00

Replaces the `LOWER(...) LIKE '%q%'` full-table scan on leads /
customers search with PostgreSQL FTS (ADR-008): a STORED generated
tsvector column + GIN index. Auto-maintained — no triggers, no
application bookkeeping. `simple` config (not 'english') because the
data is multilingual (7 supported locales). pg_trgm fuzzy-match
fallback is a P2 follow-up.

Weights: A on personal names (first/last), B on email/company.
Receiver of `ts_rank` can use the weighting later when we surface
ranking in the UI.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "062fbc7b628d"
down_revision: Union[str, None] = "dc830726fed0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEAD_VECTOR_EXPR = """
    setweight(to_tsvector('simple', coalesce(first_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(last_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(email, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(company, '')), 'B')
"""

_CUSTOMER_VECTOR_EXPR = """
    setweight(to_tsvector('simple', coalesce(first_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(last_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(email, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(company, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(industry, '')), 'C')
"""


def upgrade() -> None:
    # STORED generated column — PG auto-recomputes on row write; SELECT
    # cost is a column read. The alternative (an expression index)
    # forces every query to spell out the full expression to match.
    op.execute(
        f"ALTER TABLE leads ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_LEAD_VECTOR_EXPR}) STORED"
    )
    op.execute(
        f"ALTER TABLE customers ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_CUSTOMER_VECTOR_EXPR}) STORED"
    )

    # GIN index on the tsvector — the recommended type for FTS
    # (faster lookups than GiST at the cost of slower writes, which
    # is fine for our read-heavy CRM workload).
    op.execute(
        "CREATE INDEX idx_leads_search_vector ON leads USING gin (search_vector)"
    )
    op.execute(
        "CREATE INDEX idx_customers_search_vector "
        "ON customers USING gin (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_customers_search_vector")
    op.execute("DROP INDEX IF EXISTS idx_leads_search_vector")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS search_vector")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS search_vector")
