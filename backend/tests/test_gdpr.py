"""GDPR forget/export endpoints (plan.md §5, right to erasure +
portability). Admin-only; PII anonymized in place keeping the id as
the audit anchor; notes hard-deleted; timeline content stripped."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Activity, AuditLog, Lead, Note, Organization
from tests.conftest import CsrfAwareClient


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

    # Audit row, with NO PII in metadata.
    audit = (
        db.execute(
            select(AuditLog).where(
                AuditLog.action == "lead.gdpr_forget", AuditLog.entity_id == lead_id
            )
        )
        .scalars()
        .first()
    )
    assert audit is not None and audit.metadata_json is None


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
