"""Quote money math + number generation (ADR-016).

Totals are NEVER trusted from the client — the API recomputes them from
the line items on every create/update. Kept here (not in the route) so
the worker and tests can call the same logic.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Quote
from app.money import ZERO, q2


def compute_line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return q2(quantity * unit_price)


def recompute_totals(quote: Quote) -> None:
    """Recompute every line_total + the quote's subtotal/tax/total in
    place from `quote.line_items` and `quote.tax_rate`. Mutates the ORM
    objects; the caller owns the flush/commit.

    All money is Decimal (ADR-015) — exact per-line rounding + exact
    summation, no binary-float drift. `tax_rate` is a percentage
    (7.7 → 7.7%). Rounding is applied per line and again on the tax so
    the printed numbers always add up.
    """
    subtotal = ZERO
    for item in quote.line_items:
        item.line_total = compute_line_total(item.quantity, item.unit_price)
        subtotal += item.line_total
    subtotal = q2(subtotal)
    tax_amount = q2(subtotal * quote.tax_rate / Decimal(100))
    quote.subtotal = subtotal
    quote.tax_amount = tax_amount
    quote.total = q2(subtotal + tax_amount)


async def next_quote_number(db: AsyncSession, organization_id: uuid.UUID) -> str:
    """Next human-facing quote number for the org, e.g. `Q-000007`.

    Zero-padded so lexicographic max == numeric max. Includes
    soft-deleted rows (`include_deleted=True`) so a deleted quote's
    number is never silently reused while another revision of it may
    still reference the sequence. Callers must hold a per-org advisory
    lock (see `create_quote`) to make the read-then-insert race-safe;
    the `(organization_id, number, version)` unique index is the
    backstop if two creates still collide.
    """
    result = await db.execute(
        select(func.max(Quote.number))
        .where(Quote.organization_id == organization_id)
        .execution_options(include_deleted=True)
    )
    current = result.scalar_one_or_none()
    if current is None:
        return "Q-000001"
    try:
        n = int(current.rsplit("-", 1)[1]) + 1
    except (IndexError, ValueError):
        # Defensive: a manually-inserted non-conforming number. Fall
        # back to a count-based guess; the unique index still guards.
        n = 1
    return f"Q-{n:06d}"
