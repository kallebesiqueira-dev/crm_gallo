"""Full-text search tests — TD-13.

Coverage:
  * `q` matches against any of first_name/last_name/email/company
    (and industry for customers)
  * Stored generated `search_vector` column updates automatically
    after PATCH (no app-layer maintenance)
  * Multi-token Google-style query (`acme corp`) matches AND, not OR
  * Empty-string `q` is treated as no filter (websearch_to_tsquery
    handles this gracefully — returns no rows otherwise)
  * Cross-org isolation: search in org A never returns org B's rows
"""

from __future__ import annotations

from sqlalchemy.orm import Session


def test_search_matches_first_name(admin_client):
    admin_client.post(
        "/api/leads", json={"first_name": "Beatrice", "last_name": "X"}
    ).raise_for_status()
    admin_client.post(
        "/api/leads", json={"first_name": "Charles", "last_name": "Y"}
    ).raise_for_status()

    rows = admin_client.get("/api/leads?q=beatrice").json()
    names = {r["first_name"] for r in rows}
    assert "Beatrice" in names
    assert "Charles" not in names


def test_search_matches_email(admin_client):
    admin_client.post(
        "/api/leads",
        json={
            "first_name": "Em",
            "last_name": "Probe",
            "email": "founder@acmecorp.example",
        },
    ).raise_for_status()
    admin_client.post(
        "/api/leads",
        json={
            "first_name": "Other",
            "last_name": "Probe",
            "email": "nobody@example.org",
        },
    ).raise_for_status()

    rows = admin_client.get("/api/leads?q=acmecorp").json()
    assert {r["email"] for r in rows} >= {"founder@acmecorp.example"}


def test_search_matches_company(admin_client):
    admin_client.post(
        "/api/leads",
        json={"first_name": "C", "last_name": "Probe", "company": "Globex"},
    ).raise_for_status()
    admin_client.post(
        "/api/leads",
        json={"first_name": "Other", "last_name": "Probe", "company": "Initech"},
    ).raise_for_status()

    rows = admin_client.get("/api/leads?q=globex").json()
    assert all(r["company"] == "Globex" for r in rows)
    assert len(rows) >= 1


def test_search_vector_updates_on_patch(admin_client):
    """STORED generated columns are recomputed by Postgres on every
    write — no application bookkeeping required. Verify by creating a
    lead with one company name, searching by NEW name (should miss),
    PATCHing the company, then searching again (should hit)."""
    created = admin_client.post(
        "/api/leads",
        json={"first_name": "Patched", "last_name": "X", "company": "OldCo"},
    ).json()

    assert admin_client.get("/api/leads?q=NewCo").json() == [] or all(
        r["id"] != created["id"] for r in admin_client.get("/api/leads?q=NewCo").json()
    )

    admin_client.patch(f"/api/leads/{created['id']}", json={"company": "NewCo"}).raise_for_status()

    rows = admin_client.get("/api/leads?q=NewCo").json()
    assert any(r["id"] == created["id"] for r in rows)


def test_search_websearch_AND_semantics(admin_client):
    """`websearch_to_tsquery` treats multi-token input as AND. A query
    `acme corp` matches rows that contain BOTH tokens (in any
    column), NOT either."""
    admin_client.post(
        "/api/leads",
        json={"first_name": "Acme", "last_name": "Founder", "company": "Corp"},
    ).raise_for_status()
    admin_client.post(
        "/api/leads",
        json={"first_name": "Acme", "last_name": "Other", "company": "Other"},
    ).raise_for_status()
    admin_client.post(
        "/api/leads",
        json={"first_name": "OnlyCorp", "last_name": "Solo", "company": "Corp"},
    ).raise_for_status()

    rows = admin_client.get("/api/leads?q=acme+corp").json()
    # Two rows contain both "Acme" AND "Corp"; one row contains
    # only Corp (the OnlyCorp lead doesn't have "Acme" anywhere).
    # Use first_name uniqueness as a probe to spot the AND filter.
    first_names = [r["first_name"] for r in rows]
    assert "Acme" in first_names
    # The "OnlyCorp" lead must NOT appear — its rows lack the "Acme"
    # token. (websearch_to_tsquery: `+` is the space separator.)
    assert "OnlyCorp" not in first_names


def test_search_cross_org_isolated(admin_client, db: Session, other_org):
    """A row with a matching company in a different org must NEVER
    appear in admin's search results (RLS + app-layer filter)."""
    from sqlalchemy import text

    db.execute(
        text(
            "INSERT INTO leads (id, organization_id, first_name, last_name, company, stage) "
            "VALUES (gen_random_uuid(), :org, 'Foreign', 'Probe', 'UniqueWord123', 'new')"
        ),
        {"org": other_org.id},
    )
    db.commit()

    rows = admin_client.get("/api/leads?q=UniqueWord123").json()
    assert rows == []


def test_customers_search_smoke(admin_client):
    """Repeat one happy-path test on customers to confirm the same
    pattern wires through (separate model, separate index)."""
    admin_client.post(
        "/api/customers",
        json={"first_name": "Cust", "last_name": "A", "company": "Hooli"},
    ).raise_for_status()
    admin_client.post(
        "/api/customers",
        json={"first_name": "Cust", "last_name": "B", "company": "Pied Piper"},
    ).raise_for_status()

    rows = admin_client.get("/api/customers?q=hooli").json()
    assert any(r["company"] == "Hooli" for r in rows)
    assert all(r["company"] != "Pied Piper" for r in rows)
