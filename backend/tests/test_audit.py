"""Audit log is the security ledger — every mutation MUST leave a
row. This test creates a lead and asserts a `lead.create` audit
exists with the right actor + org. The audit_logs SELECT policy
allows scoped+system reads, so the test reads via the admin engine
(BYPASSRLS) for simplicity."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from tests.conftest import CsrfAwareClient


def test_audit_row_on_lead_create(admin_client: CsrfAwareClient, db: Session, admin_user: User):
    r = admin_client.post(
        "/api/leads",
        json={
            "first_name": "Audit",
            "last_name": "Probe",
            "stage": "new",
        },
    )
    assert r.status_code == 201
    lead_id = r.json()["id"]

    # Verify the audit row exists.
    result = db.execute(
        select(AuditLog).where(
            AuditLog.action == "lead.create",
            AuditLog.entity_id == lead_id,
        )
    )
    audit = result.scalar_one_or_none()
    assert audit is not None, "no audit row for lead.create"
    assert audit.actor_id == admin_user.id
    assert audit.organization_id == admin_user.last_active_org_id


def test_audit_row_on_lead_patch(admin_client: CsrfAwareClient, db: Session, admin_user: User):
    r = admin_client.post(
        "/api/leads",
        json={"first_name": "A", "last_name": "B", "stage": "new"},
    )
    lead_id = r.json()["id"]

    r = admin_client.patch(f"/api/leads/{lead_id}", json={"stage": "qualified"})
    assert r.status_code == 200

    result = db.execute(
        select(AuditLog).where(
            AuditLog.action == "lead.update",
            AuditLog.entity_id == lead_id,
        )
    )
    rows = result.scalars().all()
    assert len(rows) >= 1, "expected at least one lead.update audit row"
    assert rows[-1].actor_id == admin_user.id


def test_audit_row_on_login(client: CsrfAwareClient, db: Session, admin_user: User):
    from tests.conftest import TEST_PASSWORD

    r = client.post(
        "/api/auth/login",
        data={"username": admin_user.email, "password": TEST_PASSWORD},
    )
    assert r.status_code == 200

    result = db.execute(
        select(AuditLog).where(
            AuditLog.action == "user.login",
            AuditLog.actor_id == admin_user.id,
        )
    )
    rows = result.scalars().all()
    assert len(rows) >= 1
