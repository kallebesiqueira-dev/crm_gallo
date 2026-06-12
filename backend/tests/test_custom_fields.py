"""Custom fields — definition CRUD (admin-gated), select/options invariant,
duplicate-key conflict, cross-org isolation, and value validation/coercion
on the entities that carry a `custom_fields` JSONB bag.

HTTP tests drive the real endpoints through RLS as a logged-in user;
cross-org rows are seeded with the owner-role `db` session.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import CustomFieldDefinition, CustomFieldType, Organization
from tests.conftest import CsrfAwareClient


def _def_payload(**overrides) -> dict:
    payload = {
        "entity_type": "lead",
        "key": "priority_tier",
        "label": "Priority Tier",
        "field_type": "text",
    }
    payload.update(overrides)
    return payload


def _create_def(client: CsrfAwareClient, **overrides) -> dict:
    r = client.post("/api/custom-fields", json=_def_payload(**overrides))
    assert r.status_code == 201, r.text
    return r.json()


# ---------- Definition CRUD ----------


def test_admin_creates_definition(admin_client):
    d = _create_def(admin_client)
    assert d["entity_type"] == "lead"
    assert d["key"] == "priority_tier"
    assert d["field_type"] == "text"
    assert d["required"] is False


def test_list_filtered_by_entity_type(admin_client):
    _create_def(admin_client, key="lead_field", entity_type="lead")
    _create_def(admin_client, key="deal_field", entity_type="deal")
    r = admin_client.get("/api/custom-fields", params={"entity_type": "deal"})
    assert r.status_code == 200
    keys = [d["key"] for d in r.json()]
    assert "deal_field" in keys
    assert "lead_field" not in keys


def test_duplicate_key_per_entity_is_409(admin_client):
    _create_def(admin_client, key="dupe")
    r = admin_client.post("/api/custom-fields", json=_def_payload(key="dupe"))
    assert r.status_code == 409


def test_same_key_different_entity_type_ok(admin_client):
    _create_def(admin_client, key="shared", entity_type="lead")
    r = admin_client.post("/api/custom-fields", json=_def_payload(key="shared", entity_type="deal"))
    assert r.status_code == 201


def test_non_admin_cannot_manage(other_client):
    # other_user is a sales_agent in the same org.
    r = other_client.post("/api/custom-fields", json=_def_payload())
    assert r.status_code == 403


def test_non_admin_can_read(other_client, admin_client):
    # Admin defines; agent reads (needed to render forms).
    admin_client.get("/api/custom-fields")  # warm
    r = other_client.get("/api/custom-fields")
    assert r.status_code == 200


def test_select_requires_options(admin_client):
    r = admin_client.post(
        "/api/custom-fields",
        json=_def_payload(key="tier", field_type="select"),
    )
    assert r.status_code == 422


def test_select_with_options_ok_and_strips_for_text(admin_client):
    d = _create_def(admin_client, key="tier", field_type="select", options=["gold", "silver"])
    assert d["options"] == ["gold", "silver"]
    # A text field must not retain options even if sent.
    d2 = _create_def(admin_client, key="memo", field_type="text", options=["x"])
    assert d2["options"] is None


def test_update_definition(admin_client):
    d = _create_def(admin_client)
    r = admin_client.patch(
        f"/api/custom-fields/{d['id']}", json={"label": "Renamed", "required": True}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "Renamed"
    assert body["required"] is True


def test_soft_delete_then_key_reusable(admin_client):
    d = _create_def(admin_client, key="recyclable")
    assert admin_client.delete(f"/api/custom-fields/{d['id']}").status_code == 204
    # Gone from the listing.
    keys = [x["key"] for x in admin_client.get("/api/custom-fields").json()]
    assert "recyclable" not in keys
    # Partial unique index lets the key be recreated.
    assert (
        admin_client.post("/api/custom-fields", json=_def_payload(key="recyclable")).status_code
        == 201
    )


def test_cross_org_definitions_not_visible(admin_client, db: Session, other_org: Organization):
    db.add(
        CustomFieldDefinition(
            organization_id=other_org.id,
            entity_type="lead",
            key="foreign_only",
            label="Foreign",
            field_type=CustomFieldType.text,
        )
    )
    db.commit()
    keys = [x["key"] for x in admin_client.get("/api/custom-fields").json()]
    assert "foreign_only" not in keys


# ---------- Value validation on entities ----------


def test_unknown_custom_field_key_rejected(admin_client):
    r = admin_client.post(
        "/api/leads",
        json={"first_name": "A", "last_name": "B", "custom_fields": {"nope": "x"}},
    )
    assert r.status_code == 422


def test_required_field_enforced_on_create(admin_client):
    _create_def(admin_client, key="must_have", required=True)
    r = admin_client.post("/api/leads", json={"first_name": "A", "last_name": "B"})
    assert r.status_code == 422


def test_valid_value_persists_and_returns(admin_client):
    _create_def(admin_client, key="priority_tier")
    r = admin_client.post(
        "/api/leads",
        json={
            "first_name": "A",
            "last_name": "B",
            "custom_fields": {"priority_tier": "high"},
        },
    )
    assert r.status_code == 201, r.text
    lead = r.json()
    assert lead["custom_fields"]["priority_tier"] == "high"
    # Round-trips through GET.
    got = admin_client.get(f"/api/leads/{lead['id']}")
    assert got.json()["custom_fields"]["priority_tier"] == "high"


def test_number_type_mismatch_rejected(admin_client):
    _create_def(admin_client, key="score", field_type="number")
    r = admin_client.post(
        "/api/leads",
        json={
            "first_name": "A",
            "last_name": "B",
            "custom_fields": {"score": "not-a-number"},
        },
    )
    assert r.status_code == 422


def test_select_value_must_be_in_options(admin_client):
    _create_def(admin_client, key="tier", field_type="select", options=["gold", "silver"])
    bad = admin_client.post(
        "/api/leads",
        json={"first_name": "A", "last_name": "B", "custom_fields": {"tier": "bronze"}},
    )
    assert bad.status_code == 422
    ok = admin_client.post(
        "/api/leads",
        json={"first_name": "A", "last_name": "B", "custom_fields": {"tier": "gold"}},
    )
    assert ok.status_code == 201


def test_multiselect_validates_each_choice(admin_client):
    _create_def(
        admin_client,
        key="tags",
        field_type="multiselect",
        options=["a", "b", "c"],
    )
    bad = admin_client.post(
        "/api/leads",
        json={"first_name": "A", "last_name": "B", "custom_fields": {"tags": ["a", "z"]}},
    )
    assert bad.status_code == 422
    ok = admin_client.post(
        "/api/leads",
        json={"first_name": "A", "last_name": "B", "custom_fields": {"tags": ["a", "b"]}},
    )
    assert ok.status_code == 201
    assert ok.json()["custom_fields"]["tags"] == ["a", "b"]


def test_update_merges_custom_fields(admin_client):
    _create_def(admin_client, key="f1")
    _create_def(admin_client, key="f2")
    lead = admin_client.post(
        "/api/leads",
        json={
            "first_name": "A",
            "last_name": "B",
            "custom_fields": {"f1": "one", "f2": "two"},
        },
    ).json()
    # Patch only f1 — f2 must survive (merge, not replace).
    r = admin_client.patch(
        f"/api/leads/{lead['id']}",
        json={"custom_fields": {"f1": "changed"}},
        headers={"If-Match": str(lead["version"])},
    )
    assert r.status_code == 200, r.text
    cf = r.json()["custom_fields"]
    assert cf == {"f1": "changed", "f2": "two"}


def test_update_clears_value_with_empty_string(admin_client):
    _create_def(admin_client, key="f1")
    lead = admin_client.post(
        "/api/leads",
        json={"first_name": "A", "last_name": "B", "custom_fields": {"f1": "one"}},
    ).json()
    r = admin_client.patch(
        f"/api/leads/{lead['id']}",
        json={"custom_fields": {"f1": ""}},
        headers={"If-Match": str(lead["version"])},
    )
    assert r.status_code == 200
    assert "f1" not in r.json()["custom_fields"]
