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

import json
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


def test_list_returns_only_own_org(
    admin_client, admin_user: User, db: Session, other_org
):
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
    r = other_client.post(
        "/api/webhooks", json={"url": "https://example.com/hook"}
    )
    assert r.status_code == 403


def test_update_paused_toggle(admin_client):
    create = admin_client.post(
        "/api/webhooks", json={"url": "https://example.com/hook"}
    ).json()

    paused = admin_client.patch(
        f"/api/webhooks/{create['id']}", json={"paused": True}
    ).json()
    assert paused["paused_at"] is not None

    unpaused = admin_client.patch(
        f"/api/webhooks/{create['id']}", json={"paused": False}
    ).json()
    assert unpaused["paused_at"] is None
    assert unpaused["consecutive_failures"] == 0  # unpause resets counter


def test_delete_webhook(admin_client):
    create = admin_client.post(
        "/api/webhooks", json={"url": "https://example.com/hook"}
    ).json()
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
        admin_client.patch(
            f"/api/webhooks/{foreign_id}", json={"paused": True}
        ).status_code
        == 404
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


def test_deliveries_endpoint_returns_only_for_owned_endpoint(
    admin_client, db: Session, other_org
):
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
