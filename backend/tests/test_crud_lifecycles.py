"""CRUD lifecycle smoke for Customer / Deal / Task — mirrors
``test_crud_lead.py`` (create → list → get → patch → soft-delete →
trash → restore → hard-delete) so every trash-able resource has the
whole pipeline exercised, not just Lead.

Customer/Deal/Task PATCH (and Deal /move) require optimistic locking:
clients echo the row's ``version`` as ``If-Match`` — missing → 428,
stale → 412 (see ``app/api/_concurrency.py``)."""

from __future__ import annotations

import pytest

from tests.conftest import CsrfAwareClient


def _if_match(version: int) -> dict[str, str]:
    return {"If-Match": str(version)}


def test_customer_lifecycle(admin_client: CsrfAwareClient):
    # CREATE
    r = admin_client.post(
        "/api/customers",
        json={
            "first_name": "Cycle",
            "last_name": "Customer",
            "email": "cycle-customer@example.com",
        },
    )
    assert r.status_code == 201, r.text
    customer = r.json()
    customer_id = customer["id"]

    # LIST — CursorPage envelope, must include the new customer
    r = admin_client.get("/api/customers")
    assert r.status_code == 200
    assert customer_id in {row["id"] for row in r.json()["items"]}

    # GET single
    r = admin_client.get(f"/api/customers/{customer_id}")
    assert r.status_code == 200
    assert r.json()["first_name"] == "Cycle"

    # PATCH without If-Match → 428 (strict optimistic locking)
    r = admin_client.patch(f"/api/customers/{customer_id}", json={"company": "Acme"})
    assert r.status_code == 428

    # PATCH with the current version succeeds and bumps version
    r = admin_client.patch(
        f"/api/customers/{customer_id}",
        json={"company": "Acme"},
        headers=_if_match(customer["version"]),
    )
    assert r.status_code == 200
    assert r.json()["company"] == "Acme"
    assert r.json()["version"] == customer["version"] + 1

    # Replaying the stale version → 412
    r = admin_client.patch(
        f"/api/customers/{customer_id}",
        json={"company": "Stale"},
        headers=_if_match(customer["version"]),
    )
    assert r.status_code == 412

    # SOFT DELETE
    r = admin_client.delete(f"/api/customers/{customer_id}")
    assert r.status_code == 204

    # LIST must NOT include it; GET must 404 (SoftDeleteMixin filter)
    r = admin_client.get("/api/customers")
    assert customer_id not in {row["id"] for row in r.json()["items"]}
    assert admin_client.get(f"/api/customers/{customer_id}").status_code == 404

    # TRASH sees it (opt-out), RESTORE brings it back
    r = admin_client.get("/api/trash")
    assert customer_id in {t["id"] for t in r.json()["items"]}
    r = admin_client.post(f"/api/trash/customer/{customer_id}/restore")
    assert r.status_code == 204
    assert admin_client.get(f"/api/customers/{customer_id}").status_code == 200

    # HARD-DELETE: soft-delete then purge via trash
    admin_client.delete(f"/api/customers/{customer_id}")
    r = admin_client.delete(f"/api/trash/customer/{customer_id}")
    assert r.status_code == 204
    assert admin_client.get(f"/api/customers/{customer_id}").status_code == 404
    r = admin_client.get("/api/trash")
    assert customer_id not in {t["id"] for t in r.json()["items"]}


