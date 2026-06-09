"""WhatsApp Business Cloud integration (phase 1).

Covers the two surfaces of `app.api.whatsapp`:

  * the UNauthenticated Meta webhook — GET verify handshake, POST HMAC gate,
    inbound persistence + dedupe, outbound-status progression, tenant routing;
  * the authenticated tenant API — account connect/RBAC/uniqueness, conversation
    listing + isolation, and the outbound-send enqueue path.

Webhook POSTs go through the same sync `CsrfAwareClient` as everything else.
They carry NO auth cookie, so the CSRF middleware treats them as it does any
public mutation (exempt) and the only thing standing between the network and
tenant data is the `X-Hub-Signature-256` HMAC — which is exactly what these
tests exercise. Persistence is asserted via the owner-role `db` session
(BYPASSRLS) so we read what the RLS'd request actually wrote.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Conversation,
    ConversationChannel,
    Customer,
    Lead,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    Organization,
    User,
    WhatsAppAccount,
    WhatsAppAccountStatus,
)
from app.whatsapp import parse_webhook, verify_challenge, verify_signature
from tests.conftest import TEST_PASSWORD, CsrfAwareClient

_APP_SECRET = "pytest-app-secret"
_VERIFY_TOKEN = "pytest-verify-token"
_PNID = "pytest-pnid-1"


# ---------- config ----------


@pytest.fixture
def wa_config():
    """Point the cached Settings singleton at known webhook credentials for
    the duration of one test. `app.whatsapp` reads `get_settings()` at call
    time, so mutating the singleton is enough — restored on teardown."""
    s = get_settings()
    orig_secret, orig_token = s.whatsapp_app_secret, s.whatsapp_verify_token
    s.whatsapp_app_secret = _APP_SECRET
    s.whatsapp_verify_token = _VERIFY_TOKEN
    yield
    s.whatsapp_app_secret, s.whatsapp_verify_token = orig_secret, orig_token


# ---------- seed helpers ----------


def _make_account(
    db: Session,
    org: Organization,
    *,
    phone_number_id: str = _PNID,
    status: WhatsAppAccountStatus = WhatsAppAccountStatus.active,
) -> WhatsAppAccount:
    acct = WhatsAppAccount(
        organization_id=org.id,
        phone_number_id=phone_number_id,
        access_token="seed-access-token",
        status=status,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def _make_conversation(
    db: Session,
    org: Organization,
    account: WhatsAppAccount,
    *,
    contact_wa_id: str = "5511988887777",
) -> Conversation:
    conv = Conversation(
        organization_id=org.id,
        account_id=account.id,
        channel=ConversationChannel.whatsapp,
        contact_wa_id=contact_wa_id,
        contact_name="Pytest Contact",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _make_lead(db: Session, org: Organization, *, first_name: str = "Lead") -> Lead:
    lead = Lead(organization_id=org.id, first_name=first_name, last_name="Pytest")
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def _make_customer(db: Session, org: Organization, *, first_name: str = "Customer") -> Customer:
    cust = Customer(organization_id=org.id, first_name=first_name, last_name="Pytest")
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return cust


# ---------- signed-webhook helpers ----------


def _sign(raw: bytes, secret: str = _APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def _post_webhook(client: CsrfAwareClient, payload: dict, *, secret: str = _APP_SECRET):
    raw = json.dumps(payload).encode()
    return client.post(
        "/api/whatsapp/webhook",
        content=raw,
        headers={"X-Hub-Signature-256": _sign(raw, secret), "Content-Type": "application/json"},
    )


def _inbound_payload(
    pnid: str = _PNID,
    *,
    sender: str = "5511988887777",
    wamid: str = "wamid.pytest.1",
    body: str = "olá",
    name: str = "Alice",
) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": pnid},
                            "contacts": [{"wa_id": sender, "profile": {"name": name}}],
                            "messages": [
                                {
                                    "id": wamid,
                                    "from": sender,
                                    "type": "text",
                                    "timestamp": "1700000000",
                                    "text": {"body": body},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def _status_payload(wamid: str, status: str, pnid: str = _PNID) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": pnid},
                            "statuses": [
                                {
                                    "id": wamid,
                                    "status": status,
                                    "timestamp": "1700000100",
                                    "recipient_id": "5511988887777",
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


# ====================== pure transport ======================


def test_verify_signature_roundtrip(wa_config):
    raw = b'{"hello":"world"}'
    assert verify_signature(raw, _sign(raw)) is True
    assert verify_signature(raw, _sign(b"tampered")) is False
    assert verify_signature(raw, None) is False
    assert verify_signature(raw, "md5=deadbeef") is False


def test_verify_challenge(wa_config):
    assert verify_challenge("subscribe", _VERIFY_TOKEN) is True
    assert verify_challenge("subscribe", "wrong") is False
    assert verify_challenge("unsubscribe", _VERIFY_TOKEN) is False


def test_parse_webhook_is_defensive():
    # Garbage in → empty result out, never raises (Meta retries hard on 5xx).
    assert parse_webhook({}).messages == []
    assert parse_webhook({"entry": [{"changes": [{}]}]}).statuses == []
    parsed = parse_webhook(_inbound_payload())
    assert len(parsed.messages) == 1
    assert parsed.messages[0].type is MessageType.text
    assert parsed.messages[0].contact_name == "Alice"


# ====================== webhook: GET handshake ======================


def test_webhook_get_echoes_challenge(client: CsrfAwareClient, wa_config):
    r = client.get(
        "/api/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": _VERIFY_TOKEN,
            "hub.challenge": "1234567890",
        },
    )
    assert r.status_code == 200
    assert r.text == "1234567890"


def test_webhook_get_wrong_token_403(client: CsrfAwareClient, wa_config):
    r = client.get(
        "/api/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "x"},
    )
    assert r.status_code == 403


# ====================== webhook: POST signature gate ======================


def test_webhook_post_bad_signature_403(client: CsrfAwareClient, wa_config):
    raw = json.dumps(_inbound_payload()).encode()
    r = client.post(
        "/api/whatsapp/webhook",
        content=raw,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
    )
    assert r.status_code == 403


def test_webhook_post_unconfigured_secret_503(client: CsrfAwareClient):
    s = get_settings()
    orig = s.whatsapp_app_secret
    s.whatsapp_app_secret = ""
    try:
        raw = json.dumps(_inbound_payload()).encode()
        r = client.post(
            "/api/whatsapp/webhook",
            content=raw,
            headers={"X-Hub-Signature-256": "sha256=x", "Content-Type": "application/json"},
        )
        assert r.status_code == 503
    finally:
        s.whatsapp_app_secret = orig


# ====================== webhook: inbound persistence ======================


def test_inbound_message_persists(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config
):
    _make_account(db, test_org)
    r = _post_webhook(client, _inbound_payload(wamid="wamid.in.1", body="primeiro"))
    assert r.status_code == 200

    msg = db.execute(select(Message).where(Message.wa_message_id == "wamid.in.1")).scalar_one()
    assert msg.direction is MessageDirection.inbound
    assert msg.status is MessageStatus.received
    assert msg.body == "primeiro"

    conv = db.get(Conversation, msg.conversation_id)
    assert conv.organization_id == test_org.id
    assert conv.unread_count == 1
    assert conv.last_message_preview == "primeiro"
    assert conv.contact_name == "Alice"


def test_inbound_replay_is_deduped(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config
):
    _make_account(db, test_org)
    payload = _inbound_payload(wamid="wamid.dup.1", body="once")
    assert _post_webhook(client, payload).status_code == 200
    assert _post_webhook(client, payload).status_code == 200  # Meta redelivery

    rows = db.execute(select(Message).where(Message.wa_message_id == "wamid.dup.1")).scalars().all()
    assert len(rows) == 1
    conv = db.get(Conversation, rows[0].conversation_id)
    assert conv.unread_count == 1  # not double-counted


def test_inbound_unknown_number_ignored(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config
):
    _make_account(db, test_org)  # different pnid than the payload below
    r = _post_webhook(client, _inbound_payload(pnid="pnid-not-connected", wamid="wamid.x"))
    assert r.status_code == 200  # ack so Meta stops retrying
    assert (
        db.execute(select(Message).where(Message.wa_message_id == "wamid.x")).scalar_one_or_none()
        is None
    )


# ====================== webhook: status progression ======================


def test_status_advances_outbound(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    out = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.out.1",
        direction=MessageDirection.outbound,
        type=MessageType.text,
        body="sent already",
        status=MessageStatus.sent,
    )
    db.add(out)
    db.commit()

    assert _post_webhook(client, _status_payload("wamid.out.1", "delivered")).status_code == 200
    db.refresh(out)
    assert out.status is MessageStatus.delivered

    assert _post_webhook(client, _status_payload("wamid.out.1", "read")).status_code == 200
    db.refresh(out)
    assert out.status is MessageStatus.read

    # Out-of-order 'delivered' must NOT regress a 'read'.
    assert _post_webhook(client, _status_payload("wamid.out.1", "delivered")).status_code == 200
    db.refresh(out)
    assert out.status is MessageStatus.read


# ====================== accounts API (RBAC + uniqueness) ======================


def test_admin_connects_account_token_never_echoed(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    r = admin_client.post(
        "/api/whatsapp/accounts",
        json={
            "phone_number_id": _PNID,
            "access_token": "super-secret-token",
            "display_phone_number": "+55 11 98888-7777",
            "verified_name": "Pytest Store",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["phone_number_id"] == _PNID
    assert "access_token" not in body  # write-only

    # Token is stored encrypted, not in cleartext.
    acct = db.execute(
        select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == _PNID)
    ).scalar_one()
    assert acct.access_token == "super-secret-token"  # decrypts transparently
    # Read the underlying column with raw SQL so the EncryptedSecret type
    # decorator doesn't decrypt it — proves the value is ciphertext at rest.
    raw = db.execute(
        text("SELECT access_token FROM whatsapp_accounts WHERE id = :id"),
        {"id": acct.id},
    ).scalar_one()
    assert raw != "super-secret-token"  # ciphertext at rest


def test_non_admin_cannot_connect(other_client: CsrfAwareClient):
    r = other_client.post(
        "/api/whatsapp/accounts",
        json={"phone_number_id": _PNID, "access_token": "x"},
    )
    assert r.status_code == 403


def test_connect_duplicate_number_other_org_409(
    admin_client: CsrfAwareClient, db: Session, other_org: Organization
):
    # Another org already owns this number.
    _make_account(db, other_org, phone_number_id="pnid-taken")
    r = admin_client.post(
        "/api/whatsapp/accounts",
        json={"phone_number_id": "pnid-taken", "access_token": "x"},
    )
    assert r.status_code == 409


def test_reconnect_same_org_rotates_token(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    _make_account(db, test_org, phone_number_id=_PNID)
    r = admin_client.post(
        "/api/whatsapp/accounts",
        json={"phone_number_id": _PNID, "access_token": "rotated-token"},
    )
    assert r.status_code == 201
    rows = (
        db.execute(select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == _PNID))
        .scalars()
        .all()
    )
    assert len(rows) == 1  # rotated in place, not duplicated
    db.refresh(rows[0])
    assert rows[0].access_token == "rotated-token"


# ====================== conversations: listing + isolation ======================


def test_list_conversations_scoped_to_org(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    _make_conversation(db, test_org, acct, contact_wa_id="5511900000001")
    r = admin_client.get("/api/whatsapp/conversations")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["contact_wa_id"] == "5511900000001"


def test_foreign_org_cannot_read_conversation(
    client: CsrfAwareClient, db: Session, test_org: Organization, foreign_user: User
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    client.post(
        "/api/auth/login",
        data={"username": foreign_user.email, "password": TEST_PASSWORD},
    )
    r = client.get(f"/api/whatsapp/conversations/{conv.id}")
    assert r.status_code == 404  # RLS hides the foreign row


# ====================== conversations: link / unlink ======================


def test_link_conversation_to_lead_and_customer(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    lead = _make_lead(db, test_org)
    cust = _make_customer(db, test_org)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/link",
        json={"lead_id": str(lead.id), "customer_id": str(cust.id)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lead_id"] == str(lead.id)
    assert body["customer_id"] == str(cust.id)

    db.refresh(conv)
    assert conv.lead_id == lead.id
    assert conv.customer_id == cust.id


def test_link_unknown_lead_404(admin_client: CsrfAwareClient, db: Session, test_org: Organization):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/link",
        json={"lead_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 404


def test_link_foreign_org_record_404(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, other_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    foreign_lead = _make_lead(db, other_org)  # belongs to another tenant
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/link",
        json={"lead_id": str(foreign_lead.id)},
    )
    assert r.status_code == 404  # RLS hides the foreign lead → looks absent
    db.refresh(conv)
    assert conv.lead_id is None  # nothing was attached


def test_unlink_explicit_null_clears_only_that_field(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    lead = _make_lead(db, test_org)
    cust = _make_customer(db, test_org)
    conv.lead_id = lead.id
    conv.customer_id = cust.id
    db.commit()

    # Explicit null clears the lead; customer omitted ⇒ left untouched.
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/link",
        json={"lead_id": None},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lead_id"] is None
    assert body["customer_id"] == str(cust.id)

    db.refresh(conv)
    assert conv.lead_id is None
    assert conv.customer_id == cust.id


def test_link_empty_body_is_noop(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    lead = _make_lead(db, test_org)
    conv.lead_id = lead.id
    db.commit()

    # No fields provided ⇒ existing link must survive.
    r = admin_client.post(f"/api/whatsapp/conversations/{conv.id}/link", json={})
    assert r.status_code == 200, r.text
    assert r.json()["lead_id"] == str(lead.id)
    db.refresh(conv)
    assert conv.lead_id == lead.id


# ============== conversations: convert → lead / customer ==============


def test_convert_conversation_to_lead(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)  # name "Pytest Contact", wa 5511988887777

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/convert",
        json={"target": "lead"},
    )
    assert r.status_code == 201, r.text
    lead_id = r.json()["lead_id"]
    assert lead_id is not None

    lead = db.get(Lead, uuid.UUID(lead_id))
    assert lead is not None
    assert lead.organization_id == test_org.id
    assert lead.first_name == "Pytest"
    assert lead.last_name == "Contact"
    assert lead.phone == "+5511988887777"
    assert lead.source == "whatsapp"

    db.refresh(conv)
    assert conv.lead_id == lead.id


def test_convert_conversation_to_customer(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/convert",
        json={"target": "customer"},
    )
    assert r.status_code == 201, r.text
    cust_id = r.json()["customer_id"]
    assert cust_id is not None

    cust = db.get(Customer, uuid.UUID(cust_id))
    assert cust is not None
    assert cust.phone == "+5511988887777"
    assert cust.first_name == "Pytest"

    db.refresh(conv)
    assert conv.customer_id == cust.id


def test_convert_honours_name_override(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/convert",
        json={"target": "lead", "first_name": "Ada", "last_name": "Lovelace"},
    )
    assert r.status_code == 201, r.text
    lead = db.get(Lead, uuid.UUID(r.json()["lead_id"]))
    assert lead.first_name == "Ada"
    assert lead.last_name == "Lovelace"


def test_convert_already_linked_lead_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    existing = _make_lead(db, test_org)
    conv.lead_id = existing.id
    db.commit()

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/convert",
        json={"target": "lead"},
    )
    assert r.status_code == 409  # already linked ⇒ refuse to fork a dupe
    db.refresh(conv)
    assert conv.lead_id == existing.id  # untouched


def test_convert_unknown_conversation_404(admin_client: CsrfAwareClient, db: Session):
    r = admin_client.post(
        "/api/whatsapp/conversations/00000000-0000-0000-0000-000000000000/convert",
        json={"target": "lead"},
    )
    assert r.status_code == 404


# ====================== outbound send (enqueue path) ======================


def test_send_message_persists_pending_and_enqueues(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    monkeypatch,
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)

    calls: list = []

    async def fake_enqueue(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages",
        json={"body": "resposta do agente"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["direction"] == "outbound"
    assert body["status"] == "pending"
    assert body["wa_message_id"] is None

    # Job was queued with the message id + a dedupe key.
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "send_whatsapp_message"
    assert args[1] == body["id"]
    assert kwargs["dedupe_key"] == f"wa_send:{body['id']}"


def test_send_message_inactive_account_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org, status=WhatsAppAccountStatus.disabled)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages",
        json={"body": "should fail"},
    )
    assert r.status_code == 409
