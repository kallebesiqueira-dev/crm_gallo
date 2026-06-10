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
from datetime import UTC, datetime, timedelta

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
    Notification,
    Organization,
    User,
    WhatsAppAccount,
    WhatsAppAccountStatus,
)
from app.whatsapp import (
    SERVICE_WINDOW,
    WhatsAppSendError,
    fetch_media,
    fetch_message_templates,
    mark_read,
    parse_template,
    parse_webhook,
    send_interactive,
    send_media,
    send_reaction,
    send_template,
    send_text,
    service_window_expires_at,
    service_window_open,
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
    waba_id: str | None = None,
) -> WhatsAppAccount:
    acct = WhatsAppAccount(
        organization_id=org.id,
        phone_number_id=phone_number_id,
        access_token="seed-access-token",
        status=status,
        waba_id=waba_id,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


# Sentinel: default a freshly-made conversation to an OPEN 24h service window
# (the contact just messaged) so the existing free-form-send tests keep working.
# Pass `last_inbound_at=None` to simulate a contact who never messaged, or a past
# datetime to simulate an expired window.
_WINDOW_OPEN = object()


def _make_conversation(
    db: Session,
    org: Organization,
    account: WhatsAppAccount,
    *,
    contact_wa_id: str = "5511988887777",
    last_inbound_at=_WINDOW_OPEN,
) -> Conversation:
    conv = Conversation(
        organization_id=org.id,
        account_id=account.id,
        channel=ConversationChannel.whatsapp,
        contact_wa_id=contact_wa_id,
        contact_name="Pytest Contact",
        last_inbound_at=(datetime.now(UTC) if last_inbound_at is _WINDOW_OPEN else last_inbound_at),
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


def test_send_text_with_context_quotes(monkeypatch):
    captured = _patch_httpx_capture(monkeypatch, wamid="wamid.quote.1")
    import asyncio

    wamid = asyncio.run(
        send_text(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            body="claro!",
            context_message_id="wamid.orig.1",
        )
    )
    assert wamid == "wamid.quote.1"
    assert captured["json"]["context"] == {"message_id": "wamid.orig.1"}


def test_send_text_without_context_omits_it(monkeypatch):
    captured = _patch_httpx_capture(monkeypatch)
    import asyncio

    asyncio.run(
        send_text(phone_number_id="PNID", access_token="tok", to="5511988887777", body="oi")
    )
    assert "context" not in captured["json"]


def test_send_message_reply_to_persists_context(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, monkeypatch
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    target = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.quote.target.1",
        direction=MessageDirection.inbound,
        type=MessageType.text,
        body="pergunta do cliente",
        status=MessageStatus.received,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    async def fake_enqueue(*args, **kwargs):
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages",
        json={"body": "resposta citada", "reply_to_message_id": str(target.id)},
    )
    assert r.status_code == 201, r.text
    assert r.json()["context_wa_message_id"] == "wamid.quote.target.1"


def test_send_message_reply_to_nonexistent_404(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages",
        json={"body": "oi", "reply_to_message_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


def test_send_message_reply_to_message_without_wamid_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    pending = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        direction=MessageDirection.outbound,
        type=MessageType.text,
        body="ainda pendente",
        status=MessageStatus.pending,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages",
        json={"body": "oi", "reply_to_message_id": str(pending.id)},
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


def test_send_media_with_context_quotes(monkeypatch):
    captured = _patch_httpx_capture(monkeypatch, wamid="wamid.media.quote.1")
    import asyncio

    asyncio.run(
        send_media(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            media_type="image",
            link="https://cdn.example/cat.jpg",
            context_message_id="wamid.orig.1",
        )
    )
    assert captured["json"]["context"] == {"message_id": "wamid.orig.1"}


def test_send_media_reply_to_persists_context(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, monkeypatch
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    target = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.media.quote.target.1",
        direction=MessageDirection.inbound,
        type=MessageType.text,
        body="manda a foto",
        status=MessageStatus.received,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    async def fake_enqueue(*args, **kwargs):
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/media",
        json={
            "media_type": "image",
            "link": "https://cdn.example/cat.jpg",
            "reply_to_message_id": str(target.id),
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["context_wa_message_id"] == "wamid.media.quote.target.1"


def test_send_interactive_reply_to_persists_context(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, monkeypatch
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    target = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.int.quote.target.1",
        direction=MessageDirection.inbound,
        type=MessageType.text,
        body="quais opções?",
        status=MessageStatus.received,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    async def fake_enqueue(*args, **kwargs):
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/interactive",
        json={
            "interactive_type": "button",
            "body_text": "Escolha:",
            "buttons": [{"id": "a", "title": "A"}],
            "reply_to_message_id": str(target.id),
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["context_wa_message_id"] == "wamid.int.quote.target.1"


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


# ---------- message templates ----------


def test_parse_template_extracts_body_and_var_count():
    raw = {
        "name": "order_update",
        "language": "pt_BR",
        "status": "APPROVED",
        "category": "UTILITY",
        "components": [
            {"type": "HEADER", "text": "Olá"},
            {"type": "BODY", "text": "Oi {{1}}, seu pedido {{2}} foi enviado."},
            {"type": "FOOTER", "text": "Obrigado"},
        ],
    }
    out = parse_template(raw)
    assert out == {
        "name": "order_update",
        "language": "pt_BR",
        "status": "APPROVED",
        "category": "UTILITY",
        "body_text": "Oi {{1}}, seu pedido {{2}} foi enviado.",
        "variable_count": 2,
    }


def test_parse_template_no_body_no_vars():
    out = parse_template(
        {"name": "ping", "language": "en", "status": "APPROVED", "category": "UTILITY"}
    )
    assert out["body_text"] == ""
    assert out["variable_count"] == 0


def _template_client(pages: list, calls: list):
    """Fake httpx.AsyncClient that replays `pages` (list of (status, json))
    one per GET, recording (url, params) into `calls`."""

    class _Resp:
        def __init__(self, status_code, json_body):
            self.status_code = status_code
            self._json = json_body
            self.content = json.dumps(json_body or {}).encode()

        def json(self):
            return self._json

    seq = iter(pages)

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            calls.append((url, params))
            status_code, body = next(seq)
            return _Resp(status_code, body)

    return _Client


def test_fetch_templates_single_page(monkeypatch):
    calls: list = []
    pages = [
        (200, {"data": [{"name": "a", "language": "en"}], "paging": {}}),
    ]
    monkeypatch.setattr("app.whatsapp.httpx.AsyncClient", _template_client(pages, calls))

    import asyncio

    out = asyncio.run(fetch_message_templates("WABA1", "tok"))
    assert [t["name"] for t in out] == ["a"]
    assert len(calls) == 1
    assert calls[0][0].endswith("/WABA1/message_templates")
    assert calls[0][1]["limit"] == 100  # first call carries query params


def test_fetch_templates_follows_pagination(monkeypatch):
    calls: list = []
    pages = [
        (200, {"data": [{"name": "a"}], "paging": {"next": "https://graph.meta/next?after=X"}}),
        (200, {"data": [{"name": "b"}], "paging": {}}),
    ]
    monkeypatch.setattr("app.whatsapp.httpx.AsyncClient", _template_client(pages, calls))

    import asyncio

    out = asyncio.run(fetch_message_templates("WABA1", "tok"))
    assert [t["name"] for t in out] == ["a", "b"]
    assert len(calls) == 2
    assert calls[1][0] == "https://graph.meta/next?after=X"
    assert calls[1][1] is None  # the `next` url already embeds cursor + fields


def test_fetch_templates_non_2xx_raises_with_meta_message(monkeypatch):
    calls: list = []
    pages = [(401, {"error": {"message": "Invalid OAuth access token"}})]
    monkeypatch.setattr("app.whatsapp.httpx.AsyncClient", _template_client(pages, calls))

    import asyncio

    with pytest.raises(WhatsAppSendError) as ei:
        asyncio.run(fetch_message_templates("WABA1", "tok"))
    assert ei.value.status_code == 401
    assert "Invalid OAuth access token" in str(ei.value)


def test_list_templates_endpoint_returns_parsed(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, monkeypatch
):
    acct = _make_account(db, test_org, waba_id="WABA-XYZ")

    async def fake_fetch(waba_id, access_token):
        assert waba_id == "WABA-XYZ"
        return [
            {
                "name": "welcome",
                "language": "pt_BR",
                "status": "APPROVED",
                "category": "MARKETING",
                "components": [{"type": "BODY", "text": "Bem-vindo {{1}}!"}],
            }
        ]

    monkeypatch.setattr("app.api.whatsapp.fetch_message_templates", fake_fetch)

    r = admin_client.get(f"/api/whatsapp/accounts/{acct.id}/templates")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == [
        {
            "name": "welcome",
            "language": "pt_BR",
            "status": "APPROVED",
            "category": "MARKETING",
            "body_text": "Bem-vindo {{1}}!",
            "variable_count": 1,
        }
    ]


def test_list_templates_no_waba_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)  # no waba_id
    r = admin_client.get(f"/api/whatsapp/accounts/{acct.id}/templates")
    assert r.status_code == 409


def test_list_templates_status_filter(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, monkeypatch
):
    acct = _make_account(db, test_org, waba_id="WABA-XYZ")

    async def fake_fetch(waba_id, access_token):
        return [
            {"name": "ok", "status": "APPROVED", "language": "en", "category": "UTILITY"},
            {"name": "pending", "status": "PENDING", "language": "en", "category": "UTILITY"},
        ]

    monkeypatch.setattr("app.api.whatsapp.fetch_message_templates", fake_fetch)

    r = admin_client.get(f"/api/whatsapp/accounts/{acct.id}/templates?status=approved")
    assert r.status_code == 200, r.text
    names = [t["name"] for t in r.json()]
    assert names == ["ok"]  # case-insensitive filter, PENDING dropped


def test_list_templates_meta_failure_502(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, monkeypatch
):
    acct = _make_account(db, test_org, waba_id="WABA-XYZ")

    async def boom(waba_id, access_token):
        raise WhatsAppSendError("HTTP 400: bad request", status_code=400)

    monkeypatch.setattr("app.api.whatsapp.fetch_message_templates", boom)

    r = admin_client.get(f"/api/whatsapp/accounts/{acct.id}/templates")
    assert r.status_code == 502


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


# ====================== interactive messages ======================


def _inbound_interactive_payload(
    pnid: str = _PNID,
    *,
    sender: str = "5511988887777",
    wamid: str = "wamid.int.in.1",
    reply_kind: str = "button_reply",
    reply_id: str = "OPT_YES",
    reply_title: str = "Sim",
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
                                    "type": "interactive",
                                    "timestamp": "1700000000",
                                    "interactive": {
                                        "type": reply_kind,
                                        reply_kind: {"id": reply_id, "title": reply_title},
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def test_send_interactive_buttons_builds_payload(monkeypatch):
    captured = _patch_httpx_capture(monkeypatch, wamid="wamid.int.1")
    import asyncio

    wamid = asyncio.run(
        send_interactive(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            interactive_type="button",
            body_text="Confirma?",
            buttons=[{"id": "yes", "title": "Sim"}, {"id": "no", "title": "Não"}],
            footer_text="Equipe Gallo",
        )
    )
    assert wamid == "wamid.int.1"
    p = captured["json"]
    assert p["type"] == "interactive"
    assert p["interactive"]["type"] == "button"
    assert p["interactive"]["body"] == {"text": "Confirma?"}
    assert p["interactive"]["footer"] == {"text": "Equipe Gallo"}
    assert p["interactive"]["action"]["buttons"] == [
        {"type": "reply", "reply": {"id": "yes", "title": "Sim"}},
        {"type": "reply", "reply": {"id": "no", "title": "Não"}},
    ]


def test_send_interactive_list_builds_payload(monkeypatch):
    captured = _patch_httpx_capture(monkeypatch)
    import asyncio

    asyncio.run(
        send_interactive(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            interactive_type="list",
            body_text="Escolha um plano",
            button_text="Ver planos",
            sections=[
                {
                    "title": "Mensais",
                    "rows": [
                        {"id": "std", "title": "Standard", "description": "9€/mês"},
                        {"id": "prm", "title": "Premium"},
                    ],
                }
            ],
        )
    )
    interactive = captured["json"]["interactive"]
    assert interactive["type"] == "list"
    assert interactive["action"]["button"] == "Ver planos"
    section = interactive["action"]["sections"][0]
    assert section["title"] == "Mensais"
    assert section["rows"] == [
        {"id": "std", "title": "Standard", "description": "9€/mês"},
        {"id": "prm", "title": "Premium"},
    ]


def test_send_interactive_buttons_persists_pending_and_enqueues(
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
        f"/api/whatsapp/conversations/{conv.id}/interactive",
        json={
            "interactive_type": "button",
            "body_text": "Confirma o horário?",
            "buttons": [
                {"id": "yes", "title": "Sim"},
                {"id": "no", "title": "Não"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["direction"] == "outbound"
    assert body["status"] == "pending"
    assert body["type"] == "interactive"
    assert body["body"] == "Confirma o horário? [Sim · Não]"

    db.refresh(conv)
    assert conv.last_message_preview == "Confirma o horário? [Sim · Não]"

    # Job queued with template + media slots None and the interactive spec 6th.
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "send_whatsapp_message"
    assert args[1] == body["id"]
    assert args[3] is None
    assert args[4] is None
    assert args[5] == {
        "interactive_type": "button",
        "body_text": "Confirma o horário?",
        "header_text": None,
        "footer_text": None,
        "buttons": [{"id": "yes", "title": "Sim"}, {"id": "no", "title": "Não"}],
        "button_text": None,
        "sections": None,
    }
    assert kwargs["dedupe_key"] == f"wa_send:{body['id']}"


def test_send_interactive_button_missing_buttons_422(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/interactive",
        json={"interactive_type": "button", "body_text": "oi"},
    )
    assert r.status_code == 422


def test_send_interactive_list_missing_sections_422(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/interactive",
        json={"interactive_type": "list", "body_text": "oi", "button_text": "Ver"},
    )
    assert r.status_code == 422


def test_send_interactive_duplicate_ids_422(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/interactive",
        json={
            "interactive_type": "button",
            "body_text": "oi",
            "buttons": [{"id": "x", "title": "A"}, {"id": "x", "title": "B"}],
        },
    )
    assert r.status_code == 422


def test_send_interactive_inactive_account_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org, status=WhatsAppAccountStatus.disabled)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/interactive",
        json={
            "interactive_type": "button",
            "body_text": "oi",
            "buttons": [{"id": "y", "title": "Sim"}],
        },
    )
    assert r.status_code == 409


def test_inbound_interactive_button_reply_parsed():
    parsed = parse_webhook(_inbound_interactive_payload(reply_title="Sim", reply_id="OPT_YES"))
    assert len(parsed.messages) == 1
    m = parsed.messages[0]
    assert m.type is MessageType.interactive
    assert m.body == "Sim"  # the tapped title threads as the message body


def test_inbound_interactive_list_reply_parsed():
    parsed = parse_webhook(
        _inbound_interactive_payload(
            reply_kind="list_reply", reply_id="std", reply_title="Standard"
        )
    )
    assert parsed.messages[0].type is MessageType.interactive
    assert parsed.messages[0].body == "Standard"


def test_inbound_interactive_persists_via_webhook(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config
):
    _make_account(db, test_org)
    r = _post_webhook(client, _inbound_interactive_payload(wamid="wamid.int.in.9"))
    assert r.status_code == 200
    msg = db.execute(select(Message).where(Message.wa_message_id == "wamid.int.in.9")).scalar_one()
    assert msg.type is MessageType.interactive
    assert msg.body == "Sim"
    assert msg.direction is MessageDirection.inbound


# ====================== reactions ======================


def _inbound_reaction_payload(
    pnid: str = _PNID,
    *,
    sender: str = "5511988887777",
    wamid: str = "wamid.react.in.1",
    target_wamid: str = "wamid.target.1",
    emoji: str = "👍",
) -> dict:
    reaction: dict = {"message_id": target_wamid}
    if emoji:
        reaction["emoji"] = emoji
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
                                    "type": "reaction",
                                    "timestamp": "1700000000",
                                    "reaction": reaction,
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def test_send_reaction_builds_payload(monkeypatch):
    captured = _patch_httpx_capture(monkeypatch, wamid="wamid.react.1")
    import asyncio

    wamid = asyncio.run(
        send_reaction(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            message_id="wamid.target.1",
            emoji="👍",
        )
    )
    assert wamid == "wamid.react.1"
    p = captured["json"]
    assert p["type"] == "reaction"
    assert p["reaction"] == {"message_id": "wamid.target.1", "emoji": "👍"}


def test_send_reaction_empty_emoji_removes(monkeypatch):
    captured = _patch_httpx_capture(monkeypatch)
    import asyncio

    asyncio.run(
        send_reaction(
            phone_number_id="PNID",
            access_token="tok",
            to="5511988887777",
            message_id="wamid.target.1",
            emoji="",
        )
    )
    assert captured["json"]["reaction"] == {"message_id": "wamid.target.1", "emoji": ""}


def test_react_endpoint_persists_pending_and_enqueues(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    monkeypatch,
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    target = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.target.endpoint.1",
        direction=MessageDirection.inbound,
        type=MessageType.text,
        body="olá",
        status=MessageStatus.received,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    calls: list = []

    async def fake_enqueue(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages/{target.id}/reaction",
        json={"emoji": "👍"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["direction"] == "outbound"
    assert body["status"] == "pending"
    assert body["type"] == "reaction"
    assert body["body"] == "👍"
    assert body["context_wa_message_id"] == "wamid.target.endpoint.1"

    db.refresh(conv)
    assert conv.last_message_preview == "👍"

    # template+media+interactive slots None; reaction spec 7th.
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "send_whatsapp_message"
    assert args[1] == body["id"]
    assert args[3] is None
    assert args[4] is None
    assert args[5] is None
    assert args[6] == {"message_id": "wamid.target.endpoint.1", "emoji": "👍"}
    assert kwargs["dedupe_key"] == f"wa_send:{body['id']}"


def test_react_to_message_without_wamid_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    pending = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        direction=MessageDirection.outbound,
        type=MessageType.text,
        body="still pending",
        status=MessageStatus.pending,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages/{pending.id}/reaction",
        json={"emoji": "👍"},
    )
    assert r.status_code == 409


def test_react_to_nonexistent_message_404(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages/{uuid.uuid4()}/reaction",
        json={"emoji": "👍"},
    )
    assert r.status_code == 404


def test_react_inactive_account_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org, status=WhatsAppAccountStatus.disabled)
    conv = _make_conversation(db, test_org, acct)
    target = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.target.inactive.1",
        direction=MessageDirection.inbound,
        type=MessageType.text,
        body="oi",
        status=MessageStatus.received,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages/{target.id}/reaction",
        json={"emoji": "👍"},
    )
    assert r.status_code == 409


def test_inbound_reaction_parsed():
    parsed = parse_webhook(_inbound_reaction_payload(emoji="❤️", target_wamid="wamid.orig.7"))
    assert len(parsed.messages) == 1
    m = parsed.messages[0]
    assert m.type is MessageType.reaction
    assert m.body == "❤️"
    assert m.context_wa_message_id == "wamid.orig.7"


def test_inbound_reaction_removed_has_empty_body():
    parsed = parse_webhook(_inbound_reaction_payload(emoji="", target_wamid="wamid.orig.8"))
    m = parsed.messages[0]
    assert m.type is MessageType.reaction
    assert not m.body
    assert m.context_wa_message_id == "wamid.orig.8"


def test_inbound_reaction_persists_via_webhook(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config
):
    _make_account(db, test_org)
    r = _post_webhook(
        client,
        _inbound_reaction_payload(
            wamid="wamid.react.in.9", target_wamid="wamid.orig.9", emoji="🔥"
        ),
    )
    assert r.status_code == 200
    msg = db.execute(
        select(Message).where(Message.wa_message_id == "wamid.react.in.9")
    ).scalar_one()
    assert msg.type is MessageType.reaction
    assert msg.body == "🔥"
    assert msg.context_wa_message_id == "wamid.orig.9"
    assert msg.direction is MessageDirection.inbound


# ---------- read receipts (blue ticks) ----------


def test_mark_read_builds_status_payload(monkeypatch):
    captured = _patch_httpx_capture(monkeypatch)
    import asyncio

    result = asyncio.run(
        mark_read(
            phone_number_id="PNID",
            access_token="tok",
            message_id="wamid.inbound.1",
        )
    )
    assert result is None
    assert captured["json"] == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.inbound.1",
    }
    assert "/PNID/messages" in captured["url"]


def test_read_endpoint_resets_unread_and_enqueues_latest_inbound(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    monkeypatch,
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    conv.unread_count = 3
    # Two inbound messages with wamids — the newest one should be marked read.
    older = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.in.old",
        direction=MessageDirection.inbound,
        type=MessageType.text,
        body="primeiro",
        status=MessageStatus.received,
    )
    db.add(older)
    db.commit()
    newer = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.in.new",
        direction=MessageDirection.inbound,
        type=MessageType.text,
        body="segundo",
        status=MessageStatus.received,
    )
    db.add(newer)
    db.commit()

    calls: list = []

    async def fake_enqueue(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = admin_client.post(f"/api/whatsapp/conversations/{conv.id}/read")
    assert r.status_code == 200, r.text
    assert r.json()["unread_count"] == 0

    db.refresh(conv)
    assert conv.unread_count == 0

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "mark_whatsapp_read"
    assert args[1] == "wamid.in.new"
    assert args[2] == str(test_org.id)
    assert kwargs["dedupe_key"] == "wa_read:wamid.in.new"


def test_read_endpoint_no_inbound_wamid_skips_enqueue(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    monkeypatch,
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    conv.unread_count = 2
    # Only an OUTBOUND message — nothing inbound to mark read.
    out = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.out.1",
        direction=MessageDirection.outbound,
        type=MessageType.text,
        body="oi",
        status=MessageStatus.sent,
    )
    db.add(out)
    db.commit()

    calls: list = []

    async def fake_enqueue(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = admin_client.post(f"/api/whatsapp/conversations/{conv.id}/read")
    assert r.status_code == 200, r.text
    assert r.json()["unread_count"] == 0

    db.refresh(conv)
    assert conv.unread_count == 0
    assert calls == []


# ---------- 24h customer-service window ----------


def test_service_window_open_helper():
    now = datetime.now(UTC)
    # Never messaged → no window.
    assert service_window_open(None) is False
    # Fresh inbound → open.
    assert service_window_open(now) is True
    # 23h ago → still open; 25h ago → closed.
    assert service_window_open(now - timedelta(hours=23)) is True
    assert service_window_open(now - timedelta(hours=25)) is False
    # Exactly at the boundary is closed (`now < expires` is strict).
    assert service_window_open(now - SERVICE_WINDOW, now=now) is False


def test_service_window_expires_at_helper():
    anchor = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    assert service_window_expires_at(anchor) == anchor + SERVICE_WINDOW
    assert service_window_expires_at(None) is None


def test_conversation_out_exposes_open_window(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)  # window open by default
    r = admin_client.get(f"/api/whatsapp/conversations/{conv.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service_window_open"] is True
    assert body["service_window_expires_at"] is not None
    assert body["last_inbound_at"] is not None


def test_conversation_out_exposes_closed_window(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    # Contact last messaged 30h ago → window closed.
    conv = _make_conversation(
        db, test_org, acct, last_inbound_at=datetime.now(UTC) - timedelta(hours=30)
    )
    r = admin_client.get(f"/api/whatsapp/conversations/{conv.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service_window_open"] is False
    assert body["service_window_expires_at"] is not None


def test_conversation_out_never_messaged_has_no_window(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct, last_inbound_at=None)
    r = admin_client.get(f"/api/whatsapp/conversations/{conv.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service_window_open"] is False
    assert body["service_window_expires_at"] is None
    assert body["last_inbound_at"] is None


def test_send_text_outside_window_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, monkeypatch
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(
        db, test_org, acct, last_inbound_at=datetime.now(UTC) - timedelta(hours=25)
    )

    calls: list = []

    async def fake_enqueue(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages",
        json={"body": "oi, tudo bem?"},
    )
    assert r.status_code == 409, r.text
    assert "service_window_closed" in r.json()["detail"]
    # Nothing persisted, nothing queued — the send was blocked up front.
    assert calls == []
    count = db.execute(select(Message).where(Message.conversation_id == conv.id)).scalars().all()
    assert count == []


def test_send_text_never_messaged_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct, last_inbound_at=None)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages",
        json={"body": "primeiro contato"},
    )
    assert r.status_code == 409
    assert "service_window_closed" in r.json()["detail"]


def test_send_media_outside_window_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct, last_inbound_at=None)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/media",
        json={"media_type": "image", "link": "https://cdn.example/cat.jpg"},
    )
    assert r.status_code == 409
    assert "service_window_closed" in r.json()["detail"]


def test_send_interactive_outside_window_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct, last_inbound_at=None)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/interactive",
        json={
            "interactive_type": "button",
            "body_text": "Escolha:",
            "buttons": [{"id": "sim", "title": "Sim"}],
        },
    )
    assert r.status_code == 409
    assert "service_window_closed" in r.json()["detail"]


def test_react_outside_window_409(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct, last_inbound_at=None)
    target = Message(
        organization_id=test_org.id,
        conversation_id=conv.id,
        wa_message_id="wamid.window.target.1",
        direction=MessageDirection.inbound,
        type=MessageType.text,
        body="oi",
        status=MessageStatus.received,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/messages/{target.id}/reaction",
        json={"emoji": "👍"},
    )
    assert r.status_code == 409
    assert "service_window_closed" in r.json()["detail"]


def test_send_template_allowed_outside_window(
    admin_client: CsrfAwareClient, db: Session, test_org: Organization, monkeypatch
):
    """Templates are the SANCTIONED way to re-open a closed conversation, so the
    window guard must NOT block them."""
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct, last_inbound_at=None)

    async def fake_enqueue(*args, **kwargs):
        return None

    monkeypatch.setattr("app.worker.queue.enqueue", fake_enqueue)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/template",
        json={"template_name": "welcome", "language_code": "pt_BR"},
    )
    assert r.status_code == 201, r.text


def test_inbound_message_anchors_service_window(
    client: CsrfAwareClient, db: Session, test_org: Organization, wa_config
):
    """The webhook stamps `last_inbound_at` from the inbound message timestamp —
    that's the anchor the 24h window is computed from. (The fixture uses a fixed
    2023 epoch, so we assert the anchor itself, not the live open/closed state.)"""
    _make_account(db, test_org)
    r = _post_webhook(client, _inbound_payload(wamid="wamid.window.in.1", body="oi"))
    assert r.status_code == 200
    msg = db.execute(
        select(Message).where(Message.wa_message_id == "wamid.window.in.1")
    ).scalar_one()
    conv = db.get(Conversation, msg.conversation_id)
    assert conv.last_inbound_at is not None
    assert conv.last_inbound_at == msg.timestamp


# ---------- conversation assignment (team inbox) ----------


def _notifications_for(db: Session, user_id) -> list[Notification]:
    return list(
        db.execute(select(Notification).where(Notification.user_id == user_id)).scalars().all()
    )


def test_assign_conversation_sets_owner_and_bells(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
    other_user: User,
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/assign",
        json={"assignee_id": str(other_user.id)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["assignee_id"] == str(other_user.id)

    db.refresh(conv)
    assert conv.assignee_id == other_user.id

    notes = _notifications_for(db, other_user.id)
    assert len(notes) == 1
    assert notes[0].type == "conversation_assigned"
    assert notes[0].actor_user_id == admin_user.id


def test_assign_to_self_does_not_bell(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/assign",
        json={"assignee_id": str(admin_user.id)},
    )
    assert r.status_code == 200, r.text
    db.refresh(conv)
    assert conv.assignee_id == admin_user.id
    # Claiming a thread for yourself must NOT self-bell.
    assert _notifications_for(db, admin_user.id) == []


def test_unassign_releases_to_queue(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    other_user: User,
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)
    conv.assignee_id = other_user.id
    db.commit()

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/assign",
        json={"assignee_id": None},
    )
    assert r.status_code == 200, r.text
    assert r.json()["assignee_id"] is None
    db.refresh(conv)
    assert conv.assignee_id is None


def test_assign_foreign_user_404(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    foreign_user: User,
):
    acct = _make_account(db, test_org)
    conv = _make_conversation(db, test_org, acct)

    r = admin_client.post(
        f"/api/whatsapp/conversations/{conv.id}/assign",
        json={"assignee_id": str(foreign_user.id)},
    )
    assert r.status_code == 404, r.text
    db.refresh(conv)
    assert conv.assignee_id is None  # unchanged — a foreign user can't own the thread


def test_list_conversations_filter_assignee_me(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    acct = _make_account(db, test_org)
    mine = _make_conversation(db, test_org, acct, contact_wa_id="5511900000001")
    other = _make_conversation(db, test_org, acct, contact_wa_id="5511900000002")
    mine.assignee_id = admin_user.id
    db.commit()

    r = admin_client.get("/api/whatsapp/conversations?assignee=me")
    assert r.status_code == 200, r.text
    ids = {c["id"] for c in r.json()}
    assert str(mine.id) in ids
    assert str(other.id) not in ids


def test_list_conversations_filter_unassigned(
    admin_client: CsrfAwareClient,
    db: Session,
    test_org: Organization,
    admin_user: User,
):
    acct = _make_account(db, test_org)
    mine = _make_conversation(db, test_org, acct, contact_wa_id="5511900000003")
    queued = _make_conversation(db, test_org, acct, contact_wa_id="5511900000004")
    mine.assignee_id = admin_user.id
    db.commit()

    r = admin_client.get("/api/whatsapp/conversations?assignee=unassigned")
    assert r.status_code == 200, r.text
    ids = {c["id"] for c in r.json()}
    assert str(queued.id) in ids
    assert str(mine.id) not in ids


def test_list_conversations_bad_assignee_422(admin_client: CsrfAwareClient):
    r = admin_client.get("/api/whatsapp/conversations?assignee=not-a-uuid")
    assert r.status_code == 422
