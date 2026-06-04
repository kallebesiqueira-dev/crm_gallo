"""Audit coverage matrix (§219).

Every mutation on a core entity MUST leave a row in the security
ledger. `test_audit.py` proves the principle for `lead.create`/
`lead.update`/`user.login`; this file widens it into a matrix that
drives all four core entities (lead / customer / deal / task) through
the full lifecycle and asserts the corresponding audit action fires
at each step:

    create → update → soft_delete → restore → hard_delete

with the correct actor and organization stamped on each row.

Scope note: this covers the CRUD/trash call sites that the four
entity routers + `app/api/trash.py` emit. The remaining ~60
`record_audit` call sites (Stripe webhooks, e-sign, quote/contract
state machines, worker jobs, settings) live behind their own
fixtures and are exercised by their dedicated suites — folding them
all into one matrix would couple unrelated subsystems.

Audit rows are read via the `db` fixture (admin engine, BYPASSRLS)
to keep the assertion independent of the request-path tenant GUC.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from tests.conftest import CsrfAwareClient

# (entity_type, plural_path, create_body, patch_body)
ENTITIES = [
    (
        "lead",
        "leads",
        {"first_name": "Aud", "last_name": "Matrix", "stage": "new"},
        {"stage": "qualified"},
    ),
    (
        "customer",
        "customers",
        {"first_name": "Aud", "last_name": "Matrix", "email": "audmatrix@example.com"},
        {"company": "Acme"},
    ),
    (
        "deal",
        "deals",
        {"title": "Aud Matrix Deal", "stage": "new"},
        {"stage": "qualified"},
    ),
    (
        "task",
        "tasks",
        {"title": "Aud Matrix Task", "status": "todo"},
        {"status": "done"},
    ),
]


def _audit_actions(db: Session, entity_id: str) -> set[str]:
    """All audit actions recorded against a given entity id."""
    rows = db.execute(select(AuditLog).where(AuditLog.entity_id == entity_id)).scalars().all()
    return {row.action for row in rows}


def _assert_stamped(db: Session, entity_id: str, action: str, admin_user: User) -> None:
    row = db.execute(
        select(AuditLog).where(
            AuditLog.action == action,
            AuditLog.entity_id == entity_id,
        )
    ).scalars().all()
    assert row, f"no audit row for {action}"
    assert row[-1].actor_id == admin_user.id, f"{action}: wrong actor"
    assert row[-1].organization_id == admin_user.last_active_org_id, f"{action}: wrong org"


@pytest.mark.parametrize(
    "entity_type,plural,create_body,patch_body",
    ENTITIES,
    ids=[e[0] for e in ENTITIES],
)
def test_audit_matrix_full_lifecycle(
    entity_type: str,
    plural: str,
    create_body: dict,
    patch_body: dict,
    admin_client: CsrfAwareClient,
    db: Session,
    admin_user: User,
):
    # create
    r = admin_client.post(f"/api/{plural}", json=create_body)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    _assert_stamped(db, eid, f"{entity_type}.create", admin_user)

    # update
    r = admin_client.patch(f"/api/{plural}/{eid}", json=patch_body)
    assert r.status_code == 200, r.text
    _assert_stamped(db, eid, f"{entity_type}.update", admin_user)

    # soft delete
    assert admin_client.delete(f"/api/{plural}/{eid}").status_code == 204
    _assert_stamped(db, eid, f"{entity_type}.soft_delete", admin_user)

    # restore (from trash)
    assert admin_client.post(f"/api/trash/{entity_type}/{eid}/restore").status_code == 204
    _assert_stamped(db, eid, f"{entity_type}.restore", admin_user)

    # soft delete again, then hard delete
    assert admin_client.delete(f"/api/{plural}/{eid}").status_code == 204
    assert admin_client.delete(f"/api/trash/{entity_type}/{eid}").status_code == 204
    _assert_stamped(db, eid, f"{entity_type}.hard_delete", admin_user)

    # the ledger holds the whole story
    actions = _audit_actions(db, eid)
    expected = {
        f"{entity_type}.create",
        f"{entity_type}.update",
        f"{entity_type}.soft_delete",
        f"{entity_type}.restore",
        f"{entity_type}.hard_delete",
    }
    assert expected <= actions, f"missing audit actions: {expected - actions}"
