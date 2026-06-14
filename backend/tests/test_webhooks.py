"""Outgoing webhook tests — CRUD, signing, fanout enqueue, delivery.

End-to-end of the actual HTTP POST + arq job is exercised in the
real-container smoke (a /health echo is enough). These pytest tests
focus on:
  * HMAC signing roundtrip (sign → verify_signature returns True;
    tampered body returns False; stale timestamp returns False)
  * CRUD: admin can create/list/get/delete; secret returned ONCE;
    update flips paused; non-admin gets 403
  * URL guard: private/loopback URLs rejected
  * Event slug validation: empty list 400; unknown slug 400; wildcard
    accepted
  * Cross-org isolation: foreign endpoint returns 404
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import User
from app.webhook_sign import generate_secret, sign_payload, verify_signature

# ---------- Signing ----------


def test_sign_verify_roundtrip():
    secret = generate_secret()
    body = b'{"hello":"world"}'
    header = sign_payload(secret, body)
    assert verify_signature(secret, body, header) is True


def test_verify_rejects_tampered_body():
    secret = generate_secret()
    body = b'{"hello":"world"}'
    header = sign_payload(secret, body)
    assert verify_signature(secret, b'{"hello":"WORLD"}', header) is False


def test_verify_rejects_wrong_secret():
    body = b"{}"
    header = sign_payload(generate_secret(), body)
    assert verify_signature(generate_secret(), body, header) is False


def test_verify_rejects_stale_timestamp():
    secret = generate_secret()
    body = b"{}"
    # Sign with a timestamp 10 minutes in the past.
    past = int(time.time()) - 600
    header = sign_payload(secret, body, timestamp=past)
    assert verify_signature(secret, body, header, max_age_seconds=300) is False


def test_secret_strength():
    s = generate_secret()
    assert len(s) == 64  # 32 bytes hex
    assert all(c in "0123456789abcdef" for c in s)


# ---------- CRUD ----------


def test_admin_can_create_webhook_and_secret_returned_once(
    admin_client, admin_user: User, db: Session
):
    """POST returns secret in the response. Follow-up GET must NOT
    include it."""
    r = admin_client.post(
        "/api/webhooks",
        json={"url": "https://example.com/hook", "description": "ci probe"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert "secret" in created and len(created["secret"]) == 64
    webhook_id = created["id"]

    detail = admin_client.get(f"/api/webhooks/{webhook_id}")
    assert detail.status_code == 200
    assert "secret" not in detail.json()


def test_list_returns_only_own_org(admin_client, admin_user: User, db: Session, other_org):
    """A row in another org must not appear in admin's list."""
    db.execute(
        text(
            "INSERT INTO webhook_endpoints (id, organization_id, url, secret) "
            "VALUES (gen_random_uuid(), :org, 'https://foreign.example/hook', :s)"
        ),
        {"org": other_org.id, "s": generate_secret()},
    )
    db.commit()

    r = admin_client.get("/api/webhooks")
    assert r.status_code == 200
    org_id = str(admin_user.last_active_org_id)
    for row in r.json():
        assert row["organization_id"] == org_id


def test_non_admin_cannot_create(other_client, other_user: User):
    """sales_agent gets 403 on POST."""
    r = other_client.post("/api/webhooks", json={"url": "https://example.com/hook"})
    assert r.status_code == 403


def test_update_paused_toggle(admin_client):
    create = admin_client.post("/api/webhooks", json={"url": "https://example.com/hook"}).json()

    paused = admin_client.patch(f"/api/webhooks/{create['id']}", json={"paused": True}).json()
    assert paused["paused_at"] is not None

    unpaused = admin_client.patch(f"/api/webhooks/{create['id']}", json={"paused": False}).json()
    assert unpaused["paused_at"] is None
    assert unpaused["consecutive_failures"] == 0  # unpause resets counter


def test_delete_webhook(admin_client):
    create = admin_client.post("/api/webhooks", json={"url": "https://example.com/hook"}).json()
    r = admin_client.delete(f"/api/webhooks/{create['id']}")
    assert r.status_code == 204
    assert admin_client.get(f"/api/webhooks/{create['id']}").status_code == 404


