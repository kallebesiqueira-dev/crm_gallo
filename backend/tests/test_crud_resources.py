"""CRUD lifecycle smoke for Customer / Deal / Task — the same
create → list → get → patch → soft-delete → trash → restore →
hard-delete pipeline that `test_crud_lead.py` exercises for Lead.

Closes the §Tests coverage gap: previously only Lead was driven
end-to-end; Customer/Deal/Task follow the same patterns but were
untested, so a regression in any of their trash/restore wiring
would have slipped through.

Shape notes:
  * Customers paginate — list returns a `{items: [...]}` envelope.
  * Deals + Tasks return a plain `[...]` list.
  * Tasks have NO GET-by-id route, so membership is asserted via the
    list (and trash) instead of a single GET.
"""

from __future__ import annotations

from tests.conftest import CsrfAwareClient


def _ids(list_json) -> set[str]:
    """Pull row ids from either the cursor envelope or a plain list."""
    rows = list_json["items"] if isinstance(list_json, dict) else list_json
    return {row["id"] for row in rows}


def _trash_ids(client: CsrfAwareClient, entity_type: str) -> set[str]:
    items = client.get("/api/trash").json()
    return {t["id"] for t in items if t["entity_type"] == entity_type}


def test_customer_lifecycle(admin_client: CsrfAwareClient):
    r = admin_client.post(
        "/api/customers",
        json={"first_name": "Cycle", "last_name": "Cust", "email": "cyclecust@example.com"},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    assert cid in _ids(admin_client.get("/api/customers").json())

    r = admin_client.get(f"/api/customers/{cid}")
    assert r.status_code == 200
    assert r.json()["first_name"] == "Cycle"

    r = admin_client.patch(f"/api/customers/{cid}", json={"company": "Acme"})
    assert r.status_code == 200
    assert r.json()["company"] == "Acme"

    assert admin_client.delete(f"/api/customers/{cid}").status_code == 204
    assert cid not in _ids(admin_client.get("/api/customers").json())
    assert admin_client.get(f"/api/customers/{cid}").status_code == 404

    assert cid in _trash_ids(admin_client, "customer")
    assert admin_client.post(f"/api/trash/customer/{cid}/restore").status_code == 204
    assert admin_client.get(f"/api/customers/{cid}").status_code == 200

    admin_client.delete(f"/api/customers/{cid}")
    assert admin_client.delete(f"/api/trash/customer/{cid}").status_code == 204
    assert admin_client.get(f"/api/customers/{cid}").status_code == 404
    assert cid not in _trash_ids(admin_client, "customer")


def test_deal_lifecycle(admin_client: CsrfAwareClient):
    r = admin_client.post("/api/deals", json={"title": "Cycle Deal", "stage": "new"})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    assert r.json()["stage"] == "new"

    assert did in _ids(admin_client.get("/api/deals").json())

    r = admin_client.get(f"/api/deals/{did}")
    assert r.status_code == 200

    # PATCH (If-Match omitted — optimistic locking is lenient when absent).
    r = admin_client.patch(f"/api/deals/{did}", json={"stage": "qualified"})
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "qualified"

    assert admin_client.delete(f"/api/deals/{did}").status_code == 204
    assert did not in _ids(admin_client.get("/api/deals").json())
    assert admin_client.get(f"/api/deals/{did}").status_code == 404

    assert did in _trash_ids(admin_client, "deal")
    assert admin_client.post(f"/api/trash/deal/{did}/restore").status_code == 204
    assert admin_client.get(f"/api/deals/{did}").status_code == 200

    admin_client.delete(f"/api/deals/{did}")
    assert admin_client.delete(f"/api/trash/deal/{did}").status_code == 204
    assert admin_client.get(f"/api/deals/{did}").status_code == 404
    assert did not in _trash_ids(admin_client, "deal")


def test_task_lifecycle(admin_client: CsrfAwareClient):
    # Tasks have no GET-by-id route, so we assert membership via list + trash.
    r = admin_client.post("/api/tasks", json={"title": "Cycle Task", "status": "todo"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    assert tid in _ids(admin_client.get("/api/tasks").json())

    r = admin_client.patch(f"/api/tasks/{tid}", json={"status": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    assert admin_client.delete(f"/api/tasks/{tid}").status_code == 204
    assert tid not in _ids(admin_client.get("/api/tasks").json())

    assert tid in _trash_ids(admin_client, "task")
    assert admin_client.post(f"/api/trash/task/{tid}/restore").status_code == 204
    assert tid in _ids(admin_client.get("/api/tasks").json())

    admin_client.delete(f"/api/tasks/{tid}")
    assert admin_client.delete(f"/api/trash/task/{tid}").status_code == 204
    assert tid not in _ids(admin_client.get("/api/tasks").json())
    assert tid not in _trash_ids(admin_client, "task")
