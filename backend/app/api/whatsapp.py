"""WhatsApp Business Cloud API — webhook + tenant inbox.

Two routers share the `/api/whatsapp` prefix:

  * `webhook_router` — UNauthenticated. Meta calls these. The GET handshake
    echoes the challenge; the POST is the only path that lets an external
    caller mutate tenant data, gated by `X-Hub-Signature-256` HMAC over the
    raw body. It routes each event to a tenant by `phone_number_id` (a lookup
    on the NON-RLS `whatsapp_accounts` routing root), then sets the tenant GUC
    and persists under RLS — mirroring the Stripe webhook's "resolve org from
    the payload, then operate in-tenant" shape.

  * `router` — authenticated tenant surface: connect/manage numbers, list
    conversations + messages, send outbound text (via the worker).

`whatsapp_accounts` is NOT RLS'd (see the model docstring), so EVERY query in
the authenticated surface filters `organization_id` explicitly.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities import (
    ENTITY_CUSTOMER,
    ENTITY_LEAD,
    ActivityType,
    record_activity,
)
from app.audit import record_audit
from app.config import get_settings
from app.database import get_db, set_current_org_id
from app.deps import get_current_org_id, get_current_user, require_roles
from app.events import EventType, record_event
from app.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Lead,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    User,
    UserRole,
    WhatsAppAccount,
    WhatsAppAccountStatus,
)
from app.schemas import (
    ConversationConvert,
    ConversationLink,
    ConversationOut,
    ConversationStatusUpdate,
    MediaDownloadOut,
    MessageOut,
    SendMediaRequest,
    SendMessageRequest,
    SendTemplateRequest,
    WhatsAppAccountConnect,
    WhatsAppAccountOut,
    WhatsAppAccountUpdate,
)
from app.storage import presigned_download_url
from app.whatsapp import (
    SIGNATURE_HEADER,
    WhatsAppNotConfigured,
    parse_webhook,
    verify_challenge,
    verify_signature,
)
from app.whatsapp_inbox import apply_status, ingest_inbound, resolve_accounts

# Inbound message types whose bytes we mirror off Meta's short-lived CDN into
# our own S3 (text/location/contacts carry no media to copy).
_MIRRORABLE_TYPES = {
    MessageType.image,
    MessageType.document,
    MessageType.video,
    MessageType.audio,
    MessageType.sticker,
}

log = structlog.get_logger(__name__)

webhook_router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

# Connecting / disconnecting a number changes the org's messaging identity, so
# gate account mutations to admin. Reading + sending is any member's job.
manage = require_roles(UserRole.admin)


# ============================ Webhook (public) ============================
@webhook_router.get("/webhook")
async def verify_webhook(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Meta's one-time subscription handshake. Echo `hub.challenge` as
    plain text iff the verify token matches; otherwise 403."""
    if verify_challenge(hub_mode, hub_verify_token):
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="verification failed")


@webhook_router.post("/webhook")
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    signature: Annotated[str | None, Header(alias=SIGNATURE_HEADER)] = None,
) -> Response:
    """Inbound messages + delivery-status callbacks from Meta.

    Always returns 200 once the signature checks out — even when nothing
    matched a known number — so Meta stops retrying. A bad/absent signature is
    403; an unconfigured app secret is 503. We never trust the parsed JSON for
    auth: the HMAC is computed over the EXACT received bytes.
    """
    raw = await request.body()
    try:
        ok = verify_signature(raw, signature)
    except WhatsAppNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    if not ok:
        log.warning("whatsapp.webhook.bad_signature")
        raise HTTPException(status_code=403, detail="invalid signature")

    try:
        payload = await request.json()
    except Exception:
        # Signed but unparseable — ack so Meta doesn't hammer us; nothing to do.
        return Response(status_code=200)

    parsed = parse_webhook(payload)
    pnids = {m.phone_number_id for m in parsed.messages} | {
        s.phone_number_id for s in parsed.statuses
    }
    # Account lookup on the NON-RLS routing table — no tenant GUC. Commit to
    # close this transaction BEFORE setting a GUC, so the begin-event applies
    # the tenant scope to the (next) write transaction.
    accounts = await resolve_accounts(db, pnids)
    await db.commit()

    ingested = 0
    # (wa_message_id, org_id) for newly-stored media messages — enqueued AFTER
    # the per-message commit so the worker can't race ahead of a visible row.
    mirror_jobs: list[tuple[str, uuid.UUID]] = []
    for msg in parsed.messages:
        account = accounts.get(msg.phone_number_id)
        if account is None or account.status is WhatsAppAccountStatus.disabled:
            continue
        set_current_org_id(account.organization_id)
        if await ingest_inbound(db, account, msg):
            ingested += 1
            if msg.media_id and msg.type in _MIRRORABLE_TYPES:
                mirror_jobs.append((msg.wa_message_id, account.organization_id))
        await db.commit()

    if mirror_jobs:
        from app.worker.queue import enqueue

        for wamid, mirror_org in mirror_jobs:
            await enqueue(
                "mirror_whatsapp_media",
                wamid,
                str(mirror_org),
                dedupe_key=f"wa_media:{wamid}",
                dedupe_ttl_seconds=3600,
            )

    statuses_applied = 0
    for st in parsed.statuses:
        account = accounts.get(st.phone_number_id)
        if account is None:
            continue
        set_current_org_id(account.organization_id)
        if await apply_status(db, account, st):
            statuses_applied += 1
        await db.commit()

    if ingested or statuses_applied:
        log.info(
            "whatsapp.webhook.processed",
            messages=ingested,
            statuses=statuses_applied,
        )
    return Response(status_code=200)