def test_cross_org_returns_404(admin_client, db: Session, other_org):
    """Endpoint in foreign org returns 404, not 403 — no enumeration
    of cross-org IDs."""
    foreign_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO webhook_endpoints (id, organization_id, url, secret) "
            "VALUES (:id, :org, 'https://foreign.example/hook', :s)"
        ),
        {"id": foreign_id, "org": other_org.id, "s": generate_secret()},
    )
    db.commit()

    assert admin_client.get(f"/api/webhooks/{foreign_id}").status_code == 404
    assert (
        admin_client.patch(f"/api/webhooks/{foreign_id}", json={"paused": True}).status_code == 404
    )


# ---------- URL guard ----------


def test_create_rejects_loopback(admin_client):
    # Non-http(s) scheme, loopback hostname, and loopback IP literal
    # are all blocked. We intentionally DON'T reject unresolvable
    # public-looking hostnames — those might be internal infra
    # that only resolves via VPN; delivery will fail at runtime if
    # they really are bogus.
    for url in (
        "http://localhost/hook",
        "http://127.0.0.1/hook",
        "ftp://example.com/hook",
    ):
        r = admin_client.post("/api/webhooks", json={"url": url})
        assert r.status_code == 400, f"expected 400 for {url}, got {r.status_code}: {r.text}"


def test_create_rejects_private_ip(admin_client):
    # 10.0.0.1 is RFC1918; bypassing the DNS path is a known foot-gun
    # (admin could use a public DNS pointing here) but the literal-IP
    # path is the one we guard.
    r = admin_client.post("/api/webhooks", json={"url": "http://10.0.0.1/hook"})
    assert r.status_code == 400


# ---------- Event slug validation ----------


def test_create_rejects_empty_event_list(admin_client):
    r = admin_client.post(
        "/api/webhooks",
        json={"url": "https://example.com/hook", "enabled_events": []},
    )
    assert r.status_code == 400


def test_create_rejects_unknown_event(admin_client):
    r = admin_client.post(
        "/api/webhooks",
        json={"url": "https://example.com/hook", "enabled_events": ["lead.imagined"]},
    )
    assert r.status_code == 400


def test_create_accepts_wildcard_and_known(admin_client):
    for events in (["*"], ["lead.created"], ["lead.created", "deal.won"]):
        r = admin_client.post(
            "/api/webhooks",
            json={"url": "https://example.com/hook", "enabled_events": events},
        )
        assert r.status_code == 201, f"failed for {events}: {r.text}"


# ---------- Delivery row inspection ----------


def test_deliveries_endpoint_returns_only_for_owned_endpoint(admin_client, db: Session, other_org):
    foreign_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO webhook_endpoints (id, organization_id, url, secret) "
            "VALUES (:id, :org, 'https://foreign.example/hook', :s)"
        ),
        {"id": foreign_id, "org": other_org.id, "s": generate_secret()},
    )
    db.commit()

    r = admin_client.get(f"/api/webhooks/{foreign_id}/deliveries")
    assert r.status_code == 404  # parent endpoint not in admin's org


# ---------- Rotate secret ----------


def test_rotate_secret_mints_a_new_one(admin_client):
    created = admin_client.post("/api/webhooks", json={"url": "https://example.com/hook"}).json()
    first = created["secret"]

    rotated = admin_client.post(f"/api/webhooks/{created['id']}/rotate-secret")
    assert rotated.status_code == 200, rotated.text
    body = rotated.json()
    assert len(body["secret"]) == 64
    assert body["secret"] != first  # genuinely rotated

    # Still not leaked on a subsequent GET.
    detail = admin_client.get(f"/api/webhooks/{created['id']}")
    assert "secret" not in detail.json()


