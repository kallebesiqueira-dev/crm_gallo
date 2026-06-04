"""Optimistic locking on Deal — TD-12.

Coverage:
  * Fresh deal starts at version=0
  * PATCH with no If-Match → 428 Precondition Required (strict mode)
  * PATCH with correct If-Match works + bumps version
  * PATCH with stale If-Match returns 412
  * Concurrent edit scenario: two clients read v=0, both PATCH with
    If-Match=0. The second wins-or-loses based on order, but exactly
    ONE gets 412.
  * Move also enforces If-Match
  * Malformed If-Match returns 400
"""

from __future__ import annotations


def test_new_deal_starts_at_version_zero(admin_client):
    r = admin_client.post("/api/deals", json={"title": "v0 probe", "value": 100}).json()
    assert r["version"] == 0


def test_patch_without_if_match_returns_428(admin_client):
    """Strict mode: the header is required; a missing one is rejected, not mutated."""
    deal = admin_client.post("/api/deals", json={"title": "no-header probe"}).json()
    r = admin_client.patch(f"/api/deals/{deal['id']}", json={"title": "renamed"})
    assert r.status_code == 428, r.text
    after = admin_client.get(f"/api/deals/{deal['id']}").json()
    assert after["version"] == 0


def test_patch_with_correct_if_match_bumps_version(admin_client):
    deal = admin_client.post("/api/deals", json={"title": "match probe"}).json()
    r = admin_client.patch(
        f"/api/deals/{deal['id']}",
        json={"title": "renamed"},
        headers={"If-Match": str(deal["version"])},
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == deal["version"] + 1


def test_patch_with_stale_if_match_returns_412(admin_client):
    deal = admin_client.post("/api/deals", json={"title": "stale probe"}).json()
    # Bump version via one successful patch.
    bumped = admin_client.patch(
        f"/api/deals/{deal['id']}",
        json={"title": "bumped"},
        headers={"If-Match": "0"},
    ).json()
    assert bumped["version"] == 1

    # Now retry with the stale version=0 — must fail.
    stale = admin_client.patch(
        f"/api/deals/{deal['id']}",
        json={"title": "should fail"},
        headers={"If-Match": "0"},
    )
    assert stale.status_code == 412, stale.text
    assert "version mismatch" in stale.json()["detail"].lower()


def test_patch_with_quoted_if_match_accepted(admin_client):
    """RFC 7232 etag-quoted form `If-Match: "7"` should also work."""
    deal = admin_client.post("/api/deals", json={"title": "quoted probe"}).json()
    r = admin_client.patch(
        f"/api/deals/{deal['id']}",
        json={"title": "renamed"},
        headers={"If-Match": '"0"'},
    )
    assert r.status_code == 200, r.text


def test_patch_with_malformed_if_match_returns_400(admin_client):
    deal = admin_client.post("/api/deals", json={"title": "malformed probe"}).json()
    r = admin_client.patch(
        f"/api/deals/{deal['id']}",
        json={"title": "renamed"},
        headers={"If-Match": "not-an-int"},
    )
    assert r.status_code == 400


def test_move_also_enforces_if_match(admin_client):
    deal = admin_client.post("/api/deals", json={"title": "move probe"}).json()
    admin_client.patch(
        f"/api/deals/{deal['id']}",
        json={"title": "first edit"},
        headers={"If-Match": "0"},
    ).raise_for_status()

    # Stale If-Match on /move should also 412.
    r = admin_client.post(
        f"/api/deals/{deal['id']}/move",
        json={"stage": "qualified", "sort_index": 0},
        headers={"If-Match": "0"},
    )
    assert r.status_code == 412


def test_concurrent_edit_one_wins_one_loses(admin_client):
    """Simulate two clients with the same view of the deal. Both
    PATCH with If-Match=0; the first wins, the second sees 412."""
    deal = admin_client.post("/api/deals", json={"title": "concurrency"}).json()

    # First client succeeds.
    a = admin_client.patch(
        f"/api/deals/{deal['id']}",
        json={"title": "A"},
        headers={"If-Match": "0"},
    )
    assert a.status_code == 200
    # Second client (same If-Match=0) loses.
    b = admin_client.patch(
        f"/api/deals/{deal['id']}",
        json={"title": "B"},
        headers={"If-Match": "0"},
    )
    assert b.status_code == 412
