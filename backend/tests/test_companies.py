"""Company (B2B account) entity — CRUD, optimistic locking, name
uniqueness, contact/deal rollup, RLS/ownership isolation.

Mirrors the quotes/customers test layout: HTTP tests drive the real
endpoints through RLS as a logged-in user; cross-org rows are seeded
with the owner-role `db` session.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import Company, Customer, Deal, Lead, Organization, User
from tests.conftest import CsrfAwareClient


def _create_company(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"name": "Acme Corp", "industry": "Manufacturing"}
    payload.update(overrides)
    r = client.post("/api/companies", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _seed_company(db: Session, org: Organization, owner: User | None) -> Company:
    company = Company(
        organization_id=org.id,
        name="Seeded Co",
        owner_id=owner.id if owner else None,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


# ---------- CRUD ----------


def test_create_assigns_owner_and_starts_at_version_zero(admin_client, admin_user):
    c = _create_company(admin_client)
    assert c["name"] == "Acme Corp"
    assert c["industry"] == "Manufacturing"
    assert c["owner_id"] == str(admin_user.id)
    assert c["version"] == 0


def test_get_and_list(admin_client):
    c = _create_company(admin_client)
    got = admin_client.get(f"/api/companies/{c['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == c["id"]

    listed = admin_client.get("/api/companies")
    assert listed.status_code == 200
    assert any(item["id"] == c["id"] for item in listed.json()["items"])


def test_search_by_name(admin_client):
    _create_company(admin_client, name="Globex International")
    _create_company(admin_client, name="Initech")
    r = admin_client.get("/api/companies", params={"q": "globex"})
    assert r.status_code == 200
    names = [item["name"] for item in r.json()["items"]]
    assert "Globex International" in names
    assert "Initech" not in names


def test_duplicate_name_per_org_is_409(admin_client):
    _create_company(admin_client, name="Dupe Inc")
    r = admin_client.post("/api/companies", json={"name": "dupe inc"})  # case-insensitive
    assert r.status_code == 409


def test_soft_delete_then_404(admin_client):
    c = _create_company(admin_client)
    assert admin_client.delete(f"/api/companies/{c['id']}").status_code == 204
    assert admin_client.get(f"/api/companies/{c['id']}").status_code == 404


# ---------- Optimistic locking ----------


def test_update_requires_if_match(admin_client):
    c = _create_company(admin_client)
    # No If-Match header → 428.
    r = admin_client.patch(f"/api/companies/{c['id']}", json={"industry": "Tech"})
    assert r.status_code == 428


def test_update_bumps_version(admin_client):
    c = _create_company(admin_client)
    r = admin_client.patch(
        f"/api/companies/{c['id']}",
        json={"industry": "Tech"},
        headers={"If-Match": str(c["version"])},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["industry"] == "Tech"
    assert body["version"] == c["version"] + 1


def test_update_stale_version_is_412(admin_client):
    c = _create_company(admin_client)
    # Bump once so the original version is stale.
    admin_client.patch(
        f"/api/companies/{c['id']}",
        json={"industry": "Tech"},
        headers={"If-Match": str(c["version"])},
    )
    r = admin_client.patch(
        f"/api/companies/{c['id']}",
        json={"industry": "Finance"},
        headers={"If-Match": str(c["version"])},  # stale
    )
    assert r.status_code == 412


# ---------- Rollup ----------


def test_rollup_returns_linked_contacts_and_deals(
    admin_client, db: Session, test_org: Organization, admin_user: User
):
    c = _create_company(admin_client)
    cid = uuid.UUID(c["id"])

    customer = Customer(
        organization_id=test_org.id,
        first_name="Jane",
        last_name="Doe",
        company_id=cid,
        owner_id=admin_user.id,
    )
    lead = Lead(
        organization_id=test_org.id,
        first_name="John",
        last_name="Buyer",
        company_id=cid,
        owner_id=admin_user.id,
    )
    deal = Deal(
        organization_id=test_org.id,
        title="Big deal",
        company_id=cid,
        owner_id=admin_user.id,
    )
    db.add_all([customer, lead, deal])
    db.commit()

    r = admin_client.get(f"/api/companies/{c['id']}/rollup")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["company"]["id"] == c["id"]
    assert [cu["first_name"] for cu in body["customers"]] == ["Jane"]
    assert [lead_["first_name"] for lead_ in body["leads"]] == ["John"]
    assert [d["title"] for d in body["deals"]] == ["Big deal"]


# ---------- Ownership + cross-org isolation ----------


def test_non_owner_cannot_mutate(
    other_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    company = _seed_company(db, test_org, owner=admin_user)
    r = other_client.patch(
        f"/api/companies/{company.id}",
        json={"industry": "hijack"},
        headers={"If-Match": str(company.version)},
    )
    assert r.status_code == 403


def test_non_owner_can_read(
    other_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    company = _seed_company(db, test_org, owner=admin_user)
    assert other_client.get(f"/api/companies/{company.id}").status_code == 200


def test_cross_org_returns_404(
    admin_client: CsrfAwareClient,
    db: Session,
    other_org: Organization,
    foreign_user: User,
):
    foreign = _seed_company(db, other_org, owner=foreign_user)
    assert admin_client.get(f"/api/companies/{foreign.id}").status_code == 404
    assert (
        admin_client.patch(
            f"/api/companies/{foreign.id}",
            json={"industry": "x"},
            headers={"If-Match": "0"},
        ).status_code
        == 404
    )
    assert admin_client.delete(f"/api/companies/{foreign.id}").status_code == 404


def test_cross_org_random_id_404(admin_client: CsrfAwareClient):
    assert admin_client.get(f"/api/companies/{uuid.uuid4()}").status_code == 404