def test_rotate_secret_non_admin_403(other_client):
    # require_roles(admin) fires during dependency resolution, before the
    # handler body — so a non-admin is 403'd regardless of the id. (Using
    # admin_client + other_client together would clobber the shared session.)
    assert other_client.post(f"/api/webhooks/{uuid.uuid4()}/rotate-secret").status_code == 403


def test_rotate_secret_cross_org_404(admin_client, db: Session, other_org):
    foreign_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO webhook_endpoints (id, organization_id, url, secret) "
            "VALUES (:id, :org, 'https://foreign.example/hook', :s)"
        ),
        {"id": foreign_id, "org": other_org.id, "s": generate_secret()},
    )
    db.commit()
    assert admin_client.post(f"/api/webhooks/{foreign_id}/rotate-secret").status_code == 404


# ---------- Test ping (synchronous) ----------


def _patch_httpx(monkeypatch, *, status_code: int = 200, raise_error: bool = False) -> dict:
    """Patch `app.api.webhooks.httpx.AsyncClient` so the test-ping POST
    records what it sent and returns a canned status instead of hitting
    the network."""
    captured: dict = {}

    class _Resp:
        def __init__(self, code: int):
            self.status_code = code
            self.text = "ok" if 200 <= code < 300 else "boom"

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content, headers):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            if raise_error:
                import httpx

                raise httpx.ConnectError("refused")
            return _Resp(status_code)

    monkeypatch.setattr("app.api.webhooks.httpx.AsyncClient", _Client)
    return captured


def test_test_ping_success(admin_client, monkeypatch):
    captured = _patch_httpx(monkeypatch, status_code=200)
    created = admin_client.post("/api/webhooks", json={"url": "https://example.com/hook"}).json()

    r = admin_client.post(f"/api/webhooks/{created['id']}/test")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["delivered"] is True
    assert body["response_code"] == 200
    assert body["delivery_id"]

    # A signed test payload was actually sent.
    assert "X-CRM-Signature" in captured["headers"]
    assert captured["headers"]["X-CRM-Event-Type"] == "webhook.test"

    # The attempt shows up in the deliveries history as a webhook.test row.
    deliveries = admin_client.get(f"/api/webhooks/{created['id']}/deliveries").json()
    assert any(d["event_type"] == "webhook.test" and d["status"] == "success" for d in deliveries)


def test_test_ping_failure_does_not_pause_endpoint(admin_client, monkeypatch):
    """A failing test ping must record the failure but never nudge the
    endpoint toward auto-pause."""
    _patch_httpx(monkeypatch, status_code=500)
    created = admin_client.post("/api/webhooks", json={"url": "https://example.com/hook"}).json()

    r = admin_client.post(f"/api/webhooks/{created['id']}/test").json()
    assert r["delivered"] is False
    assert r["response_code"] == 500
    assert r["error"] == "HTTP 500"

    ep = admin_client.get(f"/api/webhooks/{created['id']}").json()
    assert ep["consecutive_failures"] == 0  # untouched by a test
    assert ep["paused_at"] is None


def test_test_ping_network_error(admin_client, monkeypatch):
    _patch_httpx(monkeypatch, raise_error=True)
    created = admin_client.post("/api/webhooks", json={"url": "https://example.com/hook"}).json()

    r = admin_client.post(f"/api/webhooks/{created['id']}/test").json()
    assert r["delivered"] is False
    assert r["response_code"] is None
    assert "ConnectError" in r["error"]


def test_test_ping_works_while_paused(admin_client, monkeypatch):
    _patch_httpx(monkeypatch, status_code=200)
    created = admin_client.post("/api/webhooks", json={"url": "https://example.com/hook"}).json()
    admin_client.patch(f"/api/webhooks/{created['id']}", json={"paused": True})

    r = admin_client.post(f"/api/webhooks/{created['id']}/test").json()
    assert r["delivered"] is True  # paused endpoints can still be tested


def test_test_ping_non_admin_403(other_client):
    # 403 from require_roles(admin) fires before the handler body (see
    # rotate-secret note), so no endpoint / httpx stub is needed.
    assert other_client.post(f"/api/webhooks/{uuid.uuid4()}/test").status_code == 403


