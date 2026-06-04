"""Cross-org isolation guard — the recurring CI version of the
Phase-2 manual smoke (skills.md "Debt" line).

Invariant under test: a user in org A must never be able to observe or
touch a row that belongs to org B. Cross-org access returns **404**
(never 403 — that would leak existence). This must hold on the detail
routes, the list routes, the trash routes, and the audit log, for
every tenant-scoped entity. A regression here is a security incident,
not a bug, so it runs on every build.

`admin_client` is logged in as `admin_user` (org = `test_org`). All
seeded rows below live in `other_org`, reached via the owner-role `db`
session that bypasses RLS for setup.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Customer,
    Deal,
    Lead,
    Organization,
    Task,
    User,
)
from tests.conftest import CsrfAwareClient


# ---------- per-entity seeders ----------


def _seed_lead(db: Session, org: Organization, owner: User) -> Lead:
    row = Lead(organization_id=org.id, first_name="Foreign", last_name="Lead", owner_id=owner.id)
    return _persist(db, row)


def _seed_customer(db: Session, org: Organization, owner: User) -> Customer:
    row = Customer(
        organization_id=org.id, first_name="Foreign", last_name="Customer", owner_id=owner.id
    )
    return _persist(db, row)


def _seed_deal(db: Session, org: Organization, owner: User) -> Deal:
    row = Deal(organization_id=org.id, title="Foreign Deal", owner_id=owner.id)
    return _persist(db, row)


def _seed_task(db: Session, org: Organization, owner: User) -> Task:
    row = Task(organization_id=org.id, title="Foreign Task", assignee_id=owner.id)
    return _persist(db, row)


def _persist(db: Session, row):
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# entity_type -> config. `has_get_detail` is False for tasks: the API
# (and the frontend) only expose PATCH/DELETE on /api/tasks/{id}, no GET.
_ENTITIES = {
    "lead": dict(
        seeder=_seed_lead, list_path="/api/leads", prefix="/api/leads",
        patch={"notes": "x"}, paginated=True, has_get_detail=True,
    ),
    "customer": dict(
        seeder=_seed_customer, list_path="/api/customers", prefix="/api/customers",
        patch={"notes": "x"}, paginated=True, has_get_detail=True,
    ),
    "deal": dict(
        seeder=_seed_deal, list_path="/api/deals", prefix="/api/deals",
        patch={"notes": "x"}, paginated=False, has_get_detail=True,
    ),
    "task": dict(
        seeder=_seed_task, list_path="/api/tasks", prefix="/api/tasks",
        patch={"title": "x"}, paginated=False, has_get_detail=False,
    ),
}


# ---------- detail routes: cross-org access → 404 ----------


@pytest.mark.parametrize("entity_type", list(_ENTITIES))
def test_cross_org_detail_is_404(
    entity_type: str,
    admin_client: CsrfAwareClient,
    db: Session,
    other_org: Organization,
    foreign_user: User,
):
    cfg = _ENTITIES[entity_type]
    row = cfg["seeder"](db, other_org, foreign_user)
    prefix = cfg["prefix"]

    if cfg["has_get_detail"]:
        assert admin_client.get(f"{prefix}/{row.id}").status_code == 404
    assert admin_client.patch(f"{prefix}/{row.id}", json=cfg["patch"]).status_code == 404
    assert admin_client.delete(f"{prefix}/{row.id}").status_code == 404


@pytest.mark.parametrize("entity_type", list(_ENTITIES))
def test_random_id_is_404_not_500(entity_type: str, admin_client: CsrfAwareClient):
    cfg = _ENTITIES[entity_type]
    prefix = cfg["prefix"]
    fake = uuid.uuid4()
    if cfg["has_get_detail"]:
        assert admin_client.get(f"{prefix}/{fake}").status_code == 404
    else:
        # No GET-detail route → probe DELETE, which must 404 (not 500).
        assert admin_client.delete(f"{prefix}/{fake}").status_code == 404


# ---------- list routes: foreign rows never appear ----------


@pytest.mark.parametrize("entity_type", list(_ENTITIES))
def test_cross_org_row_absent_from_list(
    entity_type: str,
    admin_client: CsrfAwareClient,
    db: Session,
    other_org: Organization,
    foreign_user: User,
):
    cfg = _ENTITIES[entity_type]
    row = cfg["seeder"](db, other_org, foreign_user)

    r = admin_client.get(cfg["list_path"])
    assert r.status_code == 200
    payload = r.json()
    items = payload["items"] if cfg["paginated"] else payload
    ids = {item["id"] for item in items}
    assert str(row.id) not in ids


# ---------- trash routes: foreign soft-deleted rows are invisible ----------


@pytest.mark.parametrize("entity_type", list(_ENTITIES))
def test_cross_org_trash_is_404(
    entity_type: str,
    admin_client: CsrfAwareClient,
    db: Session,
    other_org: Organization,
    foreign_user: User,
):
    from datetime import datetime, timezone

    row = _ENTITIES[entity_type]["seeder"](db, other_org, foreign_user)
    row.deleted_at = datetime.now(timezone.utc)
    db.commit()

    # Not listed in the requesting org's trash.
    r = admin_client.get("/api/trash")
    assert r.status_code == 200
    assert str(row.id) not in {item["id"] for item in r.json()}

    # Restore + hard-delete of a foreign row look like it doesn't exist.
    assert (
        admin_client.post(f"/api/trash/{entity_type}/{row.id}/restore").status_code == 404
    )
    assert admin_client.delete(f"/api/trash/{entity_type}/{row.id}").status_code == 404


# ---------- audit log: foreign org's audit rows never surface ----------


def test_cross_org_audit_rows_hidden(
    admin_client: CsrfAwareClient,
    db: Session,
    other_org: Organization,
    foreign_user: User,
):
    foreign_audit = AuditLog(
        organization_id=other_org.id,
        actor_id=foreign_user.id,
        action="lead.create",
        entity_type="lead",
        entity_id=str(uuid.uuid4()),
    )
    _persist(db, foreign_audit)

    r = admin_client.get("/api/audit")
    assert r.status_code == 200
    assert str(foreign_audit.id) not in {entry["id"] for entry in r.json()}
