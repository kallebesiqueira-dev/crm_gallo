"""Dashboard `/stats` aggregate parity.

Locks the numeric output of the dashboard aggregates so the server-side
`GROUP BY` rewrite (which replaced per-row Python summation) keeps
producing identical figures. Money is mostly EUR (FX multiplier 1.0) so
the assertions are independent of live rates; a single USD deal + a
seeded USD rate exercises the multi-currency `(stage, currency)`
grouping deterministically (1 EUR = 2 USD → 1 USD = 0.5 EUR).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    Currency,
    Deal,
    DealStage,
    Lead,
    LeadStage,
    Organization,
    Quote,
    QuoteStatus,
)


@pytest.fixture(autouse=True)
def _clean_fx(db: Session):
    """fx_rates is global (not pytest-namespaced); wipe around each test
    and seed a deterministic USD rate so EUR conversions are exact."""
    db.execute(text("DELETE FROM fx_rates"))
    db.execute(
        text(
            "INSERT INTO fx_rates (base, quote, rate, as_of, source, fetched_at) "
            "VALUES ('EUR', 'USD', '2.0', '2026-06-13', 'frankfurter', now())"
        )
    )
    db.commit()
    yield
    db.execute(text("DELETE FROM fx_rates"))
    db.commit()


def _seed(db: Session, org: Organization) -> None:
    now = datetime.now(UTC)
    two_months_ago = now - timedelta(days=62)
    oid = org.id

    # Leads: 3 new (two scored 80/100, one unscored), 2 won, 1 lost.
    db.add_all(
        [
            Lead(organization_id=oid, first_name="A", last_name="X", stage=LeadStage.new),
            Lead(
                organization_id=oid, first_name="B", last_name="X", stage=LeadStage.new, ai_score=80
            ),
            Lead(
                organization_id=oid,
                first_name="C",
                last_name="X",
                stage=LeadStage.new,
                ai_score=100,
            ),
            Lead(organization_id=oid, first_name="D", last_name="X", stage=LeadStage.won),
            Lead(organization_id=oid, first_name="E", last_name="X", stage=LeadStage.won),
            Lead(organization_id=oid, first_name="F", last_name="X", stage=LeadStage.lost),
        ]
    )

    # Deals: open (new/qualified/negotiation) incl. one USD; won x2 (this
    # month + 2 months ago); one lost (excluded from pipeline + funnel).
    db.add_all(
        [
            Deal(organization_id=oid, title="d1", value="1000", stage=DealStage.new),
            Deal(organization_id=oid, title="d2", value="2000", stage=DealStage.qualified),
            Deal(
                organization_id=oid,
                title="d3-usd",
                value="100",
                currency=Currency.USD,
                stage=DealStage.qualified,
            ),
            Deal(organization_id=oid, title="d4", value="500", stage=DealStage.negotiation),
            Deal(
                organization_id=oid,
                title="w1",
                value="3000",
                stage=DealStage.won,
                updated_at=now,
            ),
            Deal(
                organization_id=oid,
                title="w2",
                value="1000",
                stage=DealStage.won,
                updated_at=two_months_ago,
            ),
            Deal(organization_id=oid, title="l1", value="9999", stage=DealStage.lost),
        ]
    )

    today = now.date()
    db.add_all(
        [
            Quote(
                organization_id=oid,
                number="Q1",
                title="q",
                status=QuoteStatus.draft,
                total="100",
            ),
            Quote(
                organization_id=oid,
                number="Q2",
                title="q",
                status=QuoteStatus.sent,
                total="200",
                valid_until=today + timedelta(days=10),
            ),
            Quote(
                organization_id=oid,
                number="Q3",
                title="q",
                status=QuoteStatus.sent,
                total="300",
                valid_until=today - timedelta(days=10),
            ),
            Quote(
                organization_id=oid,
                number="Q4",
                title="q",
                status=QuoteStatus.accepted,
                total="400",
            ),
            Quote(
                organization_id=oid,
                number="Q5",
                title="q",
                status=QuoteStatus.declined,
                total="500",
            ),
            Quote(
                organization_id=oid,
                number="Q6",
                title="q",
                status=QuoteStatus.expired,
                total="600",
            ),
        ]
    )
    db.commit()


def test_dashboard_stats_aggregates(admin_client, admin_user, test_org: Organization, db: Session):
    _seed(db, test_org)

    body = admin_client.get("/api/dashboard/stats").json()

    # Leads ----------------------------------------------------------------
    assert body["total_leads"] == 6
    assert body["leads_by_stage"]["new"] == 3
    assert body["leads_by_stage"]["won"] == 2
    assert body["leads_by_stage"]["lost"] == 1
    assert body["won_count"] == 2
    assert body["lost_count"] == 1
    assert body["conversion_rate"] == round(2 / 3, 4)
    assert body["avg_ai_score"] == 90.0  # (80 + 100) / 2, NULLs ignored

    # Counts ---------------------------------------------------------------
    assert body["total_customers"] == 0
    assert body["total_deals"] == 7  # 4 open + 2 won + 1 lost

    # Pipeline (open deals only; USD 100 → 50 EUR) -------------------------
    assert body["pipeline_value_eur"] == 3550.0  # 1000 + 2000 + 500 + 50
    assert body["pipeline_value_by_currency"] == {"EUR": 3500.0, "USD": 100.0}

    # Funnel (lost excluded; won included) ---------------------------------
    funnel = {row["stage"]: row for row in body["pipeline_funnel"]}
    assert funnel["new"]["count"] == 1 and funnel["new"]["value_eur"] == 1000.0
    assert funnel["qualified"]["count"] == 2 and funnel["qualified"]["value_eur"] == 2050.0
    assert funnel["proposal_sent"]["count"] == 0
    assert funnel["negotiation"]["count"] == 1 and funnel["negotiation"]["value_eur"] == 500.0
    assert funnel["won"]["count"] == 2 and funnel["won"]["value_eur"] == 4000.0

    # Monthly revenue (won deals) ------------------------------------------
    assert body["revenue_total_eur"] == 4000.0
    months = {row["month"]: row["value_eur"] for row in body["monthly_revenue"]}
    this_month = datetime.now(UTC).strftime("%Y-%m")
    assert months[this_month] == 3000.0
    assert sum(row["value_eur"] for row in body["monthly_revenue"]) == 4000.0

    # Quotes ----------------------------------------------------------------
    q = body["quotes"]
    assert q["total_eur"] == 2100.0
    assert q["outstanding_eur"] == 600.0  # draft + sent
    assert q["accepted_eur"] == 400.0
    assert q["rejected_eur"] == 1100.0  # declined + expired
    assert q["open_eur"] == 200.0  # sent, future valid_until
    assert q["overdue_eur"] == 300.0  # sent, past valid_until
