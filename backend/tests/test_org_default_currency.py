"""Org default currency (plan.md §6): the org-settings knob and the
omitted-vs-explicit rule on deal/quote creation. Display-only — no FX
conversion anywhere."""

from __future__ import annotations

from tests.conftest import CsrfAwareClient


def test_org_settings_roundtrip_and_role_gate(
    admin_client: CsrfAwareClient,
):
    assert admin_client.get("/api/orgs/current/settings").json() == {"default_currency": "EUR"}

    r = admin_client.patch("/api/orgs/current/settings", json={"default_currency": "CHF"})
    assert r.status_code == 200, r.text
    assert r.json() == {"default_currency": "CHF"}
    assert admin_client.get("/api/orgs/current/settings").json() == {"default_currency": "CHF"}

    # Unknown ISO code → pydantic 422 (enum-validated).
    assert (
        admin_client.patch(
            "/api/orgs/current/settings", json={"default_currency": "BRL"}
        ).status_code
        == 422
    )


def test_org_settings_admin_only(other_client: CsrfAwareClient):
    assert other_client.get("/api/orgs/current/settings").status_code == 403
    assert (
        other_client.patch(
            "/api/orgs/current/settings", json={"default_currency": "CHF"}
        ).status_code
        == 403
    )


def test_deal_inherits_org_default_unless_explicit(admin_client: CsrfAwareClient):
    admin_client.patch("/api/orgs/current/settings", json={"default_currency": "GBP"})

    # Omitted → org default.
    inherited = admin_client.post("/api/deals", json={"title": "Currency probe"}).json()
    assert inherited["currency"] == "GBP"

    # Explicit always wins — even when it equals the schema default the
    # org setting would otherwise override.
    explicit = admin_client.post(
        "/api/deals", json={"title": "Explicit EUR", "currency": "EUR"}
    ).json()
    assert explicit["currency"] == "EUR"


def test_quote_inherits_org_default_unless_explicit(admin_client: CsrfAwareClient):
    admin_client.patch("/api/orgs/current/settings", json={"default_currency": "CHF"})

    inherited = admin_client.post(
        "/api/quotes",
        json={
            "title": "Quote currency probe",
            "line_items": [{"description": "Thing", "quantity": 1, "unit_price": 10}],
        },
    ).json()
    assert inherited["currency"] == "CHF"

    explicit = admin_client.post(
        "/api/quotes",
        json={
            "title": "Explicit USD quote",
            "currency": "USD",
            "line_items": [{"description": "Thing", "quantity": 1, "unit_price": 10}],
        },
    ).json()
    assert explicit["currency"] == "USD"
