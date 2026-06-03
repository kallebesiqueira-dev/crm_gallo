"""Merge-field document templates — catalog, render engine, CRUD,
apply-to-contract, role gate, RLS (ADR-016).

The render engine (`app.documents.merge`) is pure and unit-tested
directly; the context builder + `{{ line_items }}` roll-up are exercised
end-to-end through the apply endpoints (they need DB + RLS).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.documents.merge import (
    CATALOG_TOKENS,
    FIELD_CATALOG,
    _format_line_items,
    render_merge,
)
from app.models import DocumentTemplate, Organization, QuoteLineItem, User
from tests.conftest import CsrfAwareClient

# ---------- helpers ----------


def _create_template(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"name": "Standard", "body": "Hello {{ customer.name }}"}
    payload.update(overrides)
    r = client.post("/api/document-templates", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_contract(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"title": "Service agreement", "value": 12000.0, "currency": "EUR"}
    payload.update(overrides)
    r = client.post("/api/contracts", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _accepted_quote_with_lines(client: CsrfAwareClient) -> dict:
    qr = client.post(
        "/api/quotes",
        json={
            "title": "Onboarding",
            "tax_rate": 0.0,
            "line_items": [
                {"description": "Setup", "quantity": 2, "unit_price": 1000.0},
                {"description": "Training", "quantity": 1, "unit_price": 500.0},
            ],
        },
    )
    assert qr.status_code == 201, qr.text
    quote = qr.json()
    client.post(f"/api/quotes/{quote['id']}/send").raise_for_status()
    client.post(f"/api/quotes/{quote['id']}/accept").raise_for_status()
    return quote


# ---------- render engine (pure) ----------


def test_render_substitutes_known_tokens():
    out = render_merge(
        "Dear {{ customer.name }}, total {{ contract.value }}.",
        {"customer.name": "Jane Doe", "contract.value": "EUR 100.00"},
    )
    assert out == "Dear Jane Doe, total EUR 100.00."


def test_render_unknown_token_passthrough():
    # A typo must stay visible, not silently vanish.
    out = render_merge("Hi {{ nope }} and {{ customer.name }}", {"customer.name": "Sam"})
    assert out == "Hi {{ nope }} and Sam"


def test_render_whitespace_tolerant():
    assert render_merge("{{customer.name}}", {"customer.name": "X"}) == "X"
    assert render_merge("{{   customer.name   }}", {"customer.name": "X"}) == "X"


def test_render_no_eval():
    # The body is operator text, not code — anything not a bare allow-list
    # token is left verbatim. (No expression evaluation / SSTI surface.)
    body = "{{ 7*7 }} {{ __import__('os') }}"
    assert render_merge(body, {"customer.name": "X"}) == body


def test_format_line_items_block():
    items = [
        QuoteLineItem(
            description="Setup",
            quantity=Decimal("2"),
            unit_price=Decimal("1000.00"),
            line_total=Decimal("2000.00"),
        ),
        QuoteLineItem(
            description="Training",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
            line_total=Decimal("500.00"),
        ),
    ]
    block = _format_line_items(items, "EUR")
    assert block == (
        "- Setup — 2 × EUR 1000.00 = EUR 2000.00\n"
        "- Training — 1 × EUR 500.00 = EUR 500.00"
    )


def test_format_line_items_empty():
    assert _format_line_items([], "EUR") == "—"


def test_catalog_tokens_match():
    assert CATALOG_TOKENS == frozenset(f.token for f in FIELD_CATALOG)
    assert "line_items" in CATALOG_TOKENS


# ---------- fields endpoint ----------


def test_fields_endpoint_returns_catalog(admin_client):
    r = admin_client.get("/api/document-templates/fields")
    assert r.status_code == 200, r.text
    tokens = {f["token"] for f in r.json()}
    assert tokens == CATALOG_TOKENS
    # Every entry carries the picker metadata.
    for f in r.json():
        assert f["label"] and f["description"] and "example" in f


# ---------- CRUD ----------


def test_create_list_get(admin_client):
    tpl = _create_template(admin_client, name="Welcome")
    assert tpl["doc_type"] == "contract"
    assert tpl["is_default"] is False

    listed = admin_client.get("/api/document-templates")
    assert listed.status_code == 200
    assert any(t["id"] == tpl["id"] for t in listed.json())

    got = admin_client.get(f"/api/document-templates/{tpl['id']}")
    assert got.status_code == 200
    assert got.json()["name"] == "Welcome"


def test_update_template(admin_client):
    tpl = _create_template(admin_client)
    r = admin_client.patch(
        f"/api/document-templates/{tpl['id']}",
        json={"name": "Renamed", "body": "New body"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert r.json()["body"] == "New body"


def test_soft_delete_then_404(admin_client):
    tpl = _create_template(admin_client)
    assert admin_client.delete(f"/api/document-templates/{tpl['id']}").status_code == 204
    assert admin_client.get(f"/api/document-templates/{tpl['id']}").status_code == 404


def test_default_toggle_demotes_previous(admin_client):
    first = _create_template(admin_client, name="First", is_default=True)
    assert first["is_default"] is True
    second = _create_template(admin_client, name="Second", is_default=True)
    assert second["is_default"] is True
    # The first must have been demoted.
    refreshed = admin_client.get(f"/api/document-templates/{first['id']}").json()
    assert refreshed["is_default"] is False


# ---------- role gate ----------


def test_sales_agent_cannot_create(other_client):
    # other_client is a sales_agent — reads are fine, writes are gated.
    r = other_client.post("/api/document-templates", json={"name": "X", "body": ""})
    assert r.status_code == 403
    assert other_client.get("/api/document-templates").status_code == 200


# ---------- apply to contract ----------


def test_apply_template_renders_body(admin_client):
    tpl = _create_template(
        admin_client,
        name="Agreement",
        body="Agreement with {{ organization.name }} dated {{ today }}.",
    )
    contract = _create_contract(admin_client)
    r = admin_client.post(
        f"/api/contracts/{contract['id']}/apply-template/{tpl['id']}"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Agreement with" in body["body"]
    assert "{{" not in body["body"]  # tokens resolved
    assert body["applied_template_id"] == tpl["id"]


def test_apply_template_rejects_non_draft(admin_client):
    tpl = _create_template(admin_client)
    contract = _create_contract(admin_client)
    admin_client.post(f"/api/contracts/{contract['id']}/send").raise_for_status()
    r = admin_client.post(
        f"/api/contracts/{contract['id']}/apply-template/{tpl['id']}"
    )
    assert r.status_code == 409


def test_apply_missing_template_404(admin_client):
    contract = _create_contract(admin_client)
    r = admin_client.post(
        f"/api/contracts/{contract['id']}/apply-template/{uuid.uuid4()}"
    )
    assert r.status_code == 404


def test_from_quote_with_template_rolls_up_line_items(admin_client):
    quote = _accepted_quote_with_lines(admin_client)
    tpl = _create_template(
        admin_client,
        name="With lines",
        body="Lines:\n{{ line_items }}",
    )
    r = admin_client.post(
        f"/api/contracts/from-quote/{quote['id']}?template_id={tpl['id']}"
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["applied_template_id"] == tpl["id"]
    assert "- Setup — 2 × EUR 1000.00 = EUR 2000.00" in c["body"]
    assert "- Training — 1 × EUR 500.00 = EUR 500.00" in c["body"]


# ---------- RLS / cross-org ----------


def test_cross_org_returns_404(
    admin_client: CsrfAwareClient,
    db: Session,
    other_org: Organization,
    foreign_user: User,
):
    foreign = DocumentTemplate(
        organization_id=other_org.id,
        name="Foreign template",
        body="secret",
        created_by_user_id=foreign_user.id,
    )
    db.add(foreign)
    db.commit()
    db.refresh(foreign)

    assert admin_client.get(f"/api/document-templates/{foreign.id}").status_code == 404
    assert (
        admin_client.patch(
            f"/api/document-templates/{foreign.id}", json={"name": "x"}
        ).status_code
        == 404
    )
    assert admin_client.delete(f"/api/document-templates/{foreign.id}").status_code == 404
    # And it never leaks into the list.
    listed = admin_client.get("/api/document-templates").json()
    assert all(t["id"] != str(foreign.id) for t in listed)
