"""Duplicate detection + merge.

Detection groups live rows colliding on a normalised email / phone / name.
Merge re-parents children (typed FKs + polymorphic Note/Activity/Attachment
+ tags with dedupe) onto the survivor and soft-deletes the losers. HTTP
drives the endpoints under RLS; awkward polymorphic children + cross-org
rows are seeded with the owner-role `db` session.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, Note, Organization
from tests.conftest import CsrfAwareClient


def _lead(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"first_name": "A", "last_name": "B"}
    payload.update(overrides)
    r = client.post("/api/leads", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _customer(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"first_name": "C", "last_name": "D"}
    payload.update(overrides)
    r = client.post("/api/customers", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _company(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"name": "Acme"}
    payload.update(overrides)
    r = client.post("/api/companies", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _merge(client: CsrfAwareClient, entity_type: str, survivor: str, losers: list[str]):
    return client.post(
        "/api/duplicates/merge",
        json={"entity_type": entity_type, "survivor_id": survivor, "loser_ids": losers},
    )


def _get_task(client: CsrfAwareClient, task_id: str) -> dict:
    # Tasks expose no single-resource GET — read the list and pick the row.
    tasks = client.get("/api/tasks").json()
    return next(t for t in tasks if t["id"] == task_id)


# ---------- Detection ----------


# Leads/customers carry a live partial-unique index on (org, lower(email)),
# so two live rows can never share an email — email-collision detection is
# only reachable on companies, which have no such constraint.
def test_detect_by_email(admin_client):
    _company(admin_client, email="dup@example.com", name="One")
    _company(admin_client, email="DUP@example.com", name="Two")  # case-insensitive
    r = admin_client.get("/api/duplicates", params={"entity_type": "company"})
    assert r.status_code == 200, r.text
    groups = r.json()["groups"]
    email_groups = [g for g in groups if g["match_type"] == "email"]
    assert len(email_groups) == 1
    assert email_groups[0]["key"] == "dup@example.com"
    assert len(email_groups[0]["records"]) == 2


def test_detect_by_phone(admin_client):
    _lead(admin_client, phone="+1 (555) 123-4567", email="a@example.com")
    _lead(admin_client, phone="15551234567", email="b@example.com")  # same digits
    groups = admin_client.get("/api/duplicates", params={"entity_type": "lead"}).json()["groups"]
    phone_groups = [g for g in groups if g["match_type"] == "phone"]
    assert len(phone_groups) == 1
    assert phone_groups[0]["key"] == "15551234567"


def test_detect_by_name(admin_client):
    _lead(admin_client, first_name="John", last_name="Doe")
    _lead(admin_client, first_name="john", last_name="DOE")
    groups = admin_client.get("/api/duplicates", params={"entity_type": "lead"}).json()["groups"]
    name_groups = [g for g in groups if g["match_type"] == "name"]
    assert any(g["key"] == "john doe" and len(g["records"]) == 2 for g in name_groups)


def test_no_duplicates(admin_client):
    _lead(admin_client, first_name="Solo", last_name="Unique", email="solo@example.com")
    groups = admin_client.get("/api/duplicates", params={"entity_type": "lead"}).json()["groups"]
    assert groups == []


def test_unknown_entity_type_422(admin_client):
    assert admin_client.get("/api/duplicates", params={"entity_type": "deal"}).status_code == 422


# ---------- Merge: typed FK re-parenting ----------


def test_merge_lead_reparents_task(admin_client):
    survivor = _lead(admin_client, first_name="Keep", email="k@example.com")
    loser = _lead(admin_client, first_name="Drop", email="d@example.com")
    task = admin_client.post("/api/tasks", json={"title": "Call", "lead_id": loser["id"]}).json()

    r = _merge(admin_client, "lead", survivor["id"], [loser["id"]])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["merged_count"] == 1
    assert body["reparented"].get("tasks") == 1

    assert _get_task(admin_client, task["id"])["lead_id"] == survivor["id"]


def test_merge_customer_reparents_deal_and_task(admin_client):
    survivor = _customer(admin_client, first_name="Keep")
    loser = _customer(admin_client, first_name="Drop")
    deal = admin_client.post("/api/deals", json={"title": "Big", "customer_id": loser["id"]}).json()
    task = admin_client.post(
        "/api/tasks", json={"title": "Email", "customer_id": loser["id"]}
    ).json()

    r = _merge(admin_client, "customer", survivor["id"], [loser["id"]])
    assert r.status_code == 200, r.text
    assert r.json()["reparented"].get("deals") == 1
    assert r.json()["reparented"].get("tasks") == 1

    assert admin_client.get(f"/api/deals/{deal['id']}").json()["customer_id"] == survivor["id"]
    assert _get_task(admin_client, task["id"])["customer_id"] == survivor["id"]


def test_merge_company_reparents_contacts(admin_client):
    survivor = _company(admin_client, name="Keep Inc")
    loser = _company(admin_client, name="Drop Inc")
    lead = _lead(admin_client, first_name="L", company_id=loser["id"], email="cl@example.com")
    cust = _customer(admin_client, first_name="C", company_id=loser["id"])
    deal = admin_client.post("/api/deals", json={"title": "D", "company_id": loser["id"]}).json()

    r = _merge(admin_client, "company", survivor["id"], [loser["id"]])
    assert r.status_code == 200, r.text
    rep = r.json()["reparented"]
    assert rep.get("leads") == 1 and rep.get("customers") == 1 and rep.get("deals") == 1

    assert admin_client.get(f"/api/leads/{lead['id']}").json()["company_id"] == survivor["id"]
    assert admin_client.get(f"/api/customers/{cust['id']}").json()["company_id"] == survivor["id"]
    assert admin_client.get(f"/api/deals/{deal['id']}").json()["company_id"] == survivor["id"]


# ---------- Merge: polymorphic + tags ----------


def test_merge_reparents_notes(admin_client, db: Session, admin_user):
    survivor = _lead(admin_client, first_name="Keep", email="k2@example.com")
    loser = _lead(admin_client, first_name="Drop", email="d2@example.com")
    org_id = admin_user.last_active_org_id
    note = Note(
        organization_id=org_id,
        author_user_id=admin_user.id,
        entity_type="lead",
        entity_id=uuid.UUID(loser["id"]),
        body="seen at trade show",
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    r = _merge(admin_client, "lead", survivor["id"], [loser["id"]])
    assert r.status_code == 200, r.text
    assert r.json()["reparented"].get("notes") == 1

    db.expire_all()
    moved = db.execute(select(Note).where(Note.id == note.id)).scalar_one()
    assert str(moved.entity_id) == survivor["id"]


def test_merge_dedupes_shared_tag(admin_client):
    survivor = _lead(admin_client, first_name="Keep", email="k3@example.com")
    loser = _lead(admin_client, first_name="Drop", email="d3@example.com")
    shared = admin_client.post("/api/tags", json={"name": "VIP"}).json()
    only_loser = admin_client.post("/api/tags", json={"name": "Cold"}).json()
    for lead_id in (survivor["id"], loser["id"]):
        admin_client.post(
            "/api/tags/assign",
            json={"tag_id": shared["id"], "entity_type": "lead", "entity_id": lead_id},
        )
    admin_client.post(
        "/api/tags/assign",
        json={"tag_id": only_loser["id"], "entity_type": "lead", "entity_id": loser["id"]},
    )

    r = _merge(admin_client, "lead", survivor["id"], [loser["id"]])
    assert r.status_code == 200, r.text
    # Only the loser-exclusive tag moves; the shared one is dropped as a dup.
    assert r.json()["reparented"].get("entity_tags") == 1

    rows = admin_client.get(
        "/api/tags/assignments",
        params={"entity_type": "lead", "entity_ids": survivor["id"]},
    ).json()
    names = sorted(t["name"] for t in rows[0]["tags"])
    assert names == ["Cold", "VIP"]


# ---------- Merge: lifecycle + validation ----------


def test_merge_soft_deletes_loser(admin_client):
    survivor = _lead(admin_client, first_name="Keep", email="k4@example.com")
    loser = _lead(admin_client, first_name="Drop", email="d4@example.com")
    _merge(admin_client, "lead", survivor["id"], [loser["id"]])

    ids = {row["id"] for row in admin_client.get("/api/leads").json()["items"]}
    assert survivor["id"] in ids
    assert loser["id"] not in ids


def test_merge_rejects_self_only_loser(admin_client):
    survivor = _lead(admin_client, first_name="Solo", email="s@example.com")
    r = _merge(admin_client, "lead", survivor["id"], [survivor["id"]])
    assert r.status_code == 422


def test_merge_unknown_loser_404(admin_client):
    survivor = _lead(admin_client, first_name="Keep", email="k5@example.com")
    r = _merge(admin_client, "lead", survivor["id"], [str(uuid.uuid4())])
    assert r.status_code == 404


def test_merge_unknown_survivor_404(admin_client):
    loser = _lead(admin_client, first_name="Drop", email="d5@example.com")
    r = _merge(admin_client, "lead", str(uuid.uuid4()), [loser["id"]])
    assert r.status_code == 404


def test_non_privileged_cannot_merge(other_client):
    a = _lead(other_client, first_name="A", email="aa@example.com")
    b = _lead(other_client, first_name="B", email="bb@example.com")
    r = _merge(other_client, "lead", a["id"], [b["id"]])
    assert r.status_code == 403


# ---------- Cross-org isolation ----------


def test_cross_org_rows_not_detected(admin_client, db: Session, other_org: Organization):
    # Same name → a dupe group *within* other_org; admin's org must not see it.
    db.add(Lead(organization_id=other_org.id, first_name="X", last_name="Y"))
    db.add(Lead(organization_id=other_org.id, first_name="X", last_name="Y"))
    db.commit()
    groups = admin_client.get("/api/duplicates", params={"entity_type": "lead"}).json()["groups"]
    assert groups == []


def test_cross_org_loser_404(admin_client, db: Session, other_org: Organization):
    survivor = _lead(admin_client, first_name="Keep", email="k6@example.com")
    foreign = Lead(organization_id=other_org.id, first_name="F", last_name="Z")
    db.add(foreign)
    db.commit()
    db.refresh(foreign)
    r = _merge(admin_client, "lead", survivor["id"], [str(foreign.id)])
    assert r.status_code == 404
