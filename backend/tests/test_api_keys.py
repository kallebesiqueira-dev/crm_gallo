"""Public-API & API-key tests (ADR-016).

Two surfaces under test:

  * **Management CRUD** (`/api/api-keys`) — admin-gated, cookie+CSRF
    authed via `admin_client`. Mint (secret shown once), list, get,
    soft-revoke, role + cross-org guards.

  * **Bearer auth + `/api/v1`** — the server-to-server path. We mint a
    real key through the management endpoint, then drive `/api/v1` with
    an `Authorization: Bearer …` header (no cookie), exercising the
    distinct bearer dependency: scope enforcement, revoked/expired/
    garbage rejection, per-key rate limit, and org isolation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import api_auth
from app.api_keys import hash_token

BEARER = "Authorization"


def _mint(admin_client, *, name="k", scopes=None, expires_at=None) -> dict:
    """Create a key via the admin endpoint and return the full 201 body
    (includes the one-time plaintext `token`)."""
    body: dict = {"name": name}
    if scopes is not None:
        body["scopes"] = scopes
    if expires_at is not None:
        body["expires_at"] = expires_at
    r = admin_client.post("/api/api-keys", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _bearer(token: str) -> dict:
    return {BEARER: f"Bearer {token}"}


# ---------- Management: create / secret-once ----------


def test_create_returns_token_once_and_defaults_read(admin_client):
    body = _mint(admin_client, name="My Integration")
    assert body["name"] == "My Integration"
    assert body["token"].startswith("crmk_")
    assert body["display_prefix"].startswith("crmk_")
    # least-privilege default
    assert body["scopes"] == ["read"]
    # The plaintext token must NOT round-trip on a subsequent read.
    got = admin_client.get(f"/api/api-keys/{body['id']}").json()
    assert "token" not in got
    assert got["display_prefix"] == body["display_prefix"]


def test_create_stores_only_hash_never_plaintext(admin_client, db: Session):
    body = _mint(admin_client)
    row = (
        db.execute(text("SELECT hashed_key FROM api_keys WHERE id = :id"), {"id": body["id"]})
        .mappings()
        .one()
    )
    # DB holds the sha256, not the token.
    assert row["hashed_key"] == hash_token(body["token"])
    assert row["hashed_key"] != body["token"]


def test_create_with_write_scope(admin_client):
    body = _mint(admin_client, scopes=["read", "write"])
    assert set(body["scopes"]) == {"read", "write"}


def test_create_empty_scopes_is_422(admin_client):
    r = admin_client.post("/api/api-keys", json={"name": "x", "scopes": []})
    assert r.status_code == 422


def test_list_and_get(admin_client):
    a = _mint(admin_client, name="a")
    b = _mint(admin_client, name="b")
    listed = admin_client.get("/api/api-keys").json()
    ids = {k["id"] for k in listed}
    assert {a["id"], b["id"]} <= ids
    assert all("token" not in k for k in listed)


# ---------- Management: role + cross-org guards ----------


def test_non_admin_cannot_create(other_client):
    # other_client is a sales_agent in the same org → 403.
    r = other_client.post("/api/api-keys", json={"name": "x"})
    assert r.status_code == 403


def test_get_cross_org_is_404(admin_client, db: Session, other_org):
    # Seed a key in ANOTHER org directly; it must look not-found.
    foreign_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO api_keys (id, organization_id, name, hashed_key, display_prefix, scopes) "
            "VALUES (:id, :org, 'foreign', :h, 'crmk_x…y', '[\"read\"]')"
        ),
        {"id": foreign_id, "org": other_org.id, "h": hash_token(f"crmk_{other_org.id.hex}_zzz")},
    )
    db.commit()
    assert admin_client.get(f"/api/api-keys/{foreign_id}").status_code == 404


# ---------- Management: revoke ----------


def test_revoke_sets_timestamp_and_is_idempotent(admin_client):
    body = _mint(admin_client)
    first = admin_client.delete(f"/api/api-keys/{body['id']}")
    assert first.status_code == 200
    assert first.json()["revoked_at"] is not None
    # Revoking again is a no-op that returns the same (still-revoked) state.
    second = admin_client.delete(f"/api/api-keys/{body['id']}")
    assert second.status_code == 200
    assert second.json()["revoked_at"] == first.json()["revoked_at"]


# ---------- Bearer auth: happy path + version header ----------


def test_bearer_lists_leads_without_cookie(admin_client):
    token = _mint(admin_client, scopes=["read"])["token"]
    # Drop the session cookie to prove the bearer path is cookie-independent.
    admin_client.cookies.clear()
    r = admin_client.get("/api/v1/leads", headers=_bearer(token))
    assert r.status_code == 200, r.text
    assert r.headers["X-API-Version"] == "v1"
    body = r.json()
    assert "items" in body and "next_cursor" in body


def test_bearer_write_creates_and_reads_back_lead(admin_client):
    token = _mint(admin_client, scopes=["read", "write"])["token"]
    admin_client.cookies.clear()
    created = admin_client.post(
        "/api/v1/leads",
        headers=_bearer(token),
        json={"first_name": "Api", "last_name": "Made"},
    )
    assert created.status_code == 201, created.text
    lead_id = created.json()["id"]
    got = admin_client.get(f"/api/v1/leads/{lead_id}", headers=_bearer(token))
    assert got.status_code == 200
    assert got.json()["first_name"] == "Api"


def test_bearer_creates_customer(admin_client):
    token = _mint(admin_client, scopes=["read", "write"])["token"]
    r = admin_client.post(
        "/api/v1/customers",
        headers=_bearer(token),
        json={"first_name": "Cust", "last_name": "Viabearer"},
    )
    assert r.status_code == 201, r.text


# ---------- Bearer auth: scope enforcement ----------


def test_read_scope_cannot_write(admin_client):
    token = _mint(admin_client, scopes=["read"])["token"]
    r = admin_client.post(
        "/api/v1/leads",
        headers=_bearer(token),
        json={"first_name": "No", "last_name": "Write"},
    )
    assert r.status_code == 403


# ---------- Bearer auth: rejection paths ----------


def test_missing_bearer_is_401(admin_client):
    admin_client.cookies.clear()
    assert admin_client.get("/api/v1/leads").status_code == 401


def test_garbage_token_is_401(admin_client):
    admin_client.cookies.clear()
    assert admin_client.get("/api/v1/leads", headers=_bearer("not-a-key")).status_code == 401


def test_wellformed_but_unknown_token_is_401(admin_client, test_org):
    # Correct shape (crmk_{org_hex}_secret), org exists, but no matching hash.
    bogus = f"crmk_{test_org.id.hex}_deadbeefsecret"
    admin_client.cookies.clear()
    assert admin_client.get("/api/v1/leads", headers=_bearer(bogus)).status_code == 401


def test_revoked_key_is_401(admin_client):
    body = _mint(admin_client, scopes=["read"])
    admin_client.delete(f"/api/api-keys/{body['id']}")
    r = admin_client.get("/api/v1/leads", headers=_bearer(body["token"]))
    assert r.status_code == 401


def test_expired_key_is_401(admin_client):
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    body = _mint(admin_client, scopes=["read"], expires_at=past)
    r = admin_client.get("/api/v1/leads", headers=_bearer(body["token"]))
    assert r.status_code == 401


# ---------- Bearer auth: per-key rate limit ----------


def test_rate_limit_trips_429(admin_client, monkeypatch):
    monkeypatch.setattr(api_auth.settings, "api_key_rate_limit_per_minute", 2)
    token = _mint(admin_client, scopes=["read"])["token"]
    h = _bearer(token)
    assert admin_client.get("/api/v1/leads", headers=h).status_code == 200
    assert admin_client.get("/api/v1/leads", headers=h).status_code == 200
    # Third call in the same minute window exceeds the budget.
    assert admin_client.get("/api/v1/leads", headers=h).status_code == 429


# ---------- Bearer auth: org isolation ----------


def test_v1_is_org_scoped(admin_client, db: Session, other_org):
    db.execute(
        text(
            "INSERT INTO leads (id, organization_id, first_name, last_name, stage) "
            "VALUES (gen_random_uuid(), :org, 'Foreign', 'Probe', 'new')"
        ),
        {"org": other_org.id},
    )
    db.commit()
    token = _mint(admin_client, scopes=["read"])["token"]
    body = admin_client.get("/api/v1/leads", headers=_bearer(token)).json()
    names = {it["first_name"] for it in body["items"]}
    assert "Foreign" not in names


def test_last_used_at_is_recorded(admin_client, db: Session):
    body = _mint(admin_client, scopes=["read"])
    admin_client.get("/api/v1/leads", headers=_bearer(body["token"]))
    row = (
        db.execute(text("SELECT last_used_at FROM api_keys WHERE id = :id"), {"id": body["id"]})
        .mappings()
        .one()
    )
    assert row["last_used_at"] is not None
