"""Versioned contracts — CRUD, state machine, versioning, from-quote,
RLS/ownership (ADR-016).

HTTP tests that exercise the real endpoints through RLS as a logged-in
user — mirrors test_quotes.py. A contract has no line items (a single
agreed `value`), so there's no totals-service unit layer here.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    Contract,
    ContractStatus,
    Organization,
    Quote,
    QuoteLineItem,
    QuoteStatus,
    User,
)
from tests.conftest import CsrfAwareClient

# ---------- helpers ----------


def _create_contract(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"title": "Service agreement", "value": 12000.0, "currency": "EUR"}
    payload.update(overrides)
    r = client.post("/api/contracts", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _seed_contract(
    db: Session,
    org: Organization,
    owner: User | None,
    *,
    status: ContractStatus = ContractStatus.draft,
    number: str = "C-000001",
) -> Contract:
    contract = Contract(
        organization_id=org.id,
        number=number,
        version=1,
        status=status,
        title="Seeded contract",
        value=Decimal("1000.00"),
        owner_id=owner.id if owner else None,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return contract


# ---------- CRUD ----------


def test_create_assigns_number_and_defaults(admin_client):
    c = _create_contract(admin_client)
    assert c["number"] == "C-000001"
    assert c["version"] == 1
    assert c["status"] == "draft"
    assert c["value"] == 12000.0
    assert c["currency"] == "EUR"
    assert c["auto_renew"] is False


def test_numbers_increment_per_org(admin_client):
    first = _create_contract(admin_client)
    second = _create_contract(admin_client)
    assert first["number"] == "C-000001"
    assert second["number"] == "C-000002"


def test_get_and_list(admin_client):
    c = _create_contract(admin_client)
    got = admin_client.get(f"/api/contracts/{c['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == c["id"]

    listed = admin_client.get("/api/contracts")
    assert listed.status_code == 200
    assert any(item["id"] == c["id"] for item in listed.json()["items"])


def test_update_draft(admin_client):
    c = _create_contract(admin_client)
    r = admin_client.patch(
        f"/api/contracts/{c['id']}",
        json={"value": 15000.0, "auto_renew": True, "renewal_term_months": 12},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["value"] == 15000.0
    assert body["auto_renew"] is True
    assert body["renewal_term_months"] == 12


def test_soft_delete_then_404(admin_client):
    c = _create_contract(admin_client)
    assert admin_client.delete(f"/api/contracts/{c['id']}").status_code == 204
    assert admin_client.get(f"/api/contracts/{c['id']}").status_code == 404


# ---------- State machine ----------


def test_send_sign_activate(admin_client):
    c = _create_contract(admin_client)
    sent = admin_client.post(f"/api/contracts/{c['id']}/send")
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    assert sent.json()["sent_at"] is not None

    signed = admin_client.post(f"/api/contracts/{c['id']}/sign")
    assert signed.status_code == 200
    assert signed.json()["status"] == "signed"
    assert signed.json()["signed_at"] is not None

    active = admin_client.post(f"/api/contracts/{c['id']}/activate")
    assert active.status_code == 200
    assert active.json()["status"] == "active"
    assert active.json()["activated_at"] is not None


def test_terminate_from_signed(admin_client):
    c = _create_contract(admin_client)
    admin_client.post(f"/api/contracts/{c['id']}/send").raise_for_status()
    admin_client.post(f"/api/contracts/{c['id']}/sign").raise_for_status()
    terminated = admin_client.post(f"/api/contracts/{c['id']}/terminate")
    assert terminated.status_code == 200
    assert terminated.json()["status"] == "terminated"
    assert terminated.json()["terminated_at"] is not None


def test_terminate_from_active(admin_client):
    c = _create_contract(admin_client)
    admin_client.post(f"/api/contracts/{c['id']}/send").raise_for_status()
    admin_client.post(f"/api/contracts/{c['id']}/sign").raise_for_status()
    admin_client.post(f"/api/contracts/{c['id']}/activate").raise_for_status()
    r = admin_client.post(f"/api/contracts/{c['id']}/terminate")
    assert r.status_code == 200
    assert r.json()["status"] == "terminated"


def test_cannot_sign_a_draft(admin_client):
    c = _create_contract(admin_client)
    assert admin_client.post(f"/api/contracts/{c['id']}/sign").status_code == 409


def test_cannot_activate_before_signed(admin_client):
    c = _create_contract(admin_client)
    admin_client.post(f"/api/contracts/{c['id']}/send").raise_for_status()
    assert admin_client.post(f"/api/contracts/{c['id']}/activate").status_code == 409


def test_cannot_send_twice(admin_client):
    c = _create_contract(admin_client)
    admin_client.post(f"/api/contracts/{c['id']}/send").raise_for_status()
    assert admin_client.post(f"/api/contracts/{c['id']}/send").status_code == 409


def test_cannot_terminate_a_draft(admin_client):
    c = _create_contract(admin_client)
    assert admin_client.post(f"/api/contracts/{c['id']}/terminate").status_code == 409


def test_cannot_edit_a_sent_contract(admin_client):
    c = _create_contract(admin_client)
    admin_client.post(f"/api/contracts/{c['id']}/send").raise_for_status()
    assert admin_client.patch(f"/api/contracts/{c['id']}", json={"title": "nope"}).status_code == 409


# ---------- Versioning / supersede ----------


def test_resend_clones_into_new_version_and_supersedes(admin_client):
    c = _create_contract(admin_client, auto_renew=True, renewal_term_months=24)
    admin_client.post(f"/api/contracts/{c['id']}/send").raise_for_status()

    resent = admin_client.post(f"/api/contracts/{c['id']}/resend")
    assert resent.status_code == 201, resent.text
    new = resent.json()
    assert new["number"] == c["number"]
    assert new["version"] == 2
    assert new["status"] == "draft"
    assert new["id"] != c["id"]
    assert new["value"] == 12000.0
    assert new["auto_renew"] is True
    assert new["renewal_term_months"] == 24

    old = admin_client.get(f"/api/contracts/{c['id']}").json()
    assert old["superseded_by"] == new["id"]
    assert old["status"] == "sent"


def test_cannot_resend_a_draft(admin_client):
    c = _create_contract(admin_client)
    assert admin_client.post(f"/api/contracts/{c['id']}/resend").status_code == 409


# ---------- From quote ----------


def test_create_from_accepted_quote(admin_client):
    # Build + accept a quote through the API, then paper it.
    qr = admin_client.post(
        "/api/quotes",
        json={
            "title": "Onboarding package",
            "tax_rate": 0.0,
            "line_items": [{"description": "Setup", "quantity": 1, "unit_price": 5000.0}],
        },
    )
    assert qr.status_code == 201, qr.text
    quote = qr.json()
    admin_client.post(f"/api/quotes/{quote['id']}/send").raise_for_status()
    admin_client.post(f"/api/quotes/{quote['id']}/accept").raise_for_status()

    r = admin_client.post(f"/api/contracts/from-quote/{quote['id']}")
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["status"] == "draft"
    assert c["title"] == "Onboarding package"
    assert c["value"] == 5000.0
    assert c["quote_id"] == quote["id"]


def test_from_quote_requires_accepted(admin_client):
    qr = admin_client.post(
        "/api/quotes",
        json={
            "title": "Draft quote",
            "tax_rate": 0.0,
            "line_items": [{"description": "X", "quantity": 1, "unit_price": 100.0}],
        },
    )
    quote = qr.json()
    # Still a draft — can't paper it.
    assert admin_client.post(f"/api/contracts/from-quote/{quote['id']}").status_code == 409


def test_from_quote_cross_org_404(admin_client: CsrfAwareClient, db: Session, other_org, foreign_user):
    quote = Quote(
        organization_id=other_org.id,
        number="Q-900001",
        version=1,
        status=QuoteStatus.accepted,
        title="Foreign quote",
        tax_rate=0.0,
        owner_id=foreign_user.id,
    )
    quote.line_items = [
        QuoteLineItem(organization_id=other_org.id, description="i", quantity=1, unit_price=10.0)
    ]
    db.add(quote)
    db.commit()
    assert admin_client.post(f"/api/contracts/from-quote/{quote.id}").status_code == 404


# ---------- Ownership + cross-org isolation ----------


def test_non_owner_cannot_mutate(
    other_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    contract = _seed_contract(db, test_org, owner=admin_user)
    r = other_client.patch(f"/api/contracts/{contract.id}", json={"title": "hijack"})
    assert r.status_code == 403


def test_non_owner_can_read(
    other_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    contract = _seed_contract(db, test_org, owner=admin_user)
    assert other_client.get(f"/api/contracts/{contract.id}").status_code == 200


def test_cross_org_returns_404(
    admin_client: CsrfAwareClient,
    db: Session,
    other_org: Organization,
    foreign_user: User,
):
    foreign = _seed_contract(db, other_org, owner=foreign_user)
    assert admin_client.get(f"/api/contracts/{foreign.id}").status_code == 404
    assert (
        admin_client.patch(f"/api/contracts/{foreign.id}", json={"title": "x"}).status_code == 404
    )
    assert admin_client.delete(f"/api/contracts/{foreign.id}").status_code == 404


def test_cross_org_random_id_404(admin_client: CsrfAwareClient):
    assert admin_client.get(f"/api/contracts/{uuid.uuid4()}").status_code == 404
