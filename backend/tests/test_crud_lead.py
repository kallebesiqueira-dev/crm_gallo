"""CRUD smoke for the Lead endpoint — create → list → get → patch →
soft-delete → trash → restore → hard-delete. Catches the obvious
regressions in the whole pipeline."""

from __future__ import annotations

from tests.conftest import CsrfAwareClient


def test_lead_lifecycle(admin_client: CsrfAwareClient):
    # CREATE
    r = admin_client.post(
        "/api/leads",
        json={
            "first_name": "Cycle",
            "last_name": "Test",
            "email": "cycle@example.com",
            "stage": "new",
        },
    )
    assert r.status_code == 201, r.text
    lead = r.json()
    lead_id = lead["id"]
    assert lead["stage"] == "new"

    # LIST — must include the new lead
    r = admin_client.get("/api/leads")
    assert r.status_code == 200
    assert lead_id in {row["id"] for row in r.json()["items"]}

    # GET single
    r = admin_client.get(f"/api/leads/{lead_id}")
    assert r.status_code == 200
    assert r.json()["first_name"] == "Cycle"

    # PATCH — stage transition
    r = admin_client.patch(f"/api/leads/{lead_id}", json={"stage": "qualified"})
    assert r.status_code == 200
    assert r.json()["stage"] == "qualified"

    # SOFT DELETE
    r = admin_client.delete(f"/api/leads/{lead_id}")
    assert r.status_code == 204

    # LIST — must NOT include the deleted lead (SoftDeleteMixin global filter)
    r = admin_client.get("/api/leads")
    assert lead_id not in {row["id"] for row in r.json()["items"]}

    # GET single — must 404 now (also filtered)
    r = admin_client.get(f"/api/leads/{lead_id}")
    assert r.status_code == 404

    # TRASH — must include it (opt-out)
    r = admin_client.get("/api/trash")
    assert lead_id in {t["id"] for t in r.json()}

    # RESTORE
    r = admin_client.post(f"/api/trash/lead/{lead_id}/restore")
    assert r.status_code == 204

    # Now reachable again
    r = admin_client.get(f"/api/leads/{lead_id}")
    assert r.status_code == 200

    # HARD-DELETE flow: soft-delete then purge via trash
    admin_client.delete(f"/api/leads/{lead_id}")
    r = admin_client.delete(f"/api/trash/lead/{lead_id}")
    assert r.status_code == 204

    # Gone forever
    r = admin_client.get(f"/api/leads/{lead_id}")
    assert r.status_code == 404
    r = admin_client.get("/api/trash")
    assert lead_id not in {t["id"] for t in r.json()}


def test_lead_create_strips_organization_id_from_body(admin_client: CsrfAwareClient):
    """Even if the client sends `organization_id` in the body, the
    server MUST resolve it from the auth context — accepting it
    from the body would let a logged-in attacker plant rows in
    other orgs."""
    r = admin_client.post(
        "/api/leads",
        json={
            "first_name": "Trust",
            "last_name": "Boundary",
            "organization_id": "00000000-0000-0000-0000-000000000000",
            "stage": "new",
        },
    )
    # If the schema rejects unknown fields, 422 is also acceptable;
    # what we care about is "not accepted into a foreign org".
    assert r.status_code in (201, 422)
    if r.status_code == 201:
        # The created lead must belong to the user's actual org, not
        # the bogus one in the body. The endpoint doesn't return
        # organization_id, so the proof is that LIST sees the new row.
        new_id = r.json()["id"]
        listed = admin_client.get("/api/leads").json()["items"]
        assert new_id in {row["id"] for row in listed}
