"""Keyset (cursor) pagination — TD-11.

Coverage:
  * A full walk via next_cursor returns every row exactly once, in order,
    with no overlap and no gap.
  * has_more / next_cursor are truthful at the boundary (last page has
    has_more=False and next_cursor=None).
  * The window is stable under a concurrent insert (a row added after
    page 1 is fetched never duplicates an already-seen row).
  * A malformed cursor is a 400, not a 500.
  * Cross-org rows never leak into another org's pages.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def _make_leads(client, n: int) -> set[str]:
    ids: set[str] = set()
    for i in range(n):
        r = client.post("/api/leads", json={"first_name": f"Page{i:02d}", "last_name": "Probe"})
        r.raise_for_status()
        ids.add(r.json()["id"])
    return ids


def test_full_walk_no_overlap_no_gap(admin_client):
    created = _make_leads(admin_client, 5)

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        url = f"/api/leads?limit=2{f'&cursor={cursor}' if cursor else ''}"
        body = admin_client.get(url).json()
        seen.extend(row["id"] for row in body["items"])
        pages += 1
        if not body["has_more"]:
            assert body["next_cursor"] is None
            break
        assert body["next_cursor"] is not None
        cursor = body["next_cursor"]
        assert pages < 10  # guard against an infinite loop

    # Every created lead seen exactly once (no overlap, no gap).
    assert created.issubset(set(seen))
    assert len(seen) == len(set(seen))


def test_order_is_created_at_desc(admin_client):
    _make_leads(admin_client, 4)
    items = admin_client.get("/api/leads?limit=50").json()["items"]
    created_ats = [row["created_at"] for row in items]
    assert created_ats == sorted(created_ats, reverse=True)


def test_stable_under_insert(admin_client):
    _make_leads(admin_client, 4)

    first = admin_client.get("/api/leads?limit=2").json()
    page1 = {row["id"] for row in first["items"]}
    cursor = first["next_cursor"]
    assert cursor is not None

    # A newer lead lands at the TOP of the DESC order; paging downward by
    # cursor must not surface or duplicate it on a later page.
    new_id = next(iter(_make_leads(admin_client, 1)))

    rest: set[str] = set()
    while cursor:
        body = admin_client.get(f"/api/leads?limit=2&cursor={cursor}").json()
        rest.update(row["id"] for row in body["items"])
        cursor = body["next_cursor"]

    assert page1.isdisjoint(rest)  # no duplicate across the boundary
    assert new_id not in rest  # the late insert didn't drift in


def test_invalid_cursor_is_400(admin_client):
    assert admin_client.get("/api/leads?cursor=not-a-valid-cursor").status_code == 400


def test_cross_org_rows_never_paged(admin_client, db: Session, other_org):
    db.execute(
        text(
            "INSERT INTO leads (id, organization_id, first_name, last_name, stage) "
            "VALUES (gen_random_uuid(), :org, 'Foreign', 'Probe', 'new')"
        ),
        {"org": other_org.id},
    )
    db.commit()

    seen: list[str] = []
    cursor = None
    while True:
        body = admin_client.get(f"/api/leads?limit=2{f'&cursor={cursor}' if cursor else ''}").json()
        seen.extend(row["first_name"] for row in body["items"])
        if not body["has_more"]:
            break
        cursor = body["next_cursor"]
    assert "Foreign" not in seen
