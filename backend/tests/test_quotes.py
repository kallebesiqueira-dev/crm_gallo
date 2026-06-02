"""Versioned quotes — totals math, CRUD, state machine, versioning,
RLS/ownership (ADR-016).

Layered like the rest of the suite: pure-Python unit tests on the
totals service (no DB/HTTP), then HTTP tests that exercise the real
endpoints through RLS as a logged-in user.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Organization, Quote, QuoteLineItem, QuoteStatus, User
from app.services.quotes import compute_line_total, recompute_totals
from tests.conftest import CsrfAwareClient

# ---------- Totals service (no DB) ----------


def test_compute_line_total_rounds_to_cents():
    assert compute_line_total(Decimal("3"), Decimal("9.99")) == Decimal("29.97")
    # Decimal is exact — no float noise to round away in the first place.
    assert compute_line_total(Decimal("1"), Decimal("0.1") + Decimal("0.2")) == Decimal("0.30")


def test_recompute_totals_sums_lines_and_applies_tax():
    quote = Quote(tax_rate=Decimal("7.7"))
    quote.line_items = [
        QuoteLineItem(description="A", quantity=Decimal("2"), unit_price=Decimal("250.00")),
        QuoteLineItem(description="B", quantity=Decimal("1"), unit_price=Decimal("500.00")),
    ]
    recompute_totals(quote)
    assert quote.line_items[0].line_total == Decimal("500.00")
    assert quote.subtotal == Decimal("1000.00")
    assert quote.tax_amount == Decimal("77.00")
    assert quote.total == Decimal("1077.00")


def test_recompute_totals_zero_tax_and_empty():
    quote = Quote(tax_rate=Decimal("0"))
    quote.line_items = []
    recompute_totals(quote)
    assert quote.subtotal == Decimal("0.00")
    assert quote.tax_amount == Decimal("0.00")
    assert quote.total == Decimal("0.00")


# ---------- helpers ----------

_LINES = [
    {"description": "Design", "quantity": 2, "unit_price": 250.0},
    {"description": "Development", "quantity": 1, "unit_price": 500.0},
]


def _create_quote(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"title": "Website project", "tax_rate": 7.7, "line_items": _LINES}
    payload.update(overrides)
    r = client.post("/api/quotes", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _seed_quote(db: Session, org: Organization, owner: User | None) -> Quote:
    quote = Quote(
        organization_id=org.id,
        number="Q-000001",
        version=1,
        status=QuoteStatus.draft,
        title="Seeded quote",
        tax_rate=0.0,
        owner_id=owner.id if owner else None,
    )
    quote.line_items = [
        QuoteLineItem(organization_id=org.id, description="Item", quantity=1, unit_price=100.0)
    ]
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote


# ---------- CRUD ----------


def test_create_computes_totals_server_side_and_assigns_number(admin_client):
    q = _create_quote(admin_client)
    assert q["number"] == "Q-000001"
    assert q["version"] == 1
    assert q["status"] == "draft"
    # Server recomputed — client never sends these.
    assert q["subtotal"] == 1000.0
    assert q["tax_amount"] == 77.0
    assert q["total"] == 1077.0
    assert len(q["line_items"]) == 2
    assert q["line_items"][0]["line_total"] == 500.0


def test_numbers_increment_per_org(admin_client):
    first = _create_quote(admin_client)
    second = _create_quote(admin_client)
    assert first["number"] == "Q-000001"
    assert second["number"] == "Q-000002"


def test_get_and_list(admin_client):
    q = _create_quote(admin_client)
    got = admin_client.get(f"/api/quotes/{q['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == q["id"]

    listed = admin_client.get("/api/quotes")
    assert listed.status_code == 200
    assert any(item["id"] == q["id"] for item in listed.json()["items"])


def test_update_draft_replaces_line_items_and_recomputes(admin_client):
    q = _create_quote(admin_client)
    r = admin_client.patch(
        f"/api/quotes/{q['id']}",
        json={
            "tax_rate": 10.0,
            "line_items": [{"description": "Flat fee", "quantity": 1, "unit_price": 200.0}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["line_items"]) == 1
    assert body["subtotal"] == 200.0
    assert body["tax_amount"] == 20.0
    assert body["total"] == 220.0


def test_soft_delete_then_404(admin_client):
    q = _create_quote(admin_client)
    assert admin_client.delete(f"/api/quotes/{q['id']}").status_code == 204
    assert admin_client.get(f"/api/quotes/{q['id']}").status_code == 404


# ---------- State machine ----------


def test_send_then_accept(admin_client):
    q = _create_quote(admin_client)
    sent = admin_client.post(f"/api/quotes/{q['id']}/send")
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    assert sent.json()["sent_at"] is not None

    accepted = admin_client.post(f"/api/quotes/{q['id']}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["accepted_at"] is not None


def test_send_then_decline(admin_client):
    q = _create_quote(admin_client)
    admin_client.post(f"/api/quotes/{q['id']}/send").raise_for_status()
    declined = admin_client.post(f"/api/quotes/{q['id']}/decline")
    assert declined.status_code == 200
    assert declined.json()["status"] == "declined"
    assert declined.json()["declined_at"] is not None


def test_cannot_accept_a_draft(admin_client):
    q = _create_quote(admin_client)
    r = admin_client.post(f"/api/quotes/{q['id']}/accept")
    assert r.status_code == 409


def test_cannot_send_twice(admin_client):
    q = _create_quote(admin_client)
    admin_client.post(f"/api/quotes/{q['id']}/send").raise_for_status()
    r = admin_client.post(f"/api/quotes/{q['id']}/send")
    assert r.status_code == 409


def test_cannot_edit_a_sent_quote(admin_client):
    q = _create_quote(admin_client)
    admin_client.post(f"/api/quotes/{q['id']}/send").raise_for_status()
    r = admin_client.patch(f"/api/quotes/{q['id']}", json={"title": "nope"})
    assert r.status_code == 409


def test_cannot_send_quote_without_line_items(admin_client):
    q = _create_quote(admin_client, line_items=[])
    r = admin_client.post(f"/api/quotes/{q['id']}/send")
    assert r.status_code == 422


# ---------- Versioning / supersede ----------


def test_resend_clones_into_new_version_and_supersedes(admin_client):
    q = _create_quote(admin_client)
    admin_client.post(f"/api/quotes/{q['id']}/send").raise_for_status()

    resent = admin_client.post(f"/api/quotes/{q['id']}/resend")
    assert resent.status_code == 201, resent.text
    new = resent.json()
    assert new["number"] == q["number"]  # same human number
    assert new["version"] == 2
    assert new["status"] == "draft"
    assert new["id"] != q["id"]
    # Line items deep-copied.
    assert len(new["line_items"]) == 2
    assert new["total"] == 1077.0

    # Old revision now points forward.
    old = admin_client.get(f"/api/quotes/{q['id']}").json()
    assert old["superseded_by"] == new["id"]
    assert old["status"] == "sent"


def test_cannot_resend_a_draft(admin_client):
    q = _create_quote(admin_client)
    r = admin_client.post(f"/api/quotes/{q['id']}/resend")
    assert r.status_code == 409


# ---------- Ownership + cross-org isolation ----------


def test_non_owner_cannot_mutate(
    other_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    quote = _seed_quote(db, test_org, owner=admin_user)
    r = other_client.patch(f"/api/quotes/{quote.id}", json={"title": "hijack"})
    assert r.status_code == 403


def test_non_owner_can_read(
    other_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    quote = _seed_quote(db, test_org, owner=admin_user)
    r = other_client.get(f"/api/quotes/{quote.id}")
    assert r.status_code == 200


def test_cross_org_returns_404(
    admin_client: CsrfAwareClient,
    db: Session,
    other_org: Organization,
    foreign_user: User,
):
    """A quote in another org must look like it doesn't exist — RLS +
    the API org filter both enforce this."""
    foreign = _seed_quote(db, other_org, owner=foreign_user)
    assert admin_client.get(f"/api/quotes/{foreign.id}").status_code == 404
    assert admin_client.patch(f"/api/quotes/{foreign.id}", json={"title": "x"}).status_code == 404
    assert admin_client.delete(f"/api/quotes/{foreign.id}").status_code == 404


def test_cross_org_random_id_404(admin_client: CsrfAwareClient):
    assert admin_client.get(f"/api/quotes/{uuid.uuid4()}").status_code == 404
