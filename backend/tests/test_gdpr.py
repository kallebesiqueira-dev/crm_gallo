"""GDPR forget/export endpoints (plan.md §5, right to erasure +
portability). Admin-only; PII anonymized in place keeping the id as
the audit anchor; notes hard-deleted; timeline content stripped."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import register_org_guc, set_current_org_id
from app.models import Activity, AuditLog, Lead, Note, Organization
from tests.conftest import CsrfAwareClient

settings = get_settings()


def _make_lead(client: CsrfAwareClient, **overrides) -> dict:
    body = {
        "first_name": "Erase",
        "last_name": "Me",
        "email": "pytest-gdpr@example.com",
        "phone": "+41791112233",
        "company": "Pytest GDPR GmbH",
        "notes": "secret preference: vegan",
        "stage": "new",
        **overrides,
    }
    r = client.post("/api/leads", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_forget_anonymizes_lead_and_purges_notes(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    lead = _make_lead(admin_client)
    lead_id = lead["id"]
    # Attach a note (free-form PII).
    r = admin_client.post(
        "/api/notes",
        json={"entity_type": "lead", "entity_id": lead_id, "body": "phone home at 18h"},
    )
    assert r.status_code == 201, r.text

    r = admin_client.post(f"/api/leads/{lead_id}/forget")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "forgotten"

    # The row is soft-deleted by /forget, so opt out of the global
    # SoftDeleteMixin filter to inspect it.
    row = db.get(Lead, uuid.UUID(lead_id), execution_options={"include_deleted": True})
    assert row.first_name == "Anonymized"
    assert row.email is None
    assert row.phone is None
    assert row.company is None
    assert row.notes is None
    assert row.custom_fields == {}
    # Soft-deleted: gone from lists, id survives for the audit trail.
    assert row.deleted_at is not None
    assert admin_client.get(f"/api/leads/{lead_id}").status_code == 404

    # Notes hard-deleted, timeline content stripped.
    notes = db.execute(select(Note).where(Note.entity_id == uuid.UUID(lead_id))).scalars().all()
    assert notes == []
    acts = (
        db.execute(
            select(Activity).where(
                Activity.entity_type == "lead", Activity.entity_id == uuid.UUID(lead_id)
            )
        )
        .scalars()
        .all()
    )
    assert acts, "timeline skeleton must survive"
    assert all(a.content is None and a.metadata_json is None for a in acts)

    # Audit row, with NO PII in metadata — only how it was driven.
    audit = (
        db.execute(
            select(AuditLog).where(
                AuditLog.action == "lead.gdpr_forget", AuditLog.entity_id == lead_id
            )
        )
        .scalars()
        .first()
    )
    assert audit is not None
    assert json.loads(audit.metadata_json) == {"via": "api"}


def test_forget_is_idempotent(admin_client: CsrfAwareClient):
    lead = _make_lead(admin_client, email="pytest-gdpr-twice@example.com")
    assert admin_client.post(f"/api/leads/{lead['id']}/forget").status_code == 200
    # Second call still 200 — already-anonymized row is reachable
    # (include_deleted) and re-wiping is harmless.
    assert admin_client.post(f"/api/leads/{lead['id']}/forget").status_code == 200


def test_export_returns_fields_notes_and_timeline(admin_client: CsrfAwareClient):
    lead = _make_lead(admin_client, email="pytest-gdpr-export@example.com")
    admin_client.post(
        "/api/notes",
        json={"entity_type": "lead", "entity_id": lead["id"], "body": "exportable note"},
    )
    r = admin_client.get(f"/api/leads/{lead['id']}/export")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["lead"]["email"] == "pytest-gdpr-export@example.com"
    assert [n["body"] for n in data["notes"]] == ["exportable note"]
    assert any(t["type"] == "created" for t in data["timeline"])
    assert data["entity_type"] == "lead"


def test_customer_forget_and_export(admin_client: CsrfAwareClient, db: Session):
    r = admin_client.post(
        "/api/customers",
        json={
            "first_name": "Cust",
            "last_name": "Erase",
            "email": "pytest-gdpr-cust@example.com",
            "phone": "+41790009999",
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    data = admin_client.get(f"/api/customers/{cid}/export").json()
    assert data["customer"]["email"] == "pytest-gdpr-cust@example.com"
    assert "deals" in data  # customers also export associated deals

    assert admin_client.post(f"/api/customers/{cid}/forget").status_code == 200
    from app.models import Customer

    row = db.get(Customer, uuid.UUID(cid), execution_options={"include_deleted": True})
    assert row.email is None and row.first_name == "Anonymized"
    assert row.deleted_at is not None


def test_forget_requires_admin(other_client: CsrfAwareClient, db: Session, test_org):
    row = db.execute(
        text(
            "INSERT INTO leads (id, organization_id, first_name, last_name, stage,"
            " custom_fields, version)"
            " VALUES (gen_random_uuid(), :org, 'NonAdmin', 'Target', 'new', '{}', 0)"
            " RETURNING id"
        ),
        {"org": str(test_org.id)},
    ).scalar_one()
    db.commit()
    assert other_client.post(f"/api/leads/{row}/forget").status_code == 403
    assert other_client.get(f"/api/leads/{row}/export").status_code == 403


# ---------- Retention policy (settings + sweep) ----------


def test_gdpr_settings_roundtrip(admin_client: CsrfAwareClient):
    assert admin_client.get("/api/gdpr/settings").json() == {"retention_months": None}

    r = admin_client.patch("/api/gdpr/settings", json={"retention_months": 24})
    assert r.status_code == 200, r.text
    assert r.json() == {"retention_months": 24}
    assert admin_client.get("/api/gdpr/settings").json() == {"retention_months": 24}

    # Null switches it back off.
    r = admin_client.patch("/api/gdpr/settings", json={"retention_months": None})
    assert r.json() == {"retention_months": None}

    # Out-of-range guarded by the schema (0 would anonymize everything).
    assert admin_client.patch("/api/gdpr/settings", json={"retention_months": 0}).status_code == 422
    assert (
        admin_client.patch("/api/gdpr/settings", json={"retention_months": 999}).status_code == 422
    )


def test_gdpr_settings_admin_only(other_client: CsrfAwareClient):
    assert other_client.get("/api/gdpr/settings").status_code == 403
    assert (
        other_client.patch("/api/gdpr/settings", json={"retention_months": 12}).status_code == 403
    )


@pytest.fixture
async def worker_session():
    """Async crm_app sessionmaker on the test loop (RLS + org GUC) —
    same pattern as test_event_types/test_automations."""
    engine = create_async_engine(settings.runtime_database_url, future=True)
    register_org_guc(engine)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield SessionLocal
    finally:
        await engine.dispose()


async def test_retention_sweep_anonymizes_only_stale_leads(
    worker_session, admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    from app.api.gdpr import enforce_org_retention

    stale = _make_lead(admin_client, email="pytest-gdpr-stale@example.com")
    fresh = _make_lead(admin_client, email="pytest-gdpr-fresh@example.com")
    # Age one lead past a 24-month cutoff (~730d > 720d).
    db.execute(
        text("UPDATE leads SET updated_at = now() - interval '800 days' WHERE id = :id"),
        {"id": stale["id"]},
    )
    db.commit()

    set_current_org_id(test_org.id)
    async with worker_session() as wdb:
        n = await enforce_org_retention(wdb, test_org.id, months=24)
    assert n == 1

    anonymized = db.get(Lead, uuid.UUID(stale["id"]), execution_options={"include_deleted": True})
    assert anonymized.first_name == "Anonymized"
    assert anonymized.email is None
    assert anonymized.deleted_at is not None
    # Audit attributes the erasure to the policy, with no human actor.
    audit = (
        db.execute(
            select(AuditLog).where(
                AuditLog.action == "lead.gdpr_forget", AuditLog.entity_id == stale["id"]
            )
        )
        .scalars()
        .first()
    )
    assert audit is not None and audit.actor_id is None
    assert json.loads(audit.metadata_json) == {"via": "retention"}

    untouched = db.get(Lead, uuid.UUID(fresh["id"]))
    assert untouched.email == "pytest-gdpr-fresh@example.com"
    assert untouched.deleted_at is None

    # Idempotent: the anonymized lead is soft-deleted, so a second
    # sweep finds nothing.
    set_current_org_id(test_org.id)
    async with worker_session() as wdb:
        assert await enforce_org_retention(wdb, test_org.id, months=24) == 0


def test_forget_cross_org_is_404(
    admin_client: CsrfAwareClient, db: Session, other_org: Organization
):
    row = db.execute(
        text(
            "INSERT INTO leads (id, organization_id, first_name, last_name, stage,"
            " custom_fields, version)"
            " VALUES (gen_random_uuid(), :org, 'Foreign', 'Target', 'new', '{}', 0)"
            " RETURNING id"
        ),
        {"org": str(other_org.id)},
    ).scalar_one()
    db.commit()
    assert admin_client.post(f"/api/leads/{row}/forget").status_code == 404
    assert admin_client.get(f"/api/leads/{row}/export").status_code == 404
