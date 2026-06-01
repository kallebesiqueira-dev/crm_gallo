"""search_vector_tokenize_emails

Revision ID: fb4c1a3697b9
Revises: 062fbc7b628d
Create Date: 2026-06-01 18:18:00+00:00

Refine the FTS generated column so emails split into searchable
parts. The `simple` tokenizer treats `founder@acmecorp.example` as
ONE token, so searching for `acmecorp` misses. We pre-split via
`regexp_replace(email, '[@.]', ' ', 'g')` BEFORE tokenizing, so the
same email contributes the tokens `founder`, `acmecorp`, `example`.

PG can't ALTER an existing GENERATED column expression — drop and
re-add. Same for the GIN index that references the column.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "fb4c1a3697b9"
down_revision: Union[str, None] = "062fbc7b628d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEAD_VECTOR_EXPR = """
    setweight(to_tsvector('simple', coalesce(first_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(last_name, '')), 'A') ||
    setweight(to_tsvector('simple', regexp_replace(coalesce(email, ''), '[@.]', ' ', 'g')), 'B') ||
    setweight(to_tsvector('simple', coalesce(company, '')), 'B')
"""

_CUSTOMER_VECTOR_EXPR = """
    setweight(to_tsvector('simple', coalesce(first_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(last_name, '')), 'A') ||
    setweight(to_tsvector('simple', regexp_replace(coalesce(email, ''), '[@.]', ' ', 'g')), 'B') ||
    setweight(to_tsvector('simple', coalesce(company, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(industry, '')), 'C')
"""

_OLD_LEAD_VECTOR_EXPR = """
    setweight(to_tsvector('simple', coalesce(first_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(last_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(email, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(company, '')), 'B')
"""

_OLD_CUSTOMER_VECTOR_EXPR = """
    setweight(to_tsvector('simple', coalesce(first_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(last_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(email, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(company, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(industry, '')), 'C')
"""


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_leads_search_vector")
    op.execute("ALTER TABLE leads DROP COLUMN search_vector")
    op.execute(
        f"ALTER TABLE leads ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_LEAD_VECTOR_EXPR}) STORED"
    )
    op.execute(
        "CREATE INDEX idx_leads_search_vector ON leads USING gin (search_vector)"
    )

    op.execute("DROP INDEX IF EXISTS idx_customers_search_vector")
    op.execute("ALTER TABLE customers DROP COLUMN search_vector")
    op.execute(
        f"ALTER TABLE customers ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_CUSTOMER_VECTOR_EXPR}) STORED"
    )
    op.execute(
        "CREATE INDEX idx_customers_search_vector "
        "ON customers USING gin (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_customers_search_vector")
    op.execute("ALTER TABLE customers DROP COLUMN search_vector")
    op.execute(
        f"ALTER TABLE customers ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_OLD_CUSTOMER_VECTOR_EXPR}) STORED"
    )
    op.execute(
        "CREATE INDEX idx_customers_search_vector "
        "ON customers USING gin (search_vector)"
    )

    op.execute("DROP INDEX IF EXISTS idx_leads_search_vector")
    op.execute("ALTER TABLE leads DROP COLUMN search_vector")
    op.execute(
        f"ALTER TABLE leads ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_OLD_LEAD_VECTOR_EXPR}) STORED"
    )
    op.execute(
        "CREATE INDEX idx_leads_search_vector ON leads USING gin (search_vector)"
    )
