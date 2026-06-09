"""Inbound-message persistence for the WhatsApp webhook.

Separated from the pure transport layer (`app.whatsapp`) and the HTTP layer
(`app.api.whatsapp`) so the "turn a parsed Meta event into Conversation +
Message rows" logic is unit-testable on its own.

RLS contract: `resolve_accounts` reads the NON-RLS `whatsapp_accounts` routing
table (no tenant GUC needed). Every other function here writes RLS'd tenant
tables and assumes the caller has ALREADY called
`set_current_org_id(account.organization_id)` for the account being processed.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Conversation,
    ConversationChannel,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
    WhatsAppAccount,
)
from app.whatsapp import InboundMessage, StatusUpdate

log = structlog.get_logger(__name__)

_PREVIEW_MAX = 255


async def resolve_accounts(
    db: AsyncSession, phone_number_ids: set[str]
) -> dict[str, WhatsAppAccount]:
    """Map each `phone_number_id` to its connected account. Reads the non-RLS
    routing root, so NO tenant GUC is required (and must not be relied on —
    the payload's org is unknown until this lookup resolves it)."""
    if not phone_number_ids:
        return {}
    rows = (
        (
            await db.execute(
                select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id.in_(phone_number_ids))
            )
        )
        .scalars()
        .all()
    )
    return {a.phone_number_id: a for a in rows}


async def _get_or_create_conversation(
    db: AsyncSession, account: WhatsAppAccount, contact_wa_id: str, contact_name: str | None
) -> Conversation:
    conv = (
        await db.execute(
            select(Conversation).where(
                Conversation.organization_id == account.organization_id,
                Conversation.account_id == account.id,
                Conversation.contact_wa_id == contact_wa_id,
            )
        )
    ).scalar_one_or_none()
    if conv is None:
        conv = Conversation(
            organization_id=account.organization_id,
            account_id=account.id,
            channel=ConversationChannel.whatsapp,
            contact_wa_id=contact_wa_id,
            contact_name=contact_name,
        )
        db.add(conv)
        await db.flush()
    elif contact_name and conv.contact_name != contact_name:
        # Keep the display name fresh as the contact updates their profile.
        conv.contact_name = contact_name
    return conv


async def ingest_inbound(db: AsyncSession, account: WhatsAppAccount, msg: InboundMessage) -> bool:
    """Persist one inbound message: upsert its conversation, insert the
    message (deduped by `wa_message_id`), bump the unread + preview denorms.

    Returns True if a NEW message row was written, False if it was a duplicate
    (a replayed webhook). Caller must have set the tenant GUC for
    `account.organization_id`.
    """
    existing = (
        await db.execute(select(Message.id).where(Message.wa_message_id == msg.wa_message_id))
    ).scalar_one_or_none()
    if existing is not None:
        return False

    conv = await _get_or_create_conversation(db, account, msg.contact_wa_id, msg.contact_name)

    row = Message(
        organization_id=account.organization_id,
        conversation_id=conv.id,
        wa_message_id=msg.wa_message_id,
        direction=MessageDirection.inbound,
        type=msg.type,
        body=msg.body,
        media_id=msg.media_id,
        status=MessageStatus.received,
        timestamp=msg.timestamp,
    )
    db.add(row)

    conv.last_message_at = msg.timestamp
    conv.last_message_preview = (msg.body or f"[{msg.type.value}]")[:_PREVIEW_MAX]
    conv.unread_count += 1
    # A reply on a resolved thread pulls it back into the inbox. An `archived`
    # thread was filed away deliberately, so it stays hidden until reopened.
    if conv.status is ConversationStatus.closed:
        conv.status = ConversationStatus.open
    await db.flush()
    return True


async def apply_status(db: AsyncSession, account: WhatsAppAccount, st: StatusUpdate) -> bool:
    """Advance an outbound message's delivery status from a Meta status
    callback. Returns True if a row was updated. Status only moves FORWARD
    (sent < delivered < read) so an out-of-order callback can't regress a
    'read' back to 'delivered'. A 'failed' always wins. Caller must have set
    the tenant GUC for `account.organization_id`."""
    msg = (
        await db.execute(select(Message).where(Message.wa_message_id == st.wa_message_id))
    ).scalar_one_or_none()
    if msg is None:
        # Status for a message we didn't originate (or haven't stored yet).
        return False

    if st.status is MessageStatus.failed:
        msg.status = MessageStatus.failed
        if st.error:
            msg.error = st.error
        await db.flush()
        return True

    if _rank(st.status) > _rank(msg.status):
        msg.status = st.status
        await db.flush()
        return True
    return False


# Monotonic ordering for outbound delivery progression. Anything not in the
# ladder (received/pending/failed) ranks 0 so a real delivery signal always
# advances a freshly-sent row.
_STATUS_RANK = {
    MessageStatus.sent: 1,
    MessageStatus.delivered: 2,
    MessageStatus.read: 3,
}


def _rank(status: MessageStatus) -> int:
    return _STATUS_RANK.get(status, 0)


async def link_conversation(
    db: AsyncSession,
    conv: Conversation,
    *,
    lead_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
) -> None:
    """Attach a conversation to a CRM record. Pass-through setter kept here so
    the link rule lives next to the model it mutates."""
    if lead_id is not None:
        conv.lead_id = lead_id
    if customer_id is not None:
        conv.customer_id = customer_id
    await db.flush()
