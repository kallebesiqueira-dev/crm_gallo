"""Money columns: double precision -> Numeric (ADR-015 / TD-30).

Float money silently drifts (0.1 + 0.2 != 0.3); every monetary amount
moves to fixed-scale Numeric so per-line rounding and summation are exact.

Scales:
  leads.budget                 numeric(12, 2)
  deals.value                  numeric(12, 2)
  quotes.subtotal              numeric(12, 2)
  quotes.tax_amount            numeric(12, 2)
  quotes.total                 numeric(12, 2)
  quotes.tax_rate              numeric(6, 3)   -- a percentage (7.7 -> 7.7%)
  quote_line_items.quantity    numeric(12, 3)  -- fractional units (hours, kg)
  quote_line_items.unit_price  numeric(12, 2)
  quote_line_items.line_total  numeric(12, 2)

The USING casts round existing float values to the target scale. NOT NULL
columns keep their constraint; only the type changes.
"""

from alembic import op

revision = "d9f1a2b3c4e5"
down_revision = "c8e4d3f9a1b2"
branch_labels = None
depends_on = None


# (table, column, precision, scale)
_MONEY_COLUMNS = [
    ("leads", "budget", 12, 2),
    ("deals", "value", 12, 2),
    ("quotes", "subtotal", 12, 2),
    ("quotes", "tax_amount", 12, 2),
    ("quotes", "total", 12, 2),
    ("quotes", "tax_rate", 6, 3),
    ("quote_line_items", "quantity", 12, 3),
    ("quote_line_items", "unit_price", 12, 2),
    ("quote_line_items", "line_total", 12, 2),
]


def upgrade() -> None:
    for table, column, precision, scale in _MONEY_COLUMNS:
        op.execute(
            f'ALTER TABLE {table} '
            f'ALTER COLUMN {column} TYPE numeric({precision}, {scale}) '
            f'USING {column}::numeric({precision}, {scale})'
        )


def downgrade() -> None:
    for table, column, _precision, _scale in _MONEY_COLUMNS:
        op.execute(
            f'ALTER TABLE {table} '
            f'ALTER COLUMN {column} TYPE double precision '
            f'USING {column}::double precision'
        )
