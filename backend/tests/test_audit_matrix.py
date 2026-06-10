"""Audit coverage matrix (§219).

Every mutation on a core entity MUST leave a row in the security
ledger. `test_audit.py` proves the principle for `lead.create`/
`lead.update`/`user.login`; this file widens it into a matrix that
drives all four core entities (lead / customer / deal / task) through
the full lifecycle and asserts the corresponding audit action fires
at each step:

    create → update → soft_delete → restore → hard_delete

with the correct actor and organization stamped on each row.

A second, shorter matrix covers the non-trash-able resources
(company / product / tag — `/api/trash` only handles the four core
entities, so their lifecycle stops at soft_delete), plus dedicated
cases for notes (polymorphic, hosted on a lead), `trash.empty`, and
the security-relevant surfaces (invite, api-key, team).

Scope note: the remaining `record_audit` call sites (Stripe webhooks,
e-sign, quote/contract state machines, worker jobs, WhatsApp,
imports) live behind their own fixtures and are exercised by their
dedicated suites — folding them all into one matrix would couple
unrelated subsystems.

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
    row = (
        db.execute(
            select(AuditLog).where(
                AuditLog.action == action,
                AuditLog.entity_id == entity_id,
            )
        )
        .scalars()
        .all()
    )
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
    created = r.json()
    eid = created["id"]
    _assert_stamped(db, eid, f"{entity_type}.create", admin_user)

    # update — version-bearing entities (customer/deal/task) require If-Match (strict mode)
    patch_headers = {"If-Match": str(created["version"])} if "version" in created else {}
    r = admin_client.patch(f"/api/{plural}/{eid}", json=patch_body, headers=patch_headers)
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


# (entity_type, plural_path, create_body, patch_body)
# Not trash-able (`/api/trash` only handles lead/customer/deal/task),
# so the audited lifecycle is create → update → soft_delete.
NON_TRASH_ENTITIES = [
    (
        "company",
        "companies",
        {"name": "Aud Matrix Co"},
        {"industry": "software"},
    ),
    (
        "product",
        "products",
        {"name": "Aud Matrix Product"},
        {"description": "updated"},
    ),
    (
        "tag",
        "tags",
        {"name": "aud-matrix-tag"},
        {"color": "#ff0000"},
    ),
]


@pytest.mark.parametrize(
    "entity_type,plural,create_body,patch_body",
    NON_TRASH_ENTITIES,
    ids=[e[0] for e in NON_TRASH_ENTITIES],
)
def test_audit_matrix_non_trash_lifecycle(
    entity_type: str,
    plural: str,
    create_body: dict,
    patch_body: dict,
    admin_client: CsrfAwareClient,
    db: Session,
    admin_user: User,
):
    r = admin_client.post(f"/api/{plural}", json=create_body)
    assert r.status_code == 201, r.text
    created = r.json()
    eid = created["id"]
    _assert_stamped(db, eid, f"{entity_type}.create", admin_user)

    patch_headers = {"If-Match": str(created["version"])} if "version" in created else {}
    r = admin_client.patch(f"/api/{plural}/{eid}", json=patch_body, headers=patch_headers)
    assert r.status_code == 200, r.text
    _assert_stamped(db, eid, f"{entity_type}.update", admin_user)

    assert admin_client.delete(f"/api/{plural}/{eid}").status_code == 204
    _assert_stamped(db, eid, f"{entity_type}.soft_delete", admin_user)


def test_audit_note_lifecycle(admin_client: CsrfAwareClient, db: Session, admin_user: User):
    """Notes are polymorphic (entity_type + entity_id) — hosted on a lead."""
    lead_id = admin_client.post(
        "/api/leads",
        json={"first_name": "Note", "last_name": "Host", "stage": "new"},
    ).json()["id"]

    r = admin_client.post(
        "/api/notes",
        json={"entity_type": "lead", "entity_id": lead_id, "body": "audit probe"},
    )
    assert r.status_code == 201, r.text
    note_id = r.json()["id"]
    _assert_stamped(db, note_id, "note.create", admin_user)

    r = admin_client.patch(f"/api/notes/{note_id}", json={"body": "edited"})
    assert r.status_code == 200, r.text
    _assert_stamped(db, note_id, "note.update", admin_user)

    assert admin_client.delete(f"/api/notes/{note_id}").status_code == 204
    _assert_stamped(db, note_id, "note.soft_delete", admin_user)


def test_audit_trash_empty(admin_client: CsrfAwareClient, db: Session, admin_user: User):
    """`/api/trash/empty` audits one `trash.empty` row (no per-row
    entity_id), stamped with the actor who pulled the trigger."""
    lead_id = admin_client.post(
        "/api/leads",
        json={"first_name": "Empty", "last_name": "Probe", "stage": "new"},
    ).json()["id"]
    admin_client.delete(f"/api/leads/{lead_id}")

    before = len(
        db.execute(
            select(AuditLog).where(
                AuditLog.action == "trash.empty",
                AuditLog.actor_id == admin_user.id,
            )
        )
        .scalars()
        .all()
    )
    assert admin_client.post("/api/trash/empty").status_code == 204
    rows = (
        db.execute(
            select(AuditLog).where(
                AuditLog.action == "trash.empty",
                AuditLog.actor_id == admin_user.id,
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == before + 1, "no audit row for trash.empty"
    assert rows[-1].organization_id == admin_user.last_active_org_id


def test_audit_invite_actions(admin_client: CsrfAwareClient, db: Session, admin_user: User):
    r = admin_client.post(
        "/api/orgs/current/invites",
        json={"email": "pytest-audit-invite@example.com"},
    )
    assert r.status_code == 201, r.text
    invite_id = r.json()["id"]
    _assert_stamped(db, invite_id, "invite.create", admin_user)

    assert admin_client.delete(f"/api/orgs/current/invites/{invite_id}").status_code == 204
    _assert_stamped(db, invite_id, "invite.revoke", admin_user)


def test_audit_api_key_actions(admin_client: CsrfAwareClient, db: Session, admin_user: User):
    r = admin_client.post("/api/api-keys", json={"name": "aud-matrix-key"})
    assert r.status_code == 201, r.text
    key_id = r.json()["id"]
    _assert_stamped(db, key_id, "api_key.create", admin_user)

    # revoke echoes the (now revoked) key back — 200, not 204
    assert admin_client.delete(f"/api/api-keys/{key_id}").status_code == 200
    _assert_stamped(db, key_id, "api_key.revoke", admin_user)


def test_audit_team_actions(admin_client: CsrfAwareClient, db: Session, admin_user: User):
    r = admin_client.post("/api/teams", json={"name": "Aud Matrix Team"})
    assert r.status_code == 201, r.text
    team_id = r.json()["id"]
    _assert_stamped(db, team_id, "team.create", admin_user)

    r = admin_client.patch(f"/api/teams/{team_id}", json={"name": "Aud Matrix Renamed"})
    assert r.status_code == 200, r.text
    _assert_stamped(db, team_id, "team.update", admin_user)

    assert admin_client.delete(f"/api/teams/{team_id}").status_code == 204
    _assert_stamped(db, team_id, "team.delete", admin_user)
