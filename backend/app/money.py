"""Money helpers (ADR-015).

Every monetary amount in the system is a `Decimal` stored in a
`Numeric` column — never a binary `float`, which can't represent cents
exactly and drifts under summation. Inputs arrive as JSON numbers and
Pydantic routes them through `str` into `Decimal` (so `0.1` stays
`Decimal('0.1')`, not the float tail); outputs are typed `float` purely
as a clean JSON transport of an already-exact 2-dp value.

`q2` is the single rounding point: quantize to 2 decimal places with
ROUND_HALF_UP (the intuitive "0.005 → 0.01" people expect on an invoice,
not Decimal's default banker's rounding).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")


def q2(amount: Decimal) -> Decimal:
    """Round a Decimal amount to 2 decimal places, half-up."""
    return Decimal(amount).quantize(CENTS, rounding=ROUND_HALF_UP)