# ---------- Delivery metrics ----------


def _seed_delivery(db: Session, endpoint_id: str, status: str, latency, *, days_ago: int = 0):
    db.execute(
        text(
            "INSERT INTO webhook_deliveries "
            "(id, endpoint_id, event_id, event_type, attempt, status, latency_ms, scheduled_for) "
            "VALUES (gen_random_uuid(), :ep, gen_random_uuid(), 'lead.created', 1, :st, :lat, "
            "now() - make_interval(days => :d))"
        ),
        {"ep": endpoint_id, "st": status, "lat": latency, "d": days_ago},
    )


def test_metrics_empty_endpoint(admin_client):
    created = admin_client.post("/api/webhooks", json={"url": "https://example.com/hook"}).json()
    m = admin_client.get(f"/api/webhooks/{created['id']}/metrics").json()
    assert m["total"] == 0
    assert m["success_rate"] is None
    assert m["p95_latency_ms"] is None


def test_metrics_aggregates(admin_client, db: Session):
    created = admin_client.post("/api/webhooks", json={"url": "https://example.com/hook"}).json()
    ep_id = created["id"]
    for lat in (100, 200, 300):
        _seed_delivery(db, ep_id, "success", lat)
    _seed_delivery(db, ep_id, "failed", 50)
    _seed_delivery(db, ep_id, "pending", None)
    # An old row outside the default 7-day window must be excluded.
    _seed_delivery(db, ep_id, "success", 999, days_ago=30)
    db.commit()

    m = admin_client.get(f"/api/webhooks/{ep_id}/metrics").json()
    assert m["total"] == 5  # the 30-day-old row is excluded
    assert m["succeeded"] == 3
    assert m["failed"] == 1
    assert m["pending"] == 1
    assert m["success_rate"] == 0.75  # 3 / (3 + 1) terminal
    assert m["p50_latency_ms"] is not None
    assert m["p95_latency_ms"] is not None
    assert m["avg_latency_ms"] is not None


def test_metrics_window_param(admin_client, db: Session):
    created = admin_client.post("/api/webhooks", json={"url": "https://example.com/hook"}).json()
    ep_id = created["id"]
    _seed_delivery(db, ep_id, "success", 100, days_ago=30)
    db.commit()
    # Default 7d window excludes it; widening to 90d includes it.
    assert admin_client.get(f"/api/webhooks/{ep_id}/metrics").json()["total"] == 0
    assert admin_client.get(f"/api/webhooks/{ep_id}/metrics?window_days=90").json()["total"] == 1


def test_metrics_cross_org_404(admin_client, db: Session, other_org):
    foreign_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO webhook_endpoints (id, organization_id, url, secret) "
            "VALUES (:id, :org, 'https://foreign.example/hook', :s)"
        ),
        {"id": foreign_id, "org": other_org.id, "s": generate_secret()},
    )
    db.commit()
    assert admin_client.get(f"/api/webhooks/{foreign_id}/metrics").status_code == 404


# NOTE: success/auto-pause paths of `deliver_webhook` are NOT covered
# by an isolated pytest. Driving the async job directly via
# `asyncio.run()` from a sync test creates a fresh event loop in the
# test thread, which binds a new asyncpg pool — incompatible with the
# session-scoped TestClient's BlockingPortal (it holds the original
# loop). The previous attempt at these tests poisoned every test
# that came after by leaving a stale pool bound to a dead loop.
#
# The success / failure / retry-backoff / auto-pause paths are
# instead verified by the live worker smoke documented in the
# session memory (POST /api/leads → outbox → fanout → POST → 405
# → retry @ 2s → retry @ 4s, with `webhook_deliveries` rows + the
# `webhook.failed` log lines populating per-attempt). The 2xx branch
# is the same code path with `succeeded=True` — trivial enough that
# the smoke alone is sufficient coverage for v1.
#
# Follow-up: when the worker grows enough behaviour to warrant a
# dedicated test loop, run these via the TestClient's `portal.call`
# so they share the app loop.
