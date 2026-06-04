"""Optimistic locking on Customer + Task — §321 (TD-12 follow-up).

Mirrors `test_deal_locking.py` for the two entities that adopted the
`version` column in migration `9a8b7c6d5e4f`. The shared guard lives in
`app/api/_concurrency.py::check_if_match`:
  * fresh row starts at version=0
  * PATCH with no If-Match → 428 Precondition Required (strict mode)
  * PATCH with correct If-Match works + bumps version
  * PATCH with stale If-Match → 412
  * malformed If-Match → 400
  * two clients with the same view: exactly one wins, the other 412s
"""

from __future__ import annotations

import pytest

from tests.conftest import CsrfAwareClient

# (plural path, minimal create body)
RESOURCES = [
    ("customers", {"first_name": "Lock", "last_name": "Probe"}),
    ("tasks", {"title": "Lock Probe", "status": "todo"}),
]
IDS = ["customer", "task"]


@pytest.mark.parametrize("plural,create_body", RESOURCES, ids=IDS)
def test_new_row_starts_at_version_zero(
    plural: str, create_body: dict, admin_client: CsrfAwareClient
):
    r = admin_client.post(f"/api/{plural}", json=create_body)
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 0


@pytest.mark.parametrize("plural,create_body", RESOURCES, ids=IDS)
def test_patch_without_if_match_returns_428(
    plural: str, create_body: dict, admin_client: CsrfAwareClient
):
    row = admin_client.post(f"/api/{plural}", json=create_body).json()
    r = admin_client.patch(f"/api/{plural}/{row['id']}", json=create_body)
    # the guard rejects before any write, so the row is left untouched
    assert r.status_code == 428, r.text


@pytest.mark.parametrize("plural,create_body", RESOURCES, ids=IDS)
def test_patch_with_correct_if_match_bumps(
    plural: str, create_body: dict, admin_client: CsrfAwareClient
):
    row = admin_client.post(f"/api/{plural}", json=create_body).json()
    r = admin_client.patch(
        f"/api/{plural}/{row['id']}",
        json=create_body,
        headers={"If-Match": str(row["version"])},
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == row["version"] + 1


@pytest.mark.parametrize("plural,create_body", RESOURCES, ids=IDS)
def test_patch_with_stale_if_match_returns_412(
    plural: str, create_body: dict, admin_client: CsrfAwareClient
):
    row = admin_client.post(f"/api/{plural}", json=create_body).json()
    bumped = admin_client.patch(
        f"/api/{plural}/{row['id']}", json=create_body, headers={"If-Match": "0"}
    ).json()
    assert bumped["version"] == 1

    stale = admin_client.patch(
        f"/api/{plural}/{row['id']}", json=create_body, headers={"If-Match": "0"}
    )
    assert stale.status_code == 412, stale.text
    assert "version mismatch" in stale.json()["detail"].lower()


@pytest.mark.parametrize("plural,create_body", RESOURCES, ids=IDS)
def test_patch_with_malformed_if_match_returns_400(
    plural: str, create_body: dict, admin_client: CsrfAwareClient
):
    row = admin_client.post(f"/api/{plural}", json=create_body).json()
    r = admin_client.patch(
        f"/api/{plural}/{row['id']}", json=create_body, headers={"If-Match": "not-an-int"}
    )
    assert r.status_code == 400, r.text


@pytest.mark.parametrize("plural,create_body", RESOURCES, ids=IDS)
def test_concurrent_edit_one_wins_one_loses(
    plural: str, create_body: dict, admin_client: CsrfAwareClient
):
    row = admin_client.post(f"/api/{plural}", json=create_body).json()
    a = admin_client.patch(
        f"/api/{plural}/{row['id']}", json=create_body, headers={"If-Match": "0"}
    )
    assert a.status_code == 200
    b = admin_client.patch(
        f"/api/{plural}/{row['id']}", json=create_body, headers={"If-Match": "0"}
    )
    assert b.status_code == 412
