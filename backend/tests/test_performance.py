"""Performance / KPI: the sales summary aggregates + sales-goal CRUD.

The summary rolls up closed deals (won/lost) in the current period plus an
all-time lead funnel; it's read-only and open to any member. Sales goals are
RLS-scoped and RBAC-gated (admin/manager). Direct seeding uses the owner-role
`db` session; endpoints are exercised over HTTP.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    Currency,
    Deal,
    DealStage,
    GoalMetric,
    GoalPeriod,
    Lead,
    LeadStage,
    Organization,
    SalesGoal,
)


def _today_first() -> str:
    t = datetime.now(timezone.utc).date()
    return t.replace(day=1).isoformat()


def _seed_deal(db, org_id, *, stage, value="1000", currency=Currency.EUR, owner_id=None, updated_at=None):
    deal = Deal(
        organization_id=org_id,
        title="Deal",
        value=Decimal(value),
        currency=currency,
        stage=stage,
        owner_id=owner_id,
    )
    if updated_at is not None:
        deal.updated_at = updated_at
    db.add(deal)
    return deal


# ---------- Summary ----------


def test_summary_aggregates(db: Session, admin_client, test_org, admin_user):
    # Two won deals (EUR + USD) + one lost + one open, all in the current month.
    _seed_deal(db, test_org.id, stage=DealStage.won, value="1000", owner_id=admin_user.id)
    _seed_deal(
        db, test_org.id, stage=DealStage.won, value="1000", currency=Currency.USD,
        owner_id=admin_user.id,
    )
    _seed_deal(db, test_org.id, stage=DealStage.lost, value="500", owner_id=admin_user.id)
    _seed_deal(db, test_org.id, stage=DealStage.new, value="9999", owner_id=admin_user.id)
    db.add(Lead(organization_id=test_org.id, first_name="A", last_name="A", stage=LeadStage.won))
    db.add(Lead(organization_id=test_org.id, first_name="B", last_name="B", stage=LeadStage.new))
    db.commit()

    r = admin_client.get("/api/performance/summary?period=month")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["won_count"] == 2
    assert body["lost_count"] == 1
    # 1000 EUR + 1000 USD * 0.93 = 1930.0
    assert body["won_value_eur"] == 1930.0
    assert body["win_rate"] == round(2 / 3, 4)
    # Leaderboard credits the owner with both won deals.
    assert len(body["leaderboard"]) == 1
    assert body["leaderboard"][0]["won_count"] == 2
    assert body["leaderboard"][0]["owner_name"] == admin_user.full_name
    # Lead funnel covers every stage; conversion = 1 won / 2 total.
    assert {s["stage"] for s in body["lead_funnel"]} == {s.value for s in LeadStage}
    assert body["lead_conversion_rate"] == 0.5


def test_summary_excludes_other_periods(db: Session, admin_client, test_org, admin_user):
    # A deal closed a year ago must not count toward this month.
    old = datetime(2025, 1, 15, tzinfo=timezone.utc)
    _seed_deal(db, test_org.id, stage=DealStage.won, value="5000", owner_id=admin_user.id, updated_at=old)
    db.commit()
    r = admin_client.get("/api/performance/summary?period=month")
    assert r.status_code == 200, r.text
    assert r.json()["won_count"] == 0
    assert r.json()["won_value_eur"] == 0.0


def test_summary_org_scoped(db: Session, admin_client, test_org, other_org, admin_user):
    # A won deal in another org must not leak into this org's summary.
    _seed_deal(db, other_org.id, stage=DealStage.won, value="9999")
    db.commit()
    r = admin_client.get("/api/performance/summary?period=month")
    assert r.status_code == 200, r.text
    assert r.json()["won_count"] == 0


# ---------- Goals ----------


def _goal_payload(**overrides) -> dict:
    payload = {
        "period": "month",
        "period_start": _today_first(),
        "metric": "revenue",
        "target": 10000,
    }
    payload.update(overrides)
    return payload


def test_create_and_list_goal_attainment(db: Session, admin_client, test_org, admin_user):
    # One won deal this month → attainment counts toward a revenue goal.
    _seed_deal(db, test_org.id, stage=DealStage.won, value="2500", owner_id=admin_user.id)
    db.commit()
    r = admin_client.post("/api/performance/goals", json=_goal_payload(target=10000))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["target"] == 10000.0
    assert body["attainment"] == 2500.0
    assert body["attainment_pct"] == 0.25

    lst = admin_client.get("/api/performance/goals")
    assert lst.status_code == 200, lst.text
    assert any(g["id"] == body["id"] for g in lst.json())


def test_goal_deal_count_metric(db: Session, admin_client, test_org, admin_user):
    _seed_deal(db, test_org.id, stage=DealStage.won, owner_id=admin_user.id)
    _seed_deal(db, test_org.id, stage=DealStage.won, owner_id=admin_user.id)
    db.commit()
    r = admin_client.post(
        "/api/performance/goals", json=_goal_payload(metric="deal_count", target=4)
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["attainment"] == 2.0
    assert body["attainment_pct"] == 0.5


def test_update_goal(admin_client):
    g = admin_client.post("/api/performance/goals", json=_goal_payload(target=10000)).json()
    r = admin_client.patch(f"/api/performance/goals/{g['id']}", json={"target": 20000})
    assert r.status_code == 200, r.text
    assert r.json()["target"] == 20000.0


def test_delete_goal(admin_client):
    g = admin_client.post("/api/performance/goals", json=_goal_payload()).json()
    r = admin_client.delete(f"/api/performance/goals/{g['id']}")
    assert r.status_code == 204, r.text
    assert all(x["id"] != g["id"] for x in admin_client.get("/api/performance/goals").json())


def test_create_goal_requires_privilege(other_client):
    # sales_agent is below the admin/manager bar for setting targets.
    r = other_client.post("/api/performance/goals", json=_goal_payload())
    assert r.status_code == 403, r.text


def test_summary_open_to_members(other_client):
    # The read-only summary is open to any member, not just admin/manager.
    r = other_client.get("/api/performance/summary")
    assert r.status_code == 200, r.text


def test_goals_org_scoped(db: Session, admin_client, test_org, other_org):
    foreign = SalesGoal(
        organization_id=other_org.id,
        period=GoalPeriod.month,
        period_start=datetime.now(timezone.utc).date().replace(day=1),
        metric=GoalMetric.revenue,
        target=Decimal("99999"),
    )
    db.add(foreign)
    db.commit()
    r = admin_client.get("/api/performance/goals")
    assert all(g["id"] != str(foreign.id) for g in r.json())
