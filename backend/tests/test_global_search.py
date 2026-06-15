"""Unified global search (GET /api/search) — powers the Cmd/Ctrl+K palette.

Delegates to the leads/customers/companies list handlers, so this verifies
the combined envelope, the min-length gate, the limit, and auth — not the
FTS internals (covered by test_search.py).
"""

from __future__ import annotations


def test_requires_auth(client):
    assert client.get("/api/search?q=acme").status_code == 401


def test_short_query_returns_empty(admin_client):
    # < 2 chars → commands/navigation only, no entity scan.
    body = admin_client.get("/api/search?q=a").json()
    assert body == {"leads": [], "customers": [], "companies": []}


def test_missing_query_is_422(admin_client):
    assert admin_client.get("/api/search").status_code == 422


def test_finds_across_entities(admin_client):
    # Seed one of each with a shared, unusual token.
    tok = "Znarfle"
    admin_client.post("/api/leads", json={"first_name": tok, "last_name": "Lead"})
    admin_client.post("/api/customers", json={"first_name": tok, "last_name": "Cust"})
    admin_client.post("/api/companies", json={"name": f"{tok} Industries"})

    body = admin_client.get(f"/api/search?q={tok}").json()
    assert any(tok in (lead["first_name"] or "") for lead in body["leads"])
    assert any(tok in (c["first_name"] or "") for c in body["customers"])
    assert any(tok in (co["name"] or "") for co in body["companies"])


def test_respects_limit(admin_client):
    for i in range(3):
        admin_client.post("/api/leads", json={"first_name": "Bulkzz", "last_name": str(i)})
    body = admin_client.get("/api/search?q=Bulkzz&limit=2").json()
    assert len(body["leads"]) <= 2
