"""Notification helper — `notify()` mirrors the pattern of
`record_audit` / `record_activity`. Same-session insert so the
caller's commit decides durability: a failed lead update never
emits a phantom "stage changed" bell.

Email fanout is a follow-up — for v1 we deliver in-app only. When
the worker (`app/workers/`) lands, it'll subscribe to the
`notification.created` outbox event and dispatch SMTP from there.
"""

from __future__ import annotations

import enum
import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, User


class NotificationType(str, enum.Enum):
    """Curated event vocabulary the bell UI knows how to render.
    Adding a type = member here + a translation in the frontend
    `notifications.*` namespace. No schema migration — the column
    is a free-form string."""

    task_assigned = "task_assigned"
    lead_stage_changed = "lead_stage_changed"
    deal_stage_changed = "deal_stage_changed"
    deal_won = "deal_won"
    deal_lost = "deal_lost"
    note_mention = "note_mention"  # reserved for @-mention v2
    file_attached = "file_attached"
    automation = "automation"  # raised by an automation rule (app.automations)
    conversation_assigned = "conversation_assigned"  # WhatsApp/omnichannel inbox


async def notify(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    notification_type: NotificationType,
    title: str,
    body: str | None = None,
    link_url: str | None = None,
    actor: User | None = None,
    metadata: dict[str, Any] | None = None,
) -> Notification:
    """Insert one notification row. Safe to call even when the
    recipient is the same as the actor — callers MUST de-dupe
    (don't notify yourself about your own action; the bell would
    be spammy). The convention is checked by every call site; this
    function does not enforce it because a future "notify on your
    own deal won" might intentionally want self-targeted bells.

    `link_url` is a locale-LESS relative path (e.g.
    `/leads/<uuid>`). The frontend prepends the current locale
    segment.
    """
    row = Notification(
        user_id=user_id,
        organization_id=organization_id,
        actor_user_id=actor.id if actor else None,
        type=notification_type.value,
        title=title,
        body=body,
        link_url=link_url,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(row)
    await db.flush()
    return row
