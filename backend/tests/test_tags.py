"""Tags + polymorphic assignments + bulk + saved segments.

HTTP tests drive the real endpoints through RLS as a logged-in user;
cross-org rows are seeded with the owner-role `db` session. Entity
attachment is exercised against leads (the polymorphic join treats every
entity type identically).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Organization, Tag
from tests.conftest import CsrfAwareClient


def _create_tag(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"name": "VIP", "color": "#ff0000"}
    payload.update(overrides)
    r = client.post("/api/tags", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_lead(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"first_name": "A", "last_name": "B"}
    payload.update(overrides)
    r = client.post("/api/leads", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ---------- Tag CRUD ----------


def test_create_tag(admin_client):
    t = _create_tag(admin_client)
    assert t["name"] == "VIP"
    assert t["color"] == "#ff0000"


def test_create_tag_default_color(admin_client):
    r = admin_client.post("/api/tags", json={"name": "Plain"})
    assert r.status_code == 201
    assert r.json()["color"] == "#64748b"


def test_list_tags_sorted(admin_client):
    _create_tag(admin_client, name="Zeta")
    _create_tag(admin_client, name="Alpha")
    names = [t["name"] for t in admin_client.get("/api/tags").json()]
    assert names == sorted(names)


def test_duplicate_name_case_insensitive_409(admin_client):
    _create_tag(admin_client, name="Gold")
    r = admin_client.post("/api/tags", json={"name": "gold"})
    assert r.status_code == 409


def test_invalid_color_rejected(admin_client):
    r = admin_client.post("/api/tags", json={"name": "Bad", "color": "red"})
    assert r.status_code == 422


def test_member_can_create_and_list(other_client):
    # Creating + listing are daily-driver actions open to any member.
    assert other_client.post("/api/tags", json={"name": "Mine"}).status_code == 201
    assert other_client.get("/api/tags").status_code == 200


def test_non_admin_cannot_update_or_delete(other_client):
    t = _create_tag(other_client, name="Locked")
    assert other_client.patch(
        f"/api/tags/{t['id']}", json={"name": "x"}
    ).status_code == 403
    assert other_client.delete(f"/api/tags/{t['id']}").status_code == 403


def test_update_tag(admin_client):
    t = _create_tag(admin_client)
    r = admin_client.patch(
        f"/api/tags/{t['id']}", json={"name": "Renamed", "color": "#00ff00"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert r.json()["color"] == "#00ff00"


def test_update_to_existing_name_409(admin_client):
    _create_tag(admin_client, name="One")
    t2 = _create_tag(admin_client, name="Two")
    r = admin_client.patch(f"/api/tags/{t2['id']}", json={"name": "one"})
    assert r.status_code == 409


def test_soft_delete_then_name_reusable(admin_client):
    t = _create_tag(admin_client, name="Recyclable")
    assert admin_client.delete(f"/api/tags/{t['id']}").status_code == 204
    names = [x["name"] for x in admin_client.get("/api/tags").json()]
    assert "Recyclable" not in names
    # Partial unique index lets the name be recreated.
    assert admin_client.post(
        "/api/tags", json={"name": "Recyclable"}
    ).status_code == 201


def test_delete_removes_assignments(admin_client):
    t = _create_tag(admin_client)
    lead = _create_lead(admin_client)
    admin_client.post(
        "/api/tags/assign",
        json={"tag_id": t["id"], "entity_type": "lead", "entity_id": lead["id"]},
    )
    assert admin_client.delete(f"/api/tags/{t['id']}").status_code == 204
    r = admin_client.get(
        "/api/tags/assignments",
        params={"entity_type": "lead", "entity_ids": lead["id"]},
    )
    assert r.json()[0]["tags"] == []


# ---------- Assignment ----------


def test_assign_and_list(admin_client):
    t = _create_tag(admin_client)
    lead = _create_lead(admin_client)
    r = admin_client.post(
        "/api/tags/assign",
        json={"tag_id": t["id"], "entity_type": "lead", "entity_id": lead["id"]},
    )
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()] == [t["id"]]


def test_assign_is_idempotent(admin_client):
    t = _create_tag(admin_client)
    lead = _create_lead(admin_client)
    body = {"tag_id": t["id"], "entity_type": "lead", "entity_id": lead["id"]}
    admin_client.post("/api/tags/assign", json=body)
    r = admin_client.post("/api/tags/assign", json=body)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_assign_unknown_entity_404(admin_client):
    import uuid

    t = _create_tag(admin_client)
    r = admin_client.post(
        "/api/tags/assign",
        json={
            "tag_id": t["id"],
            "entity_type": "lead",
            "entity_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 404


def test_assign_unknown_tag_404(admin_client):
    import uuid

    lead = _create_lead(admin_client)
    r = admin_client.post(
        "/api/tags/assign",
        json={
            "tag_id": str(uuid.uuid4()),
            "entity_type": "lead",
            "entity_id": lead["id"],
        },
    )
    assert r.status_code == 404


def test_unassign(admin_client):
    t = _create_tag(admin_client)
    lead = _create_lead(admin_client)
    body = {"tag_id": t["id"], "entity_type": "lead", "entity_id": lead["id"]}
    admin_client.post("/api/tags/assign", json=body)
    assert admin_client.post("/api/tags/unassign", json=body).status_code == 204
    r = admin_client.get(
        "/api/tags/assignments",
        params={"entity_type": "lead", "entity_ids": lead["id"]},
    )
    assert r.json()[0]["tags"] == []


def test_assignments_unknown_entity_type_422(admin_client):
    r = admin_client.get(
        "/api/tags/assignments",
        params={"entity_type": "bogus", "entity_ids": "x"},
    )
    assert r.status_code == 422


def test_assignments_invalid_uuid_422(admin_client):
    r = admin_client.get(
        "/api/tags/assignments",
        params={"entity_type": "lead", "entity_ids": "not-a-uuid"},
    )
    assert r.status_code == 422


# ---------- Bulk ----------


def test_bulk_add_and_remove(admin_client):
    t1 = _create_tag(admin_client, name="T1")
    t2 = _create_tag(admin_client, name="T2")
    l1 = _create_lead(admin_client)
    l2 = _create_lead(admin_client)
    r = admin_client.post(
        "/api/tags/bulk",
        json={
            "tag_ids": [t1["id"], t2["id"]],
            "entity_type": "lead",
            "entity_ids": [l1["id"], l2["id"]],
            "action": "add",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == 4  # 2 tags x 2 entities
    # Idempotent re-add affects nothing.
    again = admin_client.post(
        "/api/tags/bulk",
        json={
            "tag_ids": [t1["id"], t2["id"]],
            "entity_type": "lead",
            "entity_ids": [l1["id"], l2["id"]],
            "action": "add",
        },
    )
    assert again.json()["affected"] == 0
    # Remove drops them.
    rem = admin_client.post(
        "/api/tags/bulk",
        json={
            "tag_ids": [t1["id"], t2["id"]],
            "entity_type": "lead",
            "entity_ids": [l1["id"], l2["id"]],
            "action": "remove",
        },
    )
    assert rem.json()["affected"] == 4


def test_bulk_ignores_unknown_ids(admin_client):
    import uuid

    t1 = _create_tag(admin_client, name="Real")
    l1 = _create_lead(admin_client)
    r = admin_client.post(
        "/api/tags/bulk",
        json={
            "tag_ids": [t1["id"], str(uuid.uuid4())],
            "entity_type": "lead",
            "entity_ids": [l1["id"], str(uuid.uuid4())],
            "action": "add",
        },
    )
    # Only the real tag x real entity pair is created.
    assert r.json()["affected"] == 1


# ---------- Cross-org isolation ----------


def test_cross_org_tags_not_visible(admin_client, db: Session, other_org: Organization):
    db.add(Tag(organization_id=other_org.id, name="ForeignTag", color="#123456"))
    db.commit()
    names = [t["name"] for t in admin_client.get("/api/tags").json()]
    assert "ForeignTag" not in names


def test_cannot_assign_cross_org_tag(
    admin_client, db: Session, other_org: Organization
):
    foreign = Tag(organization_id=other_org.id, name="Foreign", color="#123456")
    db.add(foreign)
    db.commit()
    db.refresh(foreign)
    lead = _create_lead(admin_client)
    r = admin_client.post(
        "/api/tags/assign",
        json={
            "tag_id": str(foreign.id),
            "entity_type": "lead",
            "entity_id": lead["id"],
        },
    )
    assert r.status_code == 404  # tag not visible in this org


# ---------- Saved segments ----------


def _create_segment(client: CsrfAwareClient, **overrides) -> dict:
    payload = {
        "entity_type": "lead",
        "name": "Hot leads",
        "filters": {"status": "qualified"},
    }
    payload.update(overrides)
    r = client.post("/api/segments", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_segment_records_creator(admin_client, admin_user):
    s = _create_segment(admin_client)
    assert s["entity_type"] == "lead"
    assert s["filters"] == {"status": "qualified"}
    assert s["created_by_id"] == str(admin_user.id)


def test_list_segments_filtered_by_entity_type(admin_client):
    _create_segment(admin_client, name="L", entity_type="lead")
    _create_segment(admin_client, name="D", entity_type="deal")
    r = admin_client.get("/api/segments", params={"entity_type": "deal"})
    names = [s["name"] for s in r.json()]
    assert names == ["D"]


def test_update_segment(admin_client):
    s = _create_segment(admin_client)
    r = admin_client.patch(
        f"/api/segments/{s['id']}",
        json={"name": "Renamed", "filters": {"x": 1}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert r.json()["filters"] == {"x": 1}


def test_member_can_manage_segments(other_client):
    # Segments are personal/team scratch — any member CRUDs them.
    s = _create_segment(other_client, name="Mine")
    assert other_client.patch(
        f"/api/segments/{s['id']}", json={"name": "Updated"}
    ).status_code == 200
    assert other_client.delete(f"/api/segments/{s['id']}").status_code == 204


def test_soft_delete_segment(admin_client):
    s = _create_segment(admin_client)
    assert admin_client.delete(f"/api/segments/{s['id']}").status_code == 204
    names = [x["name"] for x in admin_client.get("/api/segments").json()]
    assert s["name"] not in names


def test_unknown_entity_type_segment_422(admin_client):
    r = admin_client.post(
        "/api/segments", json={"entity_type": "bogus", "name": "x", "filters": {}}
    )
    assert r.status_code == 422


def test_cross_org_segments_not_visible(
    admin_client, db: Session, other_org: Organization
):
    from app.models import SavedSegment

    db.add(
        SavedSegment(
            organization_id=other_org.id,
            entity_type="lead",
            name="ForeignSeg",
            filters={},
        )
    )
    db.commit()
    names = [x["name"] for x in admin_client.get("/api/segments").json()]
    assert "ForeignSeg" not in names