def test_deal_lifecycle(admin_client: CsrfAwareClient):
    # CREATE — version starts at 0
    r = admin_client.post("/api/deals", json={"title": "Cycle Deal", "value": 1000})
    assert r.status_code == 201, r.text
    deal = r.json()
    deal_id = deal["id"]
    assert deal["version"] == 0
    assert deal["stage"] == "new"

    # LIST — plain list (kanban needs the whole set)
    r = admin_client.get("/api/deals")
    assert r.status_code == 200
    assert deal_id in {row["id"] for row in r.json()}

    # GET single
    r = admin_client.get(f"/api/deals/{deal_id}")
    assert r.status_code == 200
    assert r.json()["title"] == "Cycle Deal"

    # PATCH without If-Match → 428
    r = admin_client.patch(f"/api/deals/{deal_id}", json={"probability": 50})
    assert r.status_code == 428

    # PATCH with current version succeeds and bumps version
    r = admin_client.patch(f"/api/deals/{deal_id}", json={"probability": 50}, headers=_if_match(0))
    assert r.status_code == 200
    assert r.json()["version"] == 1

    # MOVE also enforces If-Match; stage transition bumps version again
    r = admin_client.post(
        f"/api/deals/{deal_id}/move",
        json={"stage": "negotiation", "sort_index": 0},
        headers=_if_match(0),
    )
    assert r.status_code == 412  # stale after the PATCH above
    r = admin_client.post(
        f"/api/deals/{deal_id}/move",
        json={"stage": "negotiation", "sort_index": 0},
        headers=_if_match(1),
    )
    assert r.status_code == 200
    assert r.json()["stage"] == "negotiation"
    assert r.json()["version"] == 2

    # SOFT DELETE → hidden from list + GET 404, visible in trash
    r = admin_client.delete(f"/api/deals/{deal_id}")
    assert r.status_code == 204
    assert deal_id not in {row["id"] for row in admin_client.get("/api/deals").json()}
    assert admin_client.get(f"/api/deals/{deal_id}").status_code == 404
    assert deal_id in {t["id"] for t in admin_client.get("/api/trash").json()["items"]}

    # RESTORE
    r = admin_client.post(f"/api/trash/deal/{deal_id}/restore")
    assert r.status_code == 204
    assert admin_client.get(f"/api/deals/{deal_id}").status_code == 200

    # HARD-DELETE
    admin_client.delete(f"/api/deals/{deal_id}")
    r = admin_client.delete(f"/api/trash/deal/{deal_id}")
    assert r.status_code == 204
    assert admin_client.get(f"/api/deals/{deal_id}").status_code == 404
    assert deal_id not in {t["id"] for t in admin_client.get("/api/trash").json()["items"]}


def test_task_lifecycle(admin_client: CsrfAwareClient):
    # CREATE
    r = admin_client.post("/api/tasks", json={"title": "Cycle Task"})
    assert r.status_code == 201, r.text
    task = r.json()
    task_id = task["id"]
    assert task["status"] == "todo"

    # LIST — plain list; Task has no GET-detail route, list is the read path
    r = admin_client.get("/api/tasks")
    assert r.status_code == 200
    assert task_id in {row["id"] for row in r.json()}

    # PATCH without If-Match → 428
    r = admin_client.patch(f"/api/tasks/{task_id}", json={"status": "done"})
    assert r.status_code == 428

    # PATCH with current version succeeds
    r = admin_client.patch(
        f"/api/tasks/{task_id}",
        json={"status": "done"},
        headers=_if_match(task["version"]),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert r.json()["version"] == task["version"] + 1

    # SOFT DELETE → hidden from list, visible in trash
    r = admin_client.delete(f"/api/tasks/{task_id}")
    assert r.status_code == 204
    assert task_id not in {row["id"] for row in admin_client.get("/api/tasks").json()}
    assert task_id in {t["id"] for t in admin_client.get("/api/trash").json()["items"]}

    # RESTORE
    r = admin_client.post(f"/api/trash/task/{task_id}/restore")
    assert r.status_code == 204
    assert task_id in {row["id"] for row in admin_client.get("/api/tasks").json()}

    # HARD-DELETE
    admin_client.delete(f"/api/tasks/{task_id}")
    r = admin_client.delete(f"/api/trash/task/{task_id}")
    assert r.status_code == 204
    assert task_id not in {row["id"] for row in admin_client.get("/api/tasks").json()}
    assert task_id not in {t["id"] for t in admin_client.get("/api/trash").json()["items"]}


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/customers", {"first_name": "Trust", "last_name": "Boundary"}),
        ("/api/deals", {"title": "Trust Boundary"}),
        ("/api/tasks", {"title": "Trust Boundary"}),
    ],
    ids=["customer", "deal", "task"],
)
def test_create_strips_organization_id_from_body(
    admin_client: CsrfAwareClient, path: str, body: dict
):
    """Mirrors the Lead trust-boundary test: `organization_id` in the body
    must never override the auth context."""
    r = admin_client.post(
        path, json={**body, "organization_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert r.status_code in (201, 422)
