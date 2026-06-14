"""FX rate layer — service math, /api/fx/rates endpoint, dashboard provenance.

The `refresh_fx_rates` worker job (httpx fetch + UPSERT) is NOT driven
directly here for the same reason as the webhook delivery job: invoking an
async worker coroutine via asyncio.run from a sync test binds a fresh
asyncpg pool to a throwaway loop and poisons the session-scoped TestClient
portal. Its read side is covered through the HTTP endpoints (which seed
`fx_rates` exactly as the job would) and its fetch/parse is exercised by the
live worker smoke.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.fx import STATIC_FALLBACK, FxSnapshot


@pytest.fixture(autouse=True)
def _clean_fx(db: Session):
    """fx_rates is global (not pytest-namespaced), so the standard cleanup
    won't touch it — wipe it around every fx test for determinism."""
    db.execute(text("DELETE FROM fx_rates"))
    db.commit()
    yield
    db.execute(text("DELETE FROM fx_rates"))
    db.commit()


def _seed(db: Session, quote: str, rate: str, as_of: str = "2026-06-13"):
    db.execute(
        text(
            "INSERT INTO fx_rates (base, quote, rate, as_of, source, fetched_at) "
            "VALUES ('EUR', :q, :r, :a, 'frankfurter', now())"
        ),
        {"q": quote, "r": rate, "a": as_of},
    )


# ---------- Service math (pure, deterministic) ----------


def test_to_eur_multipliers_inverts_rate():
    snap = FxSnapshot(
        rates={"EUR": Decimal("1"), "USD": Decimal("2"), "GBP": Decimal("0.8")},
        as_of=date(2026, 6, 13),
        source="frankfurter",
    )
    mult = snap.to_eur_multipliers()
    assert mult["EUR"] == Decimal("1")
    # 1 EUR = 2 USD → 1 USD = 0.5 EUR
    assert mult["USD"] == Decimal("0.5")
    # 1 EUR = 0.8 GBP → 1 GBP = 1.25 EUR
    assert mult["GBP"] == Decimal("1.25")


def test_convert_roundtrips_via_eur():
    snap = FxSnapshot(
        rates={"EUR": Decimal("1"), "USD": Decimal("1.25")},
        as_of=None,
        source="static-fallback",
    )
    # 100 USD → EUR → USD is identity
    assert snap.convert(Decimal("100"), "USD", "USD") == Decimal("100")
    # 100 USD at 1 EUR = 1.25 USD → 80 EUR
    assert snap.convert(Decimal("100"), "USD", "EUR") == Decimal("80")
    # unknown currency treated as EUR (multiplier 1)
    assert snap.convert(Decimal("50"), "ZZZ", "EUR") == Decimal("50")


# ---------- GET /api/fx/rates ----------


def test_fx_rates_requires_auth(client):
    assert client.get("/api/fx/rates").status_code == 401


def test_fx_rates_static_fallback_when_empty(admin_client):
    body = admin_client.get("/api/fx/rates").json()
    assert body["source"] == "static-fallback"
    assert body["as_of"] is None
    assert body["base"] == "EUR"
    assert body["rates"]["EUR"] == 1.0
    # Fallback covers the documented currencies.
    assert set(STATIC_FALLBACK).issubset(body["rates"].keys())


def test_fx_rates_reads_db(admin_client, db: Session):
    _seed(db, "USD", "1.08")
    _seed(db, "GBP", "0.85")
    db.commit()
    body = admin_client.get("/api/fx/rates").json()
    assert body["source"] == "frankfurter"
    assert body["as_of"] == "2026-06-13"
    assert body["rates"]["USD"] == 1.08
    assert body["rates"]["GBP"] == 0.85
    assert body["rates"]["EUR"] == 1.0  # base always present


# ---------- Dashboard provenance ----------


def test_dashboard_carries_fx_provenance_fallback(admin_client):
    body = admin_client.get("/api/dashboard/stats").json()
    assert "fx_rates" in body and "fx_as_of" in body and "fx_source" in body
    assert body["fx_source"] == "static-fallback"
    assert body["fx_as_of"] is None
    assert body["fx_rates"]["EUR"] == 1.0


def test_dashboard_uses_live_rates(admin_client, db: Session):
    _seed(db, "USD", "1.10")
    db.commit()
    body = admin_client.get("/api/dashboard/stats").json()
    assert body["fx_source"] == "frankfurter"
    assert body["fx_as_of"] == "2026-06-13"
    assert body["fx_rates"]["USD"] == 1.10
