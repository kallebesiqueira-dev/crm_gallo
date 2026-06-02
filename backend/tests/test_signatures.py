"""E-signature requests on quotes — CRUD, manual signing state machine,
inbound webhook HMAC, RLS/ownership (ADR-016).

HTTP tests drive the real endpoints through RLS as a logged-in user, same
posture as test_quotes. The manual provider is the default, so the in-app
sign flow needs no vendor config; webhook tests seed a vendor-style request
(non-NULL `external_id`) and sign the payload with the configured secret.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Organization,
    Quote,
    QuoteLineItem,
    QuoteStatus,
    SignatureRequest,
    SignatureStatus,
    User,
)
from app.webhook_sign import SIGNATURE_HEADER, sign_payload
from tests.conftest import CsrfAwareClient

# ---------- helpers ----------

_LINES = [{"description": "Design", "quantity": 2, "unit_price": 250.0}]


def _sent_quote(client: CsrfAwareClient) -> dict:
    """Create a quote and move it to `sent` — the only state a signature
    request can be raised from."""
    r = client.post("/api/quotes", json={"title": "Proposal", "tax_rate": 0.0, "line_items": _LINES})
    assert r.status_code == 201, r.text
    q = r.json()
    client.post(f"/api/quotes/{q['id']}/send").raise_for_status()
    return q


def _create_request(client: CsrfAwareClient, quote_id: str, **overrides) -> dict:
    payload = {
        "quote_id": quote_id,
        "signer_name": "Jane Signer",
        "signer_email": "jane@example.com",
    }
    payload.update(overrides)
    r = client.post("/api/signatures", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _send(client: CsrfAwareClient, req_id: str) -> dict:
    r = client.post(f"/api/signatures/{req_id}/send")
    assert r.status_code == 200, r.text
    return r.json()


def _token_from_url(signing_url: str) -> str:
    assert "/sign/" in signing_url, signing_url
    return signing_url.split("/sign/", 1)[1]


def _seed_sent_quote(db: Session, org: Organization, owner: User | None) -> Quote:
    quote = Quote(
        organization_id=org.id,
        number="Q-000001",
        version=1,
        status=QuoteStatus.sent,
        title="Seeded quote",
        tax_rate=0.0,
        owner_id=owner.id if owner else None,
    )
    quote.line_items = [
        QuoteLineItem(organization_id=org.id, description="Item", quantity=1, unit_price=100.0)
    ]
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote


def _seed_request(
    db: Session,
    org: Organization,
    quote: Quote,
    owner: User | None,
    *,
    status: SignatureStatus = SignatureStatus.sent,
    provider: str = "skribble",
    external_id: str | None = "env_seed_1",
) -> SignatureRequest:
    req = SignatureRequest(
        organization_id=org.id,
        quote_id=quote.id,
        provider=provider,
        status=status,
        signer_name="Jane Signer",
        signer_email="jane@example.com",
        external_id=external_id,
        owner_id=owner.id if owner else None,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


# ---------- create / CRUD ----------


def test_create_from_sent_quote(admin_client):
    q = _sent_quote(admin_client)
    req = _create_request(admin_client, q["id"])
    assert req["status"] == "drafted"
    assert req["provider"] == "manual"
    assert req["quote_id"] == q["id"]
    assert req["signed_at"] is None


def test_cannot_create_from_draft_quote(admin_client):
    r = admin_client.post(
        "/api/quotes", json={"title": "Draft", "tax_rate": 0.0, "line_items": _LINES}
    )
    q = r.json()
    resp = admin_client.post(
        "/api/signatures",
        json={"quote_id": q["id"], "signer_name": "X", "signer_email": "x@example.com"},
    )
    assert resp.status_code == 409


def test_create_against_missing_quote_404(admin_client):
    resp = admin_client.post(
        "/api/signatures",
        json={
            "quote_id": str(uuid.uuid4()),
            "signer_name": "X",
            "signer_email": "x@example.com",
        },
    )
    assert resp.status_code == 404


def test_get_and_list(admin_client):
    q = _sent_quote(admin_client)
    req = _create_request(admin_client, q["id"])
    got = admin_client.get(f"/api/signatures/{req['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == req["id"]

    listed = admin_client.get("/api/signatures")
    assert listed.status_code == 200
    assert any(item["id"] == req["id"] for item in listed.json()["items"])

    filtered = admin_client.get(f"/api/signatures?quote_id={q['id']}")
    assert filtered.status_code == 200
    assert all(item["quote_id"] == q["id"] for item in filtered.json()["items"])


def test_soft_delete_then_404(admin_client):
    q = _sent_quote(admin_client)
    req = _create_request(admin_client, q["id"])
    assert admin_client.delete(f"/api/signatures/{req['id']}").status_code == 204
    assert admin_client.get(f"/api/signatures/{req['id']}").status_code == 404


# ---------- send / state machine ----------


def test_send_mints_token_and_sets_sent(admin_client):
    q = _sent_quote(admin_client)
    req = _create_request(admin_client, q["id"])
    sent = _send(admin_client, req["id"])
    assert sent["status"] == "sent"
    assert sent["sent_at"] is not None
    assert sent["signing_url"]
    assert "/sign/" in sent["signing_url"]


def test_cannot_send_twice(admin_client):
    q = _sent_quote(admin_client)
    req = _create_request(admin_client, q["id"])
    _send(admin_client, req["id"])
    r = admin_client.post(f"/api/signatures/{req['id']}/send")
    assert r.status_code == 409


def test_cancel_then_cannot_send(admin_client):
    q = _sent_quote(admin_client)
    req = _create_request(admin_client, q["id"])
    cancelled = admin_client.post(f"/api/signatures/{req['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert admin_client.post(f"/api/signatures/{req['id']}/send").status_code == 409


# ---------- manual signing surface (unauthenticated token) ----------


def test_view_marks_viewed(admin_client):
    q = _sent_quote(admin_client)
    req = _create_request(admin_client, q["id"])
    token = _token_from_url(_send(admin_client, req["id"])["signing_url"])

    page = admin_client.get(f"/api/signatures/sign/{token}")
    assert page.status_code == 200, page.text
    ctx = page.json()
    assert ctx["status"] == "viewed"
    assert ctx["quote_number"] == q["number"]
    assert ctx["signer_name"] == "Jane Signer"

    # The request itself is now `viewed`.
    assert admin_client.get(f"/api/signatures/{req['id']}").json()["status"] == "viewed"


def test_manual_sign_signs_and_accepts_quote(admin_client):
    q = _sent_quote(admin_client)
    req = _create_request(admin_client, q["id"])
    token = _token_from_url(_send(admin_client, req["id"])["signing_url"])

    signed = admin_client.post(
        f"/api/signatures/sign/{token}", json={"typed_name": "Jane Q. Signer"}
    )
    assert signed.status_code == 200, signed.text
    body = signed.json()
    assert body["status"] == "signed"
    assert body["signed_at"] is not None
    assert body["signed_document_key"]  # audit trail persisted to S3

    # A signed quote IS an acceptance.
    assert admin_client.get(f"/api/quotes/{q['id']}").json()["status"] == "accepted"


def test_decline(admin_client):
    q = _sent_quote(admin_client)
    req = _create_request(admin_client, q["id"])
    token = _token_from_url(_send(admin_client, req["id"])["signing_url"])

    declined = admin_client.post(
        f"/api/signatures/sign/{token}/decline", json={"reason": "Out of budget"}
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "declined"
    # Quote stays sent — a decline is not an acceptance.
    assert admin_client.get(f"/api/quotes/{q['id']}").json()["status"] == "sent"


def test_cannot_sign_after_signed_410(admin_client):
    q = _sent_quote(admin_client)
    req = _create_request(admin_client, q["id"])
    token = _token_from_url(_send(admin_client, req["id"])["signing_url"])
    admin_client.post(f"/api/signatures/sign/{token}", json={"typed_name": "Jane"})

    # Re-signing is a 409; re-viewing the page is a 410 (already signed).
    assert (
        admin_client.post(f"/api/signatures/sign/{token}", json={"typed_name": "Jane"}).status_code
        == 409
    )
    assert admin_client.get(f"/api/signatures/sign/{token}").status_code == 410


def test_bad_token_404(admin_client):
    # Well-formed org prefix, garbage secret.
    bad = f"{uuid.uuid4().hex}.deadbeef"
    assert admin_client.get(f"/api/signatures/sign/{bad}").status_code == 404
    # Malformed token (no org prefix) is also a 404, not a 500.
    assert admin_client.get("/api/signatures/sign/not-a-token").status_code == 404


# ---------- inbound vendor webhook ----------


def test_webhook_503_when_unconfigured(client: CsrfAwareClient):
    # Default settings leave the secret empty.
    assert get_settings().signing_webhook_secret == ""
    r = client.post("/api/signatures/webhook", json={"event": "signed"})
    assert r.status_code == 503


def test_webhook_400_on_bad_signature(client: CsrfAwareClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "signing_webhook_secret", "whsec_test")
    body = json.dumps({"organization_id": str(uuid.uuid4()), "external_id": "x", "event": "signed"})
    r = client.post(
        "/api/signatures/webhook",
        content=body,
        headers={SIGNATURE_HEADER: "t=1,v1=deadbeef", "content-type": "application/json"},
    )
    assert r.status_code == 400


def test_webhook_400_on_missing_header(client: CsrfAwareClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "signing_webhook_secret", "whsec_test")
    r = client.post("/api/signatures/webhook", json={"event": "signed"})
    assert r.status_code == 400


def test_webhook_valid_signed_advances_and_accepts(
    client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
    monkeypatch,
):
    secret = "whsec_test"
    monkeypatch.setattr(get_settings(), "signing_webhook_secret", secret)
    quote = _seed_sent_quote(db, test_org, owner=admin_user)
    req = _seed_request(db, test_org, quote, owner=admin_user, external_id="env_abc")

    body = json.dumps(
        {"organization_id": str(test_org.id), "external_id": "env_abc", "event": "signed"}
    ).encode("utf-8")
    sig = sign_payload(secret, body)
    r = client.post(
        "/api/signatures/webhook",
        content=body,
        headers={SIGNATURE_HEADER: sig, "content-type": "application/json"},
    )
    assert r.status_code == 204, r.text

    db.refresh(req)
    db.refresh(quote)
    assert req.status == SignatureStatus.signed
    assert quote.status == QuoteStatus.accepted


def test_webhook_unknown_envelope_is_noop_2xx(client: CsrfAwareClient, monkeypatch):
    secret = "whsec_test"
    monkeypatch.setattr(get_settings(), "signing_webhook_secret", secret)
    body = json.dumps(
        {"organization_id": str(uuid.uuid4()), "external_id": "nope", "event": "signed"}
    ).encode("utf-8")
    sig = sign_payload(secret, body)
    r = client.post(
        "/api/signatures/webhook",
        content=body,
        headers={SIGNATURE_HEADER: sig, "content-type": "application/json"},
    )
    # Verified but unplaceable → 2xx no-op so the vendor stops retrying.
    assert r.status_code == 204


# ---------- ownership + cross-org isolation ----------


def test_non_owner_cannot_send(
    other_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    quote = _seed_sent_quote(db, test_org, owner=admin_user)
    req = _seed_request(
        db, test_org, quote, owner=admin_user, status=SignatureStatus.drafted
    )
    r = other_client.post(f"/api/signatures/{req.id}/send")
    assert r.status_code == 403


def test_cross_org_returns_404(
    admin_client: CsrfAwareClient,
    db: Session,
    other_org: Organization,
    foreign_user: User,
):
    quote = _seed_sent_quote(db, other_org, owner=foreign_user)
    foreign = _seed_request(db, other_org, quote, owner=foreign_user)
    assert admin_client.get(f"/api/signatures/{foreign.id}").status_code == 404
    assert admin_client.post(f"/api/signatures/{foreign.id}/send").status_code == 404
    assert admin_client.delete(f"/api/signatures/{foreign.id}").status_code == 404


def test_random_id_404(admin_client: CsrfAwareClient):
    assert admin_client.get(f"/api/signatures/{uuid.uuid4()}").status_code == 404