# ===================== Accounts (authenticated, admin) =====================
def _account_out(a: WhatsAppAccount) -> WhatsAppAccountOut:
    return WhatsAppAccountOut.model_validate(a)


async def _get_account_or_404(
    db: AsyncSession, account_id: uuid.UUID, org_id: uuid.UUID
) -> WhatsAppAccount:
    a = (
        await db.execute(
            select(WhatsAppAccount).where(
                WhatsAppAccount.id == account_id,
                WhatsAppAccount.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="WhatsApp account not found")
    return a


@router.get("/accounts", response_model=list[WhatsAppAccountOut])
async def list_accounts(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[WhatsAppAccountOut]:
    rows = (
        (
            await db.execute(
                select(WhatsAppAccount)
                .where(WhatsAppAccount.organization_id == org_id)
                .order_by(WhatsAppAccount.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_account_out(a) for a in rows]


@router.post("/accounts", response_model=WhatsAppAccountOut, status_code=status.HTTP_201_CREATED)
async def connect_account(
    payload: WhatsAppAccountConnect,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> WhatsAppAccountOut:
    """Connect a WhatsApp number. `phone_number_id` is globally unique — if it
    already belongs to ANOTHER org, 409 (one number ↔ one tenant). If it
    already belongs to THIS org, the connect re-points the token (rotate)."""
    existing = (
        await db.execute(
            select(WhatsAppAccount).where(
                WhatsAppAccount.phone_number_id == payload.phone_number_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None and existing.organization_id != org_id:
        raise HTTPException(
            status_code=409, detail="This WhatsApp number is already connected to another account"
        )

    if existing is not None:
        existing.access_token = payload.access_token
        existing.waba_id = payload.waba_id or existing.waba_id
        existing.display_phone_number = (
            payload.display_phone_number or existing.display_phone_number
        )
        existing.verified_name = payload.verified_name or existing.verified_name
        existing.status = WhatsAppAccountStatus.active
        account = existing
        action = "whatsapp.account.reconnect"
    else:
        account = WhatsAppAccount(
            organization_id=org_id,
            phone_number_id=payload.phone_number_id,
            access_token=payload.access_token,
            waba_id=payload.waba_id,
            display_phone_number=payload.display_phone_number,
            verified_name=payload.verified_name,
            created_by_user_id=user.id,
        )
        db.add(account)
        action = "whatsapp.account.connect"

    await db.flush()
    await record_audit(
        db,
        actor=user,
        action=action,
        entity_type="whatsapp_account",
        entity_id=account.id,
        organization_id=org_id,
        metadata={"phone_number_id": account.phone_number_id},
    )
    await db.commit()
    await db.refresh(account)
    return _account_out(account)


@router.patch("/accounts/{account_id}", response_model=WhatsAppAccountOut)
async def update_account(
    account_id: uuid.UUID,
    payload: WhatsAppAccountUpdate,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> WhatsAppAccountOut:
    account = await _get_account_or_404(db, account_id, org_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(account, field, value)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="whatsapp.account.update",
        entity_type="whatsapp_account",
        entity_id=account.id,
        organization_id=org_id,
        metadata={"fields": [f for f in changes if f != "access_token"]},
    )
    await db.commit()
    await db.refresh(account)
    return _account_out(account)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_account(
    account_id: uuid.UUID,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    account = await _get_account_or_404(db, account_id, org_id)
    await record_audit(
        db,
        actor=user,
        action="whatsapp.account.disconnect",
        entity_type="whatsapp_account",
        entity_id=account.id,
        organization_id=org_id,
        metadata={"phone_number_id": account.phone_number_id},
    )
    await db.delete(account)
    await db.commit()


# ===================== Conversations + messages (members) =====================
async def _get_conversation_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, org_id: uuid.UUID
) -> Conversation:
    conv = (
        await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    conv_status: Annotated[ConversationStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.organization_id == org_id)
        .order_by(desc(Conversation.last_message_at), desc(Conversation.created_at))
        .limit(limit)
    )
    if conv_status is not None:
        stmt = stmt.where(Conversation.status == conv_status)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    return await _get_conversation_or_404(db, conversation_id, org_id)


@router.post("/conversations/{conversation_id}/read", response_model=ConversationOut)
async def mark_read(
    conversation_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    conv = await _get_conversation_or_404(db, conversation_id, org_id)
    conv.unread_count = 0
    await db.commit()
    await db.refresh(conv)
    return conv


@router.post("/conversations/{conversation_id}/status", response_model=ConversationOut)
async def set_conversation_status(
    conversation_id: uuid.UUID,
    payload: ConversationStatusUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    """Move a thread through its lifecycle (open / closed / archived). A no-op
    re-set of the current status still returns 200 (idempotent)."""
    conv = await _get_conversation_or_404(db, conversation_id, org_id)
    if conv.status is not payload.status:
        prev = conv.status
        conv.status = payload.status
        await record_audit(
            db,
            actor=user,
            action="whatsapp.conversation.status",
            entity_type="conversation",
            entity_id=conv.id,
            organization_id=org_id,
            metadata={"from": prev.value, "to": payload.status.value},
        )
    await db.commit()
    await db.refresh(conv)
    return conv


@router.post("/conversations/{conversation_id}/link", response_model=ConversationOut)
async def link_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationLink,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    """Attach the thread to a Lead and/or Customer — or detach it.

    A field that is omitted from the body is left untouched; a field sent as
    an explicit ``null`` clears that link. A non-null id is validated to belong
    to the caller's org (RLS hides a foreign row → 404) before being set. We use
    ``model_fields_set`` to tell "omitted" apart from "explicit null", since both
    deserialize to ``None``."""
    conv = await _get_conversation_or_404(db, conversation_id, org_id)
    provided = payload.model_fields_set
    if "lead_id" in provided:
        if payload.lead_id is not None:
            lead = (
                await db.execute(select(Lead.id).where(Lead.id == payload.lead_id))
            ).scalar_one_or_none()
            if lead is None:
                raise HTTPException(status_code=404, detail="Lead not found")
        conv.lead_id = payload.lead_id  # None ⇒ detach
    if "customer_id" in provided:
        if payload.customer_id is not None:
            cust = (
                await db.execute(select(Customer.id).where(Customer.id == payload.customer_id))
            ).scalar_one_or_none()
            if cust is None:
                raise HTTPException(status_code=404, detail="Customer not found")
        conv.customer_id = payload.customer_id  # None ⇒ detach
    await db.commit()
    await db.refresh(conv)
    return conv


def _derive_name(
    contact_name: str | None, wa_id: str, first: str | None, last: str | None
) -> tuple[str, str]:
    """Best-effort split of a WhatsApp profile name into first/last, honouring
    explicit overrides. Both columns are NOT NULL, so we never return blanks:
    the wa_id is the last-resort last name when nothing else is known."""
    if first or last:
        return (first or "WhatsApp").strip(), (last or "Contact").strip()
    parts = (contact_name or "").split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    if len(parts) == 1:
        return parts[0], wa_id
    return "WhatsApp", wa_id


@router.post(
    "/conversations/{conversation_id}/convert",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def convert_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationConvert,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    """Create a Lead or Customer from an inbound thread and link it.

    Seeds name from the contact's profile name and phone from their wa_id, then
    attaches the new record to this conversation. Refuses (409) if the thread is
    already linked to a record of that type, so a double-tap can't fork dupes."""
    conv = await _get_conversation_or_404(db, conversation_id, org_id)
    if payload.target == "lead" and conv.lead_id is not None:
        raise HTTPException(status_code=409, detail="Conversation already linked to a lead")
    if payload.target == "customer" and conv.customer_id is not None:
        raise HTTPException(status_code=409, detail="Conversation already linked to a customer")

    first, last = _derive_name(
        conv.contact_name, conv.contact_wa_id, payload.first_name, payload.last_name
    )
    phone = f"+{conv.contact_wa_id}"

    if payload.target == "lead":
        record = Lead(
            organization_id=org_id,
            first_name=first,
            last_name=last,
            phone=phone,
            source="whatsapp",
            owner_id=user.id,
        )
        db.add(record)
        await db.flush()
        conv.lead_id = record.id
        await record_audit(
            db,
            actor=user,
            action="lead.create",
            entity_type="lead",
            entity_id=record.id,
            organization_id=org_id,
            metadata={"source": "whatsapp", "conversation_id": str(conv.id)},
        )
        await record_activity(
            db,
            entity_type=ENTITY_LEAD,
            entity_id=record.id,
            activity_type=ActivityType.created,
            organization_id=org_id,
            actor=user,
            metadata={"source": "whatsapp"},
        )
        await record_event(
            db,
            event_type=EventType.lead_created,
            organization_id=org_id,
            payload={
                "lead_id": record.id,
                "owner_id": user.id,
                "stage": record.stage.value,
                "actor_user_id": user.id,
            },
        )
    else:
        record = Customer(
            organization_id=org_id,
            first_name=first,
            last_name=last,
            phone=phone,
            owner_id=user.id,
        )
        db.add(record)
        await db.flush()
        conv.customer_id = record.id
        await record_audit(
            db,
            actor=user,
            action="customer.create",
            entity_type="customer",
            entity_id=record.id,
            organization_id=org_id,
            metadata={"source": "whatsapp", "conversation_id": str(conv.id)},
        )
        await record_activity(
            db,
            entity_type=ENTITY_CUSTOMER,
            entity_id=record.id,
            activity_type=ActivityType.created,
            organization_id=org_id,
            actor=user,
        )

    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[Message]:
    # 404s for a foreign/missing conversation (no enumeration).
    await _get_conversation_or_404(db, conversation_id, org_id)
    rows = (
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.timestamp, Message.created_at)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@router.get(
    "/conversations/{conversation_id}/messages/{message_id}/media",
    response_model=MediaDownloadOut,
)
async def download_message_media(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> MediaDownloadOut:
    """Short-lived presigned URL for an inbound message's mirrored media. 404 if
    the message isn't in this conversation/org, or hasn't been mirrored yet (the
    `mirror_whatsapp_media` job hadn't landed)."""
    await _get_conversation_or_404(db, conversation_id, org_id)
    msg = (
        await db.execute(
            select(Message).where(
                Message.id == message_id,
                Message.conversation_id == conversation_id,
                Message.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if msg is None or not msg.media_storage_key:
        raise HTTPException(status_code=404, detail="No downloadable media for this message")
    url = await presigned_download_url(msg.media_storage_key)
    return MediaDownloadOut(url=url, expires_in=get_settings().s3_download_url_ttl)


async def _require_active_account(
    db: AsyncSession, conv: Conversation, org_id: uuid.UUID
) -> WhatsAppAccount:
    """The conversation's connected number must still be active to send.
    409 (not 404) — the thread exists, it's the channel that isn't sendable."""
    account = (
        await db.execute(
            select(WhatsAppAccount).where(
                WhatsAppAccount.id == conv.account_id,
                WhatsAppAccount.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if account is None or account.status is not WhatsAppAccountStatus.active:
        raise HTTPException(status_code=409, detail="WhatsApp number is not connected/active")
    return account


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Message:
    """Queue an outbound text. Persists a `pending` Message immediately (so the
    UI shows it optimistically) and hands the actual Graph API send to the
    worker, which stamps the `wamid` + advances the status. The connected
    account must be active."""
    conv = await _get_conversation_or_404(db, conversation_id, org_id)
    await _require_active_account(db, conv, org_id)

    msg = Message(
        organization_id=org_id,
        conversation_id=conv.id,
        direction=MessageDirection.outbound,
        type=MessageType.text,
        body=payload.body,
        status=MessageStatus.pending,
        sender_user_id=user.id,
    )
    db.add(msg)
    conv.last_message_at = msg.timestamp
    conv.last_message_preview = payload.body[:255]
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="whatsapp.message.send",
        entity_type="conversation",
        entity_id=conv.id,
        organization_id=org_id,
        metadata={"message_id": str(msg.id)},
    )
    await db.commit()
    await db.refresh(msg)

    from app.worker.queue import enqueue

    await enqueue(
        "send_whatsapp_message",
        str(msg.id),
        str(org_id),
        dedupe_key=f"wa_send:{msg.id}",
        dedupe_ttl_seconds=300,
    )
    return msg


def _template_preview(template_name: str, body_params: list[str]) -> str:
    """A human-readable stand-in for the message list — we don't render the
    template locally (Meta does), so show the name + the filled variables."""
    preview = f"[template: {template_name}]"
    if body_params:
        preview += " " + " · ".join(body_params)
    return preview[:255]


@router.post(
    "/conversations/{conversation_id}/template",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_template_message(
    conversation_id: uuid.UUID,
    payload: SendTemplateRequest,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Message:
    """Queue a pre-approved template send — the way to (re)open a conversation
    outside the 24h window. Persists a `pending` Message (type=template, body =
    a preview of the filled template) and hands the Graph API send to the
    worker. The connected account must be active."""
    conv = await _get_conversation_or_404(db, conversation_id, org_id)
    await _require_active_account(db, conv, org_id)

    preview = _template_preview(payload.template_name, payload.body_params)
    msg = Message(
        organization_id=org_id,
        conversation_id=conv.id,
        direction=MessageDirection.outbound,
        type=MessageType.template,
        body=preview,
        status=MessageStatus.pending,
        sender_user_id=user.id,
    )
    db.add(msg)
    conv.last_message_at = msg.timestamp
    conv.last_message_preview = preview
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="whatsapp.message.send_template",
        entity_type="conversation",
        entity_id=conv.id,
        organization_id=org_id,
        metadata={
            "message_id": str(msg.id),
            "template": payload.template_name,
            "language": payload.language_code,
        },
    )
    await db.commit()
    await db.refresh(msg)

    from app.worker.queue import enqueue

    await enqueue(
        "send_whatsapp_message",
        str(msg.id),
        str(org_id),
        {
            "name": payload.template_name,
            "language": payload.language_code,
            "params": payload.body_params,
        },
        dedupe_key=f"wa_send:{msg.id}",
        dedupe_ttl_seconds=300,
    )
    return msg


_MEDIA_TYPE_MAP = {
    "image": MessageType.image,
    "document": MessageType.document,
    "video": MessageType.video,
    "audio": MessageType.audio,
}


@router.post(
    "/conversations/{conversation_id}/media",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_media_message(
    conversation_id: uuid.UUID,
    payload: SendMediaRequest,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Message:
    """Queue an outbound media message (image/document/video/audio) sourced by a
    public URL or a Meta media id. Persists a `pending` Message of the matching
    type — `media_url`/`media_id` recording the source, `body` the caption — and
    hands the Graph API send to the worker. The connected account must be
    active."""
    conv = await _get_conversation_or_404(db, conversation_id, org_id)
    await _require_active_account(db, conv, org_id)

    preview = (payload.caption or f"[{payload.media_type}]")[:255]
    msg = Message(
        organization_id=org_id,
        conversation_id=conv.id,
        direction=MessageDirection.outbound,
        type=_MEDIA_TYPE_MAP[payload.media_type],
        body=payload.caption,
        media_id=payload.media_id,
        media_url=payload.link,
        status=MessageStatus.pending,
        sender_user_id=user.id,
    )
    db.add(msg)
    conv.last_message_at = msg.timestamp
    conv.last_message_preview = preview
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="whatsapp.message.send_media",
        entity_type="conversation",
        entity_id=conv.id,
        organization_id=org_id,
        metadata={"message_id": str(msg.id), "media_type": payload.media_type},
    )
    await db.commit()
    await db.refresh(msg)

    from app.worker.queue import enqueue

    await enqueue(
        "send_whatsapp_message",
        str(msg.id),
        str(org_id),
        None,
        {
            "media_type": payload.media_type,
            "link": payload.link,
            "media_id": payload.media_id,
            "caption": payload.caption,
            "filename": payload.filename,
        },
        dedupe_key=f"wa_send:{msg.id}",
        dedupe_ttl_seconds=300,
    )
    return msg
