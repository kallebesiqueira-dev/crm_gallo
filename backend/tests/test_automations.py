"""Automation rules — CRUD/RBAC over HTTP + the engine (event runner,
stale scan, idempotency) driven directly.

CRUD/validation/RBAC go through the sync TestClient. The async engine
(`run_event_automations`, `scan_org_stale_leads`) runs on the pytest-asyncio
loop, so — like `test_imports_worker` — we build a dedicated `crm_app`
async engine bound to that loop with the org-GUC listener, and monkeypatch
`app.automations.SessionLocal` so the event handler opens its sessions on
the test loop (not the TestClient's portal loop).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.automations import run_event_automations, scan_org_stale_leads
from app.config import get_settings
from app.database import register_org_guc, set_current_org_id
from app.events import EventType
from app.events_dispatcher import EventContext
from app.models import (
    AutomationAction,
    AutomationRule,
    AutomationTrigger,
    Currency,
    Deal,
    DealStage,
    Lead,
    LeadStage,
)

settings = get_settings()


# ---------- CRUD / validation / RBAC (sync HTTP) ----------


def test_admin_creates_and_lists_rule(admin_client, admin_user):
    r = admin_client.post(
        "/api/automations",
        json={
            "name": "Follow up new lead",
            "trigger": "lead_created",
            "action": "create_task",
            "action_config": {"title": "Call the lead", "due_in_days": 2, "assignee": "owner"},
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["trigger"] == "lead_created"
    assert body["action_config"]["due_in_days"] == 2
    assert body["run_count"] == 0

    listed = admin_client.get("/api/automations")
    assert listed.status_code == 200
    assert any(row["id"] == body["id"] for row in listed.json())


def test_non_admin_cannot_create(other_client):
    r = other_client.post(
        "/api/automations",
        json={
            "name": "x",
            "trigger": "lead_created",
            "action": "send_notification",
            "action_config": {"title": "hi"},
        },
    )
    assert r.status_code == 403


def test_change_stage_requires_valid_stage_and_deal_trigger(admin_client):
    # Missing to_stage → 422.
    r = admin_client.post(
        "/api/automations",
        json={
            "name": "bad",
            "trigger": "deal_created",
            "action": "change_stage",
            "action_config": {},
        },
    )
    assert r.status_code == 422
    # Valid stage but a lead trigger → 422 (change_stage needs a deal).
    r = admin_client.post(
        "/api/automations",
        json={
            "name": "bad2",
            "trigger": "lead_created",
            "action": "change_stage",
            "action_config": {"to_stage": "qualified"},
        },
    )
    assert r.status_code == 422
    # Valid combo → 201.
    r = admin_client.post(
        "/api/automations",
        json={
            "name": "ok",
            "trigger": "deal_created",
            "action": "change_stage",
            "action_config": {"to_stage": "qualified"},
        },
    )
    assert r.status_code == 201, r.text


def test_update_and_delete(admin_client):
    rid = admin_client.post(
        "/api/automations",
        json={
            "name": "n",
            "trigger": "deal_won",
            "action": "send_notification",
            "action_config": {"title": "won!"},
        },
    ).json()["id"]

    patched = admin_client.patch(f"/api/automations/{rid}", json={"enabled": False})
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    assert admin_client.delete(f"/api/automations/{rid}").status_code == 204
    assert admin_client.get("/api/automations").json() == [] or all(
        row["id"] != rid for row in admin_client.get("/api/automations").json()
    )


def test_cross_org_rule_not_visible(admin_client, db: Session, other_org):
    db.execute(
        text(
            "INSERT INTO automation_rules "
            "(id, organization_id, name, enabled, trigger, action, action_config) "
            "VALUES (gen_random_uuid(), :org, 'foreign', true, 'lead_created', "
            " 'create_task', '{}')"
        ),
        {"org": other_org.id},
    )
    db.commit()
    rows = admin_client.get("/api/automations").json()
    assert rows == []


def test_runs_endpoint_scoped_to_org(admin_client, admin_user, db: Session, test_org, other_org):
    # A rule + run in MY org, and a run in another org that must not leak.
    rule_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO automation_rules "
            "(id, organization_id, name, enabled, trigger, action, action_config) "
            "VALUES (:id, :org, 'r', true, 'lead_created', 'create_task', '{}')"
        ),
        {"id": rule_id, "org": test_org.id},
    )
    db.execute(
        text(
            "INSERT INTO automation_runs "
            "(id, rule_id, organization_id, idempotency_key, status) "
            "VALUES (gen_random_uuid(), :rid, :org, :k, 'success')"
        ),
        {"rid": rule_id, "org": test_org.id, "k": f"{rule_id}:mine"},
    )
    db.execute(
        text(
            "INSERT INTO automation_runs "
            "(id, rule_id, organization_id, idempotency_key, status) "
            "VALUES (gen_random_uuid(), :rid, :org, :k, 'success')"
        ),
        {"rid": rule_id, "org": other_org.id, "k": f"{rule_id}:foreign"},
    )
    db.commit()

    runs = admin_client.get("/api/automations/runs").json()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"


# ---------- Engine (async, test-loop SessionLocal) ----------


@pytest.fixture
async def auto_session(monkeypatch):
    """Async `crm_app` sessionmaker bound to the test loop, patched into
    `app.automations` so the event handler runs under RLS on this loop."""
    engine = create_async_engine(settings.runtime_database_url, future=True)
    register_org_guc(engine)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.automations.SessionLocal", SessionLocal)
    try:
        yield SessionLocal
    finally:
        await engine.dispose()


def _seed_rule(db, org_id, *, trigger, action, config, enabled=True, name="rule"):
    rule = AutomationRule(
        organization_id=org_id,
        name=name,
        enabled=enabled,
        trigger=trigger,
        action=action,
        action_config=json.dumps(config),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _lead_event(org_id, lead_id, owner_id):
    return EventContext(
        event_id=uuid.uuid4(),
        event_type=EventType.lead_created.value,
        organization_id=org_id,
        payload={"lead_id": str(lead_id), "owner_id": str(owner_id)},
        occurred_at=datetime.now(UTC),
    )


async def test_event_create_task_fires(auto_session, db: Session, test_org, admin_user):
    lead = Lead(
        organization_id=test_org.id,
        first_name="A",
        last_name="A",
        stage=LeadStage.new,
        owner_id=admin_user.id,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    rule = _seed_rule(
        db,
        test_org.id,
        trigger=AutomationTrigger.lead_created,
        action=AutomationAction.create_task,
        config={"title": "Follow up", "assignee": "owner"},
    )

    await run_event_automations(_lead_event(test_org.id, lead.id, admin_user.id))

    tasks = (
        db.execute(
            text("SELECT title, assignee_id, lead_id FROM tasks WHERE organization_id = :o"),
            {"o": test_org.id},
        )
        .mappings()
        .all()
    )
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Follow up"
    assert tasks[0]["assignee_id"] == admin_user.id
    assert tasks[0]["lead_id"] == lead.id

    db.refresh(rule)
    assert rule.run_count == 1
    runs = (
        db.execute(text("SELECT status FROM automation_runs WHERE rule_id = :r"), {"r": rule.id})
        .scalars()
        .all()
    )
    assert runs == ["success"]


async def test_event_is_idempotent(auto_session, db: Session, test_org, admin_user):
    lead = Lead(
        organization_id=test_org.id,
        first_name="B",
        last_name="B",
        stage=LeadStage.new,
        owner_id=admin_user.id,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    rule = _seed_rule(
        db,
        test_org.id,
        trigger=AutomationTrigger.lead_created,
        action=AutomationAction.create_task,
        config={"title": "once"},
    )
    ctx = _lead_event(test_org.id, lead.id, admin_user.id)

    await run_event_automations(ctx)
    await run_event_automations(ctx)  # same event_id → deduped

    n_tasks = db.execute(
        text("SELECT count(*) FROM tasks WHERE organization_id = :o"), {"o": test_org.id}
    ).scalar_one()
    assert n_tasks == 1
    db.refresh(rule)
    assert rule.run_count == 1


async def test_disabled_rule_does_nothing(auto_session, db: Session, test_org, admin_user):
    lead = Lead(
        organization_id=test_org.id,
        first_name="C",
        last_name="C",
        stage=LeadStage.new,
        owner_id=admin_user.id,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    _seed_rule(
        db,
        test_org.id,
        trigger=AutomationTrigger.lead_created,
        action=AutomationAction.create_task,
        config={"title": "nope"},
        enabled=False,
    )

    await run_event_automations(_lead_event(test_org.id, lead.id, admin_user.id))

    n_tasks = db.execute(
        text("SELECT count(*) FROM tasks WHERE organization_id = :o"), {"o": test_org.id}
    ).scalar_one()
    assert n_tasks == 0


async def test_change_stage_action(auto_session, db: Session, test_org, admin_user):
    deal = Deal(
        organization_id=test_org.id,
        title="D",
        value=Decimal("100"),
        currency=Currency.EUR,
        stage=DealStage.new,
        owner_id=admin_user.id,
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)
    rule = _seed_rule(
        db,
        test_org.id,
        trigger=AutomationTrigger.deal_created,
        action=AutomationAction.change_stage,
        config={"to_stage": "qualified"},
    )
    ctx = EventContext(
        event_id=uuid.uuid4(),
        event_type=EventType.deal_created.value,
        organization_id=test_org.id,
        payload={"deal_id": str(deal.id), "owner_id": str(admin_user.id)},
        occurred_at=datetime.now(UTC),
    )

    await run_event_automations(ctx)

    db.refresh(deal)
    assert deal.stage == DealStage.qualified
    db.refresh(rule)
    assert rule.run_count == 1

    # Re-fire of the same event is deduped → no second move, no error.
    await run_event_automations(ctx)
    db.refresh(rule)
    assert rule.run_count == 1


async def test_stale_scan_fires_once_per_day(auto_session, db: Session, test_org, admin_user):
    old = datetime.now(UTC) - timedelta(days=30)
    stale = Lead(
        organization_id=test_org.id,
        first_name="Old",
        last_name="Lead",
        stage=LeadStage.new,
        owner_id=admin_user.id,
    )
    stale.updated_at = old
    db.add(stale)
    # A fresh lead that must NOT trigger.
    db.add(
        Lead(
            organization_id=test_org.id,
            first_name="Fresh",
            last_name="Lead",
            stage=LeadStage.new,
            owner_id=admin_user.id,
        )
    )
    db.commit()
    rule = _seed_rule(
        db,
        test_org.id,
        trigger=AutomationTrigger.lead_stale,
        action=AutomationAction.create_task,
        config={"title": "Stale!", "stale_days": 7},
    )

    set_current_org_id(test_org.id)
    async with auto_session() as adb:
        await scan_org_stale_leads(adb, test_org.id)

    tasks = (
        db.execute(
            text("SELECT title, lead_id FROM tasks WHERE organization_id = :o"), {"o": test_org.id}
        )
        .mappings()
        .all()
    )
    assert len(tasks) == 1
    assert tasks[0]["lead_id"] == stale.id

    # Second scan same day → idempotent (one task total).
    set_current_org_id(test_org.id)
    async with auto_session() as adb:
        await scan_org_stale_leads(adb, test_org.id)
    n = db.execute(
        text("SELECT count(*) FROM tasks WHERE organization_id = :o"), {"o": test_org.id}
    ).scalar_one()
    assert n == 1
    db.refresh(rule)
    assert rule.run_count == 1
