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
    ConversationStatus,
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
from app.whatsapp import (
    WhatsAppSendError,
    fetch_media,
    parse_webhook,
    send_media,
    send_template,
    verify_challenge,
    verify_signature,
)
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


def _inbound_media_payload(
    pnid: str = _PNID,
    *,
    sender: str = "5511988887777",
    wamid: str = "wamid.media.in.1",
    media_id: str = "MEDIAIN1",
    mtype: str = "image",
    caption: str = "foto",
) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": pnid},
                            "contacts": [{"wa_id": sender, "profile": {"name": "Alice"}}],
                            "messages": [
                                {
                                    "id": wamid,
                                    "from": sender,
                                    "type": mtype,
                                    "timestamp": "1700000000",
                                    mtype: {"id": media_id, "caption": caption},
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


# ============== conversations: status lifecycle ==============


def test_status_close_then_reopen(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/status", json={"status": "closed"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed"
    db.refresh(conv)
    assert conv.status is ConversationStatus.closed

    r = admin_client.post(f"/api/whatsapp/conversations/{conv.id}/status", json={"status": "open"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "open"


def test_status_archive(admin_client: CsrfAwareClient, db: Session, test_org: Organization):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/status", json={"status": "archived"}
    )
    assert r.status_code == 200, r.text
    db.refresh(conv)
    assert conv.status is ConversationStatus.archived


def test_status_invalid_value_422(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/status", json={"status": "banana"}
    )
    assert r.status_code == 422


def test_status_filter_excludes_other_statuses(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    open_conv = _make_conversation(db, test_org, acct, contact_wa_id="5511900000001")
    archived = _make_conversation(db, test_org, acct, contact_wa_id="5511900000002")
    archived.status = ConversationStatus.archived
    db.commit()

    r = admin_client.get("/api/whatsapp/conversations?status=archived")
    assert r.status_code == 200, r.text
    ids = {c["id"] for c in r.json()}
    assert str(archived.id) in ids
    assert str(open_conv.id) not in ids


def test_inbound_reopens_closed_conversation(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config
):
    acct = _make_account(db, test_org)  # pnid _PNID, matches the inbound payload
    conv = _make_conversation(db, test_org, acct)  # contact 5511988887777 (payload sender)
    conv.status = ConversationStatus.closed
    db.commit()

    r = _post_webhook(client, _inbound_payload(wamid="wamid.reopen.1", body="oi de novo"))
    assert r.status_code == 200

    db.refresh(conv)
    assert conv.status is ConversationStatus.open  # reply pulled it back in


def test_inbound_leaves_archived_filed(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    conv.status = ConversationStatus.archived
    db.commit()

    r = _post_webhook(client, _inbound_payload(wamid="wamid.archived.1", body="ainda aqui"))
    assert r.status_code == 200

    db.refresh(conv)
    assert conv.status is ConversationStatus.archived  # stays filed away


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


# ====================== outbound template send ======================


def test_send_template_builds_wire_payload(monkeypatch):
    """The transport layer must emit Meta's `type:template` shape, with the
    positional body params filling the template's variables in order."""
    captured: dict = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"messages": [{"id": "wamid.tmpl.1"}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Resp()

    monkeypatch.setattr("app.whatsapp.httpx.AsyncClient", _Client)

    import asyncio

    wamid = asyncio.run(
        send_template(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            template_name="welcome",
            language_code="pt_BR",
            body_params=["Ada", "10%"],
        )
    )
    assert wamid == "wamid.tmpl.1"
    p = captured["json"]
    assert p["type"] == "template"
    assert p["to"] == "5511988887777"
    assert p["template"]["name"] == "welcome"
    assert p["template"]["language"] == {"code": "pt_BR"}
    comp = p["template"]["components"][0]
    assert comp["type"] == "body"
    assert [x["text"] for x in comp["parameters"]] == ["Ada", "10%"]
    assert captured["headers"]["Authorization"] == "Bearer tok"


def test_send_template_no_params_omits_components(monkeypatch):
    """A variable-free template must NOT carry an (empty) components array —
    Meta rejects a body component with zero parameters."""
    captured: dict = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"messages": [{"id": "wamid.tmpl.2"}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json, headers):
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr("app.whatsapp.httpx.AsyncClient", _Client)

    import asyncio

    asyncio.run(
        send_template(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            template_name="ping",
            language_code="en_US",
        )
    )
    assert "components" not in captured["json"]["template"]


def test_send_template_persists_pending_and_enqueues(
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
        f"/api/whatsapp/conversations/{conv.id}/template",
        json={
            "template_name": "welcome",
            "language_code": "pt_BR",
            "body_params": ["Ada", "10%"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["direction"] == "outbound"
    assert body["status"] == "pending"
    assert body["type"] == "template"
    # Body is a human preview, not the wire payload.
    assert body["body"] == "[template: welcome] Ada · 10%"

    # The conversation's preview denorm tracks it too.
    db.refresh(conv)
    assert conv.last_message_preview == "[template: welcome] Ada · 10%"

    # Job queued with the template spec as the 3rd positional arg.
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "send_whatsapp_message"
    assert args[1] == body["id"]
    assert args[3] == {"name": "welcome", "language": "pt_BR", "params": ["Ada", "10%"]}
    assert kwargs["dedupe_key"] == f"wa_send:{body['id']}"


def test_send_template_inactive_account_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org, status=WhatsAppAccountStatus.disabled)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/template",
        json={"template_name": "welcome"},
    )
    assert r.status_code == 409


def test_send_template_missing_name_422(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/template",
        json={"template_name": ""},
    )
    assert r.status_code == 422


# ====================== outbound media send ======================


def _patch_httpx_capture(monkeypatch, *, wamid: str = "wamid.cap.1") -> dict:
    """Patch `app.whatsapp.httpx.AsyncClient` so a transport send records the
    posted body/headers instead of hitting the network, and returns a fake 200
    carrying `wamid`."""
    captured: dict = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"messages": [{"id": wamid}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Resp()

    monkeypatch.setattr("app.whatsapp.httpx.AsyncClient", _Client)
    return captured


def test_send_media_link_builds_payload(monkeypatch):
    captured = _patch_httpx_capture(monkeypatch, wamid="wamid.media.1")
    import asyncio

    wamid = asyncio.run(
        send_media(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            media_type="image",
            link="https://cdn.example/cat.jpg",
            caption="meu gato",
        )
    )
    assert wamid == "wamid.media.1"
    p = captured["json"]
    assert p["type"] == "image"
    assert p["image"] == {"link": "https://cdn.example/cat.jpg", "caption": "meu gato"}


def test_send_media_document_by_id_with_filename(monkeypatch):
    captured = _patch_httpx_capture(monkeypatch)
    import asyncio

    asyncio.run(
        send_media(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            media_type="document",
            media_id="MEDIA123",
            caption="contrato",
            filename="contrato.pdf",
        )
    )
    assert captured["json"]["document"] == {
        "id": "MEDIA123",
        "caption": "contrato",
        "filename": "contrato.pdf",
    }


def test_send_media_audio_omits_caption_and_filename(monkeypatch):
    """Audio carries neither caption nor filename — Meta rejects them on the
    wrong media kind, so the transport must drop them."""
    captured = _patch_httpx_capture(monkeypatch)
    import asyncio

    asyncio.run(
        send_media(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            media_type="audio",
            link="https://cdn.example/a.mp3",
            caption="ignored",
            filename="ignored.mp3",
        )
    )
    assert captured["json"]["audio"] == {"link": "https://cdn.example/a.mp3"}


def test_send_media_persists_pending_and_enqueues(
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
        f"/api/whatsapp/conversations/{conv.id}/media",
        json={
            "media_type": "image",
            "link": "https://cdn.example/cat.jpg",
            "caption": "meu gato",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["direction"] == "outbound"
    assert body["status"] == "pending"
    assert body["type"] == "image"
    assert body["body"] == "meu gato"
    assert body["media_url"] == "https://cdn.example/cat.jpg"

    db.refresh(conv)
    assert conv.last_message_preview == "meu gato"

    # Job queued with template slot None + the media spec as the 4th/5th args.
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "send_whatsapp_message"
    assert args[1] == body["id"]
    assert args[3] is None
    assert args[4] == {
        "media_type": "image",
        "link": "https://cdn.example/cat.jpg",
        "media_id": None,
        "caption": "meu gato",
        "filename": None,
    }
    assert kwargs["dedupe_key"] == f"wa_send:{body['id']}"


def test_send_media_no_caption_uses_bracket_preview(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, monkeypatch
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)

    async def fake_enqueue(*args, **kwargs):
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/media",
        json={"media_type": "document", "media_id": "MEDIA1"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["body"] is None
    db.refresh(conv)
    assert conv.last_message_preview == "[document]"


def test_send_media_both_sources_422(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/media",
        json={"media_type": "image", "link": "https://x/y.jpg", "media_id": "ID1"},
    )
    assert r.status_code == 422  # exactly-one-of guard


def test_send_media_neither_source_422(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/media",
        json={"media_type": "image"},
    )
    assert r.status_code == 422


def test_send_media_inactive_account_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org, status=WhatsAppAccountStatus.disabled)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/media",
        json={"media_type": "image", "link": "https://cdn.example/cat.jpg"},
    )
    assert r.status_code == 409


# ====================== inbound media mirroring ======================


def test_fetch_media_two_hop(monkeypatch):
    """Resolve the media id to a CDN url, then download the bytes — both hops
    carrying the bearer token."""
    calls: list = []

    class _Resp:
        def __init__(self, status_code, json_body=None, content=b""):
            self.status_code = status_code
            self._json = json_body
            self.content = content

        def json(self):
            return self._json

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers):
            calls.append((url, headers))
            if url.endswith("/MEDIA123"):
                return _Resp(200, {"url": "https://cdn.meta/blob", "mime_type": "image/jpeg"})
            return _Resp(200, content=b"\xff\xd8\xffbytes")

    monkeypatch.setattr("app.whatsapp.httpx.AsyncClient", _Client)

    import asyncio

    data, mime = asyncio.run(fetch_media("MEDIA123", "tok"))
    assert data == b"\xff\xd8\xffbytes"
    assert mime == "image/jpeg"
    assert calls[1][0] == "https://cdn.meta/blob"  # 2nd hop hits the CDN url
    assert all(h["Authorization"] == "Bearer tok" for _, h in calls)


def test_fetch_media_404_raises_terminal(monkeypatch):
    class _Resp:
        status_code = 404

        def json(self):
            return {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers):
            return _Resp()

    monkeypatch.setattr("app.whatsapp.httpx.AsyncClient", _Client)

    import asyncio

    with pytest.raises(WhatsAppSendError) as ei:
        asyncio.run(fetch_media("GONE", "tok"))
    assert ei.value.status_code == 404  # worker treats 4xx as terminal


def test_inbound_media_enqueues_mirror_job(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config, monkeypatch
):
    _make_account(db, test_org)

    calls: list = []

    async def fake_enqueue(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = _post_webhook(client, _inbound_media_payload(wamid="wamid.mediajob.1", media_id="MID9"))
    assert r.status_code == 200

    msg = db.execute(
        select(Message).where(Message.wa_message_id == "wamid.mediajob.1")
    ).scalar_one()
    assert msg.type is MessageType.image
    assert msg.media_id == "MID9"
    assert msg.media_storage_key is None  # worker hasn't run in this test

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "mirror_whatsapp_media"
    assert args[1] == "wamid.mediajob.1"
    assert args[2] == str(test_org.id)
    assert kwargs["dedupe_key"] == "wa_media:wamid.mediajob.1"


def test_inbound_text_enqueues_no_mirror(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config, monkeypatch
):
    _make_account(db, test_org)

    calls: list = []

    async def fake_enqueue(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = _post_webhook(client, _inbound_payload(wamid="wamid.textnojob.1"))
    assert r.status_code == 200
    assert calls == []  # a text message carries no media to mirror


def test_download_message_media_returns_presigned(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, monkeypatch
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    msg = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.dl.1",
        direction=MessageDirection.inbound,
        type=MessageType.image,
        status=MessageStatus.received,
        media_id="MID",
        media_storage_key=f"org-{test_org.id}/whatsapp-media/{conv.id}/abc",
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    async def fake_presign(key, filename=None):
        return f"https://s3.local/{key}?sig=abc"

    monkeypatch.setattr("app.api.whatsapp.presigned_download_url", fake_presign)

    r = admin_client.get(f"/api/whatsapp/conversations/{conv.id}/messages/{msg.id}/media")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith("https://s3.local/")
    assert body["expires_in"] > 0


def test_download_message_media_not_mirrored_404(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    msg = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.dl.2",
        direction=MessageDirection.inbound,
        type=MessageType.image,
        status=MessageStatus.received,
        media_id="MID",
        media_storage_key=None,  # not yet mirrored
    )
    db.add(msg)
    db.commit()

    r = admin_client.get(f"/api/whatsapp/conversations/{conv.id}/messages/{msg.id}/media")
    assert r.status_code == 404
