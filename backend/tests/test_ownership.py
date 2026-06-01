"""Ownership + cross-org isolation negative tests.

Proves the two invariants that the manual smoke verified during
Phase 2:
  * Non-owner, non-admin user attempting to mutate someone else's
    record gets 403 (permissive ownership: read any, mutate own).
  * Any attempt to touch a record belonging to a DIFFERENT org
    returns 404, never 403 — the latter would leak existence.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import Lead, Organization, User
from tests.conftest import CsrfAwareClient


def _seed_lead(db: Session, org: Organization, owner: User | None) -> Lead:
    lead = Lead(
        organization_id=org.id,
        first_name="Seeded",
        last_name="Lead",
        owner_id=owner.id if owner else None,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def test_non_owner_cannot_mutate(
    other_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
    other_user: User,
):
    """Lead is owned by admin_user. other_user (sales_agent, not
    privileged) tries to PATCH → 403."""
    lead = _seed_lead(db, test_org, owner=admin_user)
    r = other_client.patch(f"/api/leads/{lead.id}", json={"stage": "qualified"})
    assert r.status_code == 403


def test_non_owner_can_read(
    other_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    """Permissive ownership: read is allowed for any user in the org."""
    lead = _seed_lead(db, test_org, owner=admin_user)
    r = other_client.get(f"/api/leads/{lead.id}")
    assert r.status_code == 200
    assert r.json()["id"] == str(lead.id)


def test_admin_can_mutate_anyone(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    other_user: User,
):
    """Admins bypass ownership — required so they can clean up rows
    that the owner no longer cares about."""
    lead = _seed_lead(db, test_org, owner=other_user)
    r = admin_client.patch(f"/api/leads/{lead.id}", json={"stage": "qualified"})
    assert r.status_code == 200


def test_cross_org_returns_404_not_403(
    admin_client: CsrfAwareClient,
    db: Session,
    other_org: Organization,
    foreign_user: User,
):
    """admin_user is in test_org; a lead in other_org must look like
    it doesn't exist — 404, NEVER 403. 403 would reveal that the row
    exists but you can't touch it (existence leak)."""
    foreign_lead = _seed_lead(db, other_org, owner=foreign_user)
    # GET
    r = admin_client.get(f"/api/leads/{foreign_lead.id}")
    assert r.status_code == 404
    # PATCH
    r = admin_client.patch(f"/api/leads/{foreign_lead.id}", json={"stage": "qualified"})
    assert r.status_code == 404
    # DELETE
    r = admin_client.delete(f"/api/leads/{foreign_lead.id}")
    assert r.status_code == 404


def test_cross_org_random_id_404(admin_client: CsrfAwareClient):
    """Sanity: a totally fake UUID also 404s (no panic / 500)."""
    r = admin_client.get(f"/api/leads/{uuid.uuid4()}")
    assert r.status_code == 404
