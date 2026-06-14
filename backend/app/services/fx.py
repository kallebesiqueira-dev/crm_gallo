"""Foreign-exchange rate layer (launch roadmap #1).

Replaces the old hardcoded ``FX_TO_EUR`` dict in ``app/api/dashboard.py``
with a refreshable, EUR-based rate set persisted in ``fx_rates`` and kept
fresh by the ``refresh_fx_rates`` worker cron (ECB data via frankfurter.app).

Convention (matches the ECB / frankfurter feed): a rate is "1 EUR = ``rate``
units of the quote currency" (e.g. EUR→USD ≈ 1.08). So:

  * amount in ``ccy`` → EUR   : ``amount / rate[ccy]``
  * amount in EUR → ``ccy``   : ``amount * rate[ccy]``

This converts **for display only** (roadmap #1 explicitly allows reversing
the old "no FX" stance, with as-of stamping for honesty). The canonical
stored amount on each deal/quote never changes — see ADR-015.

When the table is empty (fresh deploy before the first cron run, or the
upstream feed is down) the service falls back to ``STATIC_FALLBACK`` and
stamps ``source="static-fallback"`` / ``as_of=None`` so callers can tell
the rates are approximate rather than a dated ECB snapshot.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FxRate

BASE = "EUR"

# EUR-based fallback (1 EUR = X). Kept close to the long-run mid-rates that
# the old dashboard dict implied; only used until the cron lands a real ECB
# snapshot. Quote currencies cover the Currency enum (EUR/CHF/USD/GBP) plus
# BRL (Stripe price point) so the rates endpoint is useful beyond deals.
STATIC_FALLBACK: dict[str, Decimal] = {
    "EUR": Decimal("1"),
    "CHF": Decimal("0.96"),
    "USD": Decimal("1.08"),
    "GBP": Decimal("0.85"),
    "BRL": Decimal("6.20"),
}


class FxSnapshot(NamedTuple):
    """An EUR-based rate set plus provenance.

    ``rates`` always includes ``EUR: 1``. ``as_of`` is the ECB publication
    date for a real snapshot, or ``None`` for the static fallback.
    """

    rates: dict[str, Decimal]
    as_of: date | None
    source: str

    def to_eur_multipliers(self) -> dict[str, Decimal]:
        """Map quote → multiplier that turns an amount in that currency into
        EUR (``1 / rate``). Mirrors the old ``FX_TO_EUR`` dict so callers can
        do ``value * mult[ccy]`` unchanged. Unknown currencies fall back to 1
        at the call site (``.get(ccy, Decimal(1))``)."""
        return {ccy: (Decimal(1) / r if r else Decimal(1)) for ccy, r in self.rates.items()}

    def convert(self, amount: Decimal, frm: str, to: str) -> Decimal:
        """Convert ``amount`` from one currency to another via EUR. Unknown
        currencies are treated as EUR (multiplier 1) — same lenient stance as
        the dashboard's old ``.get(..., 1)``."""
        rf = self.rates.get(frm, Decimal(1))
        rt = self.rates.get(to, Decimal(1))
        eur = amount / rf if rf else amount
        return eur * rt


async def get_snapshot(db: AsyncSession) -> FxSnapshot:
    """Load the current EUR-based rate set from ``fx_rates``.

    Falls back to ``STATIC_FALLBACK`` when the table has no EUR-based rows.
    The most recent ``as_of`` across the rows is reported as the snapshot
    date (the cron writes them all with the same date, so this is just the
    feed's publication date)."""
    rows = (await db.execute(select(FxRate).where(FxRate.base == BASE))).scalars().all()
    if not rows:
        return FxSnapshot(rates=dict(STATIC_FALLBACK), as_of=None, source="static-fallback")
    rates: dict[str, Decimal] = {BASE: Decimal(1)}
    as_of: date | None = None
    source = rows[0].source
    for row in rows:
        rates[row.quote] = Decimal(row.rate)
        if as_of is None or row.as_of > as_of:
            as_of = row.as_of
    return FxSnapshot(rates=rates, as_of=as_of, source=source)
