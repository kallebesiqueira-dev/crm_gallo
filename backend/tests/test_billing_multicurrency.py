"""Multi-currency billing plumbing (plan.md §6, Stripe leg).

Catalog price points + per-currency Stripe Price ID resolution +
checkout currency validation. No test here ever reaches the Stripe
API — the endpoint tests exercise only the paths that fail BEFORE
the network call (free plan, unsupported currency)."""

from __future__ import annotations

from decimal import Decimal

from app.billing.catalog import (
    SUPPORTED_CURRENCIES,
    get_plan,
    resolve_stripe_price_id,
)
from app.config import get_settings
from app.models import BillingCycle, Plan
from tests.conftest import CsrfAwareClient


def test_supported_currencies_and_price_points():
    assert SUPPORTED_CURRENCIES == ("eur", "chf", "gbp", "brl")
    for plan in (Plan.standard, Plan.business, Plan.premium):
        descriptor = get_plan(plan)
        # EUR is the canonical column; every other supported currency
        # must carry a positioned price point.
        assert descriptor.monthly_price("eur") == descriptor.monthly_eur
        for cur in ("chf", "gbp", "brl"):
            price = descriptor.monthly_price(cur)
            assert isinstance(price, Decimal) and price > 0
            # Annual keeps the same 20% discount in every currency.
            assert descriptor.yearly_price_per_user(cur) == (price * Decimal("0.80")).quantize(
                Decimal("0.01")
            )
    # Free has no paid price points.
    assert get_plan(Plan.free).monthly_prices == {}


def test_resolve_price_id_per_currency(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_price_standard_monthly", "price_eur_123")
    monkeypatch.setattr(settings, "stripe_price_standard_monthly_chf", "price_chf_456")
    monkeypatch.setattr(settings, "stripe_price_standard_monthly_gbp", "")

    # EUR keeps the legacy env name — zero-change for existing deploys.
    assert resolve_stripe_price_id(Plan.standard, BillingCycle.monthly) == "price_eur_123"
    assert resolve_stripe_price_id(Plan.standard, BillingCycle.monthly, "eur") == "price_eur_123"
    assert resolve_stripe_price_id(Plan.standard, BillingCycle.monthly, "chf") == "price_chf_456"
    # Unset currency variant → None (NOT an EUR fallback: charging the
    # wrong currency is worse than a clear "not available").
    assert resolve_stripe_price_id(Plan.standard, BillingCycle.monthly, "gbp") is None


def test_checkout_rejects_unsupported_currency(admin_client: CsrfAwareClient):
    r = admin_client.post(
        "/api/billing/checkout",
        json={"plan": "standard", "billing_cycle": "monthly", "currency": "usd"},
    )
    assert r.status_code == 400
    assert "Unsupported currency" in r.json()["detail"]


def test_checkout_currency_is_case_insensitive_validated(admin_client: CsrfAwareClient):
    """Uppercase ISO code must pass the currency gate (it's lowered
    server-side). The request then dies on Stripe config — 503 when no
    API key, 502 when the CHF price id is unset — both BEFORE any
    network call, and both prove 'CHF' was not rejected with the 400."""
    r = admin_client.post(
        "/api/billing/checkout",
        json={"plan": "standard", "billing_cycle": "monthly", "currency": "CHF"},
    )
    assert r.status_code in (502, 503), r.text
    assert "Unsupported currency" not in r.text
