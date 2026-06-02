"""Outbox event helper — ADR-007.

`record_event` writes one row to `outbox_events` in the same session
as the caller. The caller's commit/rollback decides durability, so a
failed mutation never publishes a phantom event ("at-least-once
delivery, never-more-than-the-mutation-itself").

Subscribers (see `app.events_dispatcher`) consume the row out of band
via the worker's `drain_outbox` periodic job. This module is the
PRODUCER side; the worker holds the consumer side.

Convention: emit `record_event` AFTER `record_audit` / `record_activity`
inside the same transaction. The order doesn't affect correctness
(they all hit the same commit boundary) but keeps the audit ledger
written first if anything in the outbox path raises.
"""

from __future__ import annotations

import enum
import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent

# Max attempts before an outbox row is flagged as DLQ. The poller
# excludes rows at this cap from future claims; the admin /api/outbox
# endpoint surfaces them under `status=failed`. Kept here (not in
# worker.jobs) so the request path can read it without importing
# the worker module.
OUTBOX_MAX_ATTEMPTS = 10


class EventType(str, enum.Enum):
    """Curated event vocabulary published to the outbox.

    Naming: `{aggregate}.{verb_past}`. Past tense — events represent
    things that already happened. Subscribers fan out from here
    (webhooks, search indexing, automation rules); adding a new type
    only requires a member here + a handler registration in
    `app.events_dispatcher`.
    """

    # Lead lifecycle
    lead_created = "lead.created"
    lead_stage_changed = "lead.stage_changed"

    # Deal lifecycle (deal.won / deal.lost are the high-value
    # automation triggers — separate from deal.stage_changed so
    # subscribers can match the specific outcome without parsing the
    # payload).
    deal_created = "deal.created"
    deal_stage_changed = "deal.stage_changed"
    deal_won = "deal.won"
    deal_lost = "deal.lost"

    # Quote lifecycle (ADR-016). `quote.sent` is the customer-facing
    # trigger (e-mail/PDF delivery); accepted/declined are the
    # high-value outcome events, separate from a generic status_changed
    # so automation can match the outcome directly.
    quote_created = "quote.created"
    quote_sent = "quote.sent"
    quote_accepted = "quote.accepted"
    quote_declined = "quote.declined"


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):  # enum
        return value.value
    return value


async def record_event(
    db: AsyncSession,
    *,
    event_type: EventType,
    organization_id: uuid.UUID | None,
    payload: dict[str, Any] | None = None,
) -> OutboxEvent:
    """Append one row to the outbox. Same session as the caller; do
    NOT commit here.

    `organization_id` is nullable: platform-level events (auth flows,
    Stripe webhook fan-out) leave it None. Tenant-scoped events MUST
    pass it so subscribers can route per-org (e.g. only this org's
    webhook endpoints get the lead.created event).
    """
    serialised: str | None = None
    if payload is not None:
        sanitized = {k: _to_jsonable(v) for k, v in payload.items()}
        serialised = json.dumps(sanitized, default=str)

    row = OutboxEvent(
        organization_id=organization_id,
        event_type=event_type.value,
        payload=serialised,
    )
    db.add(row)
    await db.flush()
    return row
