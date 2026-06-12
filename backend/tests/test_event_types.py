"""The three previously-missing outbox event types (skills.md backlog):

  customer.created — emitted on POST /api/customers AND on lead
                     conversion (new contact only, never on reuse)
  user.invited     — emitted on invite create
  task.overdue     — emitted by the worker's daily sweep, once per
                     (task, due_date), deduped against prior outbox rows

Plus the automation wiring: `customer_created` rules fire through
`run_event_automations` like any event-family trigger.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.automations import run_event_automations
from app.config import get_settings
from app.database import register_org_guc, set_current_org_id
from app.events import EventType
from app.events_dispatcher import EventContext
from app.models import AutomationAction, AutomationRule, AutomationTrigger, Organization, User
from app.worker.jobs import scan_org_overdue_tasks
from tests.conftest import CsrfAwareClient

settings = get_settings()


def _outbox_payloads(db: Session, org_id, event_type: str) -> list[dict]:
    rows = (
        db.execute(
            text(
                "SELECT payload FROM outbox_events"
                " WHERE organization_id = :org AND event_type = :et"
            ),
            {"org": str(org_id), "et": event_type},
        )
        .scalars()
        .all()
    )
    return [json.loads(r or "{}") for r in rows]


def test_customer_create_emits_event(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, admin_user: User
):
    r = admin_client.post(
        "/api/customers",
        json={"first_name": "Event", "last_name": "Probe", "email": "pytest-evt-c@example.com"},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    events = [
        p
        for p in _outbox_payloads(db, test_org.id, "customer.created")
        if p.get("customer_id") == cid
    ]
    assert len(events) == 1
    assert events[0]["actor_user_id"] == str(admin_user.id)


def test_invite_create_emits_event(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, admin_user: User
):
    r = admin_client.post(
        "/api/orgs/current/invites",
        json={"email": "pytest-evt-invite@example.com", "role": "sales_agent"},
    )
    assert r.status_code in (200, 201), r.text

    events = [
        p
        for p in _outbox_payloads(db, test_org.id, "user.invited")
        if p.get("email") == "pytest-evt-invite@example.com"
    ]
    assert len(events) == 1
    assert events[0]["role"] == "sales_agent"
    # owner_id = the inviter, so notification actions reach them.
    assert events[0]["owner_id"] == str(admin_user.id)


def test_lead_convert_emits_customer_created_once(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    lead = admin_client.post(
        "/api/leads",
        json={
            "first_name": "Conv",
            "last_name": "Event",
            "email": "pytest-evt-conv@example.com",
            "stage": "qualified",
        },
    ).json()
    out = admin_client.post(f"/api/leads/{lead['id']}/convert").json()

    events = [
        p
        for p in _outbox_payloads(db, test_org.id, "customer.created")
        if p.get("customer_id") == out["customer_id"]
    ]
    assert len(events) == 1
    assert events[0]["source"] == "lead_conversion"


# ---------- task.overdue sweep (worker, per-org helper) ----------


@pytest.fixture
async def worker_session(monkeypatch):
    """Async crm_app sessionmaker on the test loop (RLS + org GUC) —
    same pattern as test_automations."""
    engine = create_async_engine(settings.runtime_database_url, future=True)
    register_org_guc(engine)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield SessionLocal
    finally:
        await engine.dispose()


async def test_overdue_sweep_emits_once_per_task_and_due_date(
    worker_session, admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    task = admin_client.post("/api/tasks", json={"title": "pytest-evt overdue"}).json()
    done = admin_client.post("/api/tasks", json={"title": "pytest-evt done"}).json()
    db.execute(
        text("UPDATE tasks SET due_date = current_date - 1 WHERE id IN (:a, :b)"),
        {"a": task["id"], "b": done["id"]},
    )
    db.execute(text("UPDATE tasks SET status = 'done' WHERE id = :b"), {"b": done["id"]})
    db.commit()

    today = datetime.now(UTC).date()
    set_current_org_id(test_org.id)
    async with worker_session() as wdb:
        emitted = await scan_org_overdue_tasks(wdb, test_org.id, today)
    assert emitted == 1  # the done task is excluded

    events = [
        p
        for p in _outbox_payloads(db, test_org.id, "task.overdue")
        if p.get("task_id") == task["id"]
    ]
    assert len(events) == 1

    # Second sweep: deduped, nothing new.
    set_current_org_id(test_org.id)
    async with worker_session() as wdb:
        emitted = await scan_org_overdue_tasks(wdb, test_org.id, today)
    assert emitted == 0


# ---------- automation wiring: customer_created rules fire ----------


@pytest.fixture
async def auto_session(monkeypatch):
    engine = create_async_engine(settings.runtime_database_url, future=True)
    register_org_guc(engine)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.automations.SessionLocal", SessionLocal)
    try:
        yield SessionLocal
    finally:
        await engine.dispose()


async def test_customer_created_rule_fires(
    auto_session, db: Session, test_org: Organization, admin_user: User
):
    rule = AutomationRule(
        organization_id=test_org.id,
        name="pytest welcome customer",
        enabled=True,
        trigger=AutomationTrigger.customer_created,
        action=AutomationAction.send_notification,
        action_config=json.dumps({"title": "Welcome the new customer"}),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    customer_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO customers (id, organization_id, first_name, last_name,"
            " owner_id, custom_fields, version)"
            " VALUES (:id, :org, 'Auto', 'Customer', :owner, '{}', 0)"
        ),
        {"id": str(customer_id), "org": str(test_org.id), "owner": str(admin_user.id)},
    )
    db.commit()

    ctx = EventContext(
        event_id=uuid.uuid4(),
        event_type=EventType.customer_created.value,
        organization_id=test_org.id,
        payload={"customer_id": str(customer_id), "owner_id": str(admin_user.id)},
        occurred_at=datetime.now(UTC),
    )
    await run_event_automations(ctx)

    run = db.execute(
        text("SELECT status, entity_type FROM automation_runs WHERE rule_id = :r"),
        {"r": str(rule.id)},
    ).first()
    assert run is not None
    assert run.status == "success"
    assert run.entity_type == "customer"

    note = db.execute(
        text("SELECT title FROM notifications WHERE user_id = :u AND title = :t"),
        {"u": str(admin_user.id), "t": "Welcome the new customer"},
    ).first()
    assert note is not None
