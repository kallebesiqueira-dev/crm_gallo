"""Lead → Customer/Company/Deal conversion (plan.md §4).

POST /api/leads/{id}/convert creates the trio atomically, reuses
same-email customers / same-name companies instead of duplicating
them, stamps `lead_converted` on both timelines, and refuses a
second conversion with 409.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Activity, Company, Customer, Deal, Organization, User
from tests.conftest import CsrfAwareClient


def _make_lead(client: CsrfAwareClient, **overrides) -> dict:
    body = {
        "first_name": "Conv",
        "last_name": "Lead",
        "email": "pytest-convert@example.com",
        "phone": "+41790000000",
        "company": "Pytest Convert AG",
        "industry": "software",
        "country": "CH",
        "budget": 2500,
        "stage": "qualified",
        **overrides,
    }
    r = client.post("/api/leads", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_convert_creates_customer_company_deal(
    admin_client: CsrfAwareClient, db: Session, admin_user: User, test_org: Organization
):
    lead = _make_lead(admin_client)

    r = admin_client.post(f"/api/leads/{lead['id']}/convert")
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["customer_existed"] is False
    assert out["company_existed"] is False
    assert out["company_id"] is not None

    customer = db.get(Customer, uuid.UUID(out["customer_id"]))
    assert customer is not None
    assert customer.email == "pytest-convert@example.com"
    assert customer.organization_id == test_org.id
    assert str(customer.company_id) == out["company_id"]

    company = db.get(Company, uuid.UUID(out["company_id"]))
    assert company is not None and company.name == "Pytest Convert AG"

    deal = db.get(Deal, uuid.UUID(out["deal_id"]))
    assert deal is not None
    assert str(deal.customer_id) == out["customer_id"]
    assert str(deal.company_id) == out["company_id"]
    # Deal value defaults to the lead's budget.
    assert float(deal.value) == 2500.0
    assert deal.title == "Pytest Convert AG"

    # lead_converted on BOTH timelines.
    rows = db.execute(
        select(Activity).where(
            Activity.type == "lead_converted",
            Activity.organization_id == test_org.id,
        )
    ).scalars()
    stamped = {(a.entity_type, str(a.entity_id)) for a in rows}
    assert ("lead", lead["id"]) in stamped
    assert ("customer", out["customer_id"]) in stamped

    # Cleanup the org-cascade-exempt outbox row noise is unnecessary —
    # org delete cascades activities/deals/customers/companies.


def test_convert_is_guarded_against_double_click(admin_client: CsrfAwareClient):
    lead = _make_lead(admin_client, email="pytest-convert-twice@example.com")
    assert admin_client.post(f"/api/leads/{lead['id']}/convert").status_code == 201
    r = admin_client.post(f"/api/leads/{lead['id']}/convert")
    assert r.status_code == 409
    assert "already" in r.json()["detail"].lower()


def test_convert_reuses_existing_customer_and_company(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    first = _make_lead(admin_client, email="pytest-convert-reuse@example.com")
    out1 = admin_client.post(f"/api/leads/{first['id']}/convert").json()

    # Soft-delete lead #1 so its email leaves the live-unique index
    # (`uq_leads_org_email_live`) — otherwise creating lead #2 with the
    # same address 409s at POST /api/leads, before conversion is even
    # exercised.
    assert admin_client.delete(f"/api/leads/{first['id']}").status_code == 204

    # Second lead, same email + same company name (different case).
    second = _make_lead(
        admin_client,
        email="PYTEST-CONVERT-REUSE@example.com",
        company="pytest convert ag",
    )
    r = admin_client.post(f"/api/leads/{second['id']}/convert")
    assert r.status_code == 201, r.text
    out2 = r.json()
    assert out2["customer_existed"] is True
    assert out2["company_existed"] is True
    assert out2["customer_id"] == out1["customer_id"]
    assert out2["company_id"] == out1["company_id"]
    # A fresh deal IS created each time — that's the point of converting.
    assert out2["deal_id"] != out1["deal_id"]


def test_convert_without_company_or_email(admin_client: CsrfAwareClient, db: Session):
    lead = _make_lead(admin_client, email=None, company=None, budget=None)
    r = admin_client.post(
        f"/api/leads/{lead['id']}/convert",
        json={"deal_title": "Manual title", "deal_value": 99},
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["company_id"] is None
    deal = db.get(Deal, uuid.UUID(out["deal_id"]))
    assert deal.title == "Manual title"
    assert float(deal.value) == 99.0
    customer = db.get(Customer, uuid.UUID(out["customer_id"]))
    assert customer.email is None


def test_convert_cross_org_is_404(
    admin_client: CsrfAwareClient, db: Session, other_org: Organization, foreign_user: User
):
    # Seed a lead in the OTHER org directly.
    row = db.execute(
        text(
            "INSERT INTO leads (id, organization_id, first_name, last_name, stage,"
            " custom_fields, version)"
            " VALUES (gen_random_uuid(), :org, 'Foreign', 'Lead', 'new', '{}', 0)"
            " RETURNING id"
        ),
        {"org": str(other_org.id)},
    ).scalar_one()
    db.commit()
    r = admin_client.post(f"/api/leads/{row}/convert")
    assert r.status_code == 404


def test_convert_requires_ownership(
    other_client: CsrfAwareClient, db: Session, test_org: Organization, admin_user: User
):
    """A sales agent who doesn't own the lead can't convert it. The lead
    is seeded directly (owned by the admin) because admin_client and
    other_client share one underlying session — only one login can be
    active per test."""
    row = db.execute(
        text(
            "INSERT INTO leads (id, organization_id, owner_id, first_name, last_name,"
            " stage, custom_fields, version)"
            " VALUES (gen_random_uuid(), :org, :owner, 'Owned', 'Lead', 'new', '{}', 0)"
            " RETURNING id"
        ),
        {"org": str(test_org.id), "owner": str(admin_user.id)},
    ).scalar_one()
    db.commit()
    r = other_client.post(f"/api/leads/{row}/convert")
    assert r.status_code == 403
