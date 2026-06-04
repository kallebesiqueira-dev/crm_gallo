"""Per-org email uniqueness surfaces as a friendly 409 (§211 follow-up).

Lead and Customer carry a partial-unique index on
`(organization_id, lower(email)) WHERE deleted_at IS NULL`. A collision
must map to HTTP 409 via `app/api/_errors.py::raise_for_duplicate_email`
— NOT a raw 500 — on BOTH the create (flush) and update (commit) paths.

Also pins the index's two deliberate edges:
  * case-insensitive (`DUP@…` collides with `dup@…`)
  * soft-deleted rows are excluded, so re-using a trashed contact's
    email is allowed.
"""

from __future__ import annotations

import pytest

from tests.conftest import CsrfAwareClient


@pytest.mark.parametrize("plural", ["leads", "customers"])
def test_duplicate_email_on_create_returns_409(plural: str, admin_client: CsrfAwareClient):
    body = {"first_name": "Dup", "last_name": "One", "email": "dupcreate@example.com"}
    assert admin_client.post(f"/api/{plural}", json=body).status_code == 201

    r = admin_client.post(
        f"/api/{plural}",
        json={"first_name": "Dup", "last_name": "Two", "email": "dupcreate@example.com"},
    )
    assert r.status_code == 409, r.text
    assert "already exists" in r.json()["detail"].lower()


@pytest.mark.parametrize("plural", ["leads", "customers"])
def test_duplicate_email_is_case_insensitive(plural: str, admin_client: CsrfAwareClient):
    assert (
        admin_client.post(
            f"/api/{plural}",
            json={"first_name": "Case", "last_name": "Lower", "email": "case@example.com"},
        ).status_code
        == 201
    )
    r = admin_client.post(
        f"/api/{plural}",
        json={"first_name": "Case", "last_name": "Upper", "email": "CASE@EXAMPLE.COM"},
    )
    assert r.status_code == 409, r.text


@pytest.mark.parametrize("plural", ["leads", "customers"])
def test_duplicate_email_on_update_returns_409(plural: str, admin_client: CsrfAwareClient):
    admin_client.post(
        f"/api/{plural}",
        json={"first_name": "Held", "last_name": "Email", "email": "held@example.com"},
    )
    r = admin_client.post(
        f"/api/{plural}",
        json={"first_name": "Mover", "last_name": "Email", "email": "mover@example.com"},
    )
    mover = r.json()
    mover_id = mover["id"]

    # PATCH the second row onto the first row's email → collision on commit.
    # customers carry a version → strict mode needs If-Match; leads don't.
    headers = {"If-Match": str(mover["version"])} if "version" in mover else {}
    r = admin_client.patch(
        f"/api/{plural}/{mover_id}", json={"email": "held@example.com"}, headers=headers
    )
    assert r.status_code == 409, r.text
    assert "already exists" in r.json()["detail"].lower()


@pytest.mark.parametrize("plural,entity_type", [("leads", "lead"), ("customers", "customer")])
def test_soft_deleted_email_can_be_reused(
    plural: str, entity_type: str, admin_client: CsrfAwareClient
):
    r = admin_client.post(
        f"/api/{plural}",
        json={"first_name": "Trash", "last_name": "Me", "email": "reuse@example.com"},
    )
    first_id = r.json()["id"]

    # Soft-delete frees the email (index excludes deleted rows).
    assert admin_client.delete(f"/api/{plural}/{first_id}").status_code == 204

    r = admin_client.post(
        f"/api/{plural}",
        json={"first_name": "Fresh", "last_name": "Start", "email": "reuse@example.com"},
    )
    assert r.status_code == 201, r.text
