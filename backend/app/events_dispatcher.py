"""Outbox dispatcher — consumer side of ADR-007.

The worker's `drain_outbox` periodic job claims rows with
`FOR UPDATE SKIP LOCKED`, calls `dispatch_event` once per row, and
marks `processed_at = now()` on success. Failures bump
`attempt_count` and store `last_error` for ops visibility.

Subscriber registration is in-process: a module-level dict mapping
`EventType` → list of async callables. The webhook outgoing fanout
(2026-06-01 evening) is registered as a wildcard handler — see
`_fanout_to_webhooks` below.

Idempotency contract: subscribers MUST be safe to invoke twice with
the same `(event_id, payload)` because retry is at-least-once. The
dispatcher does NOT dedupe — it can't tell whether a subscriber's
side-effect (HTTP POST, DB write, queue push) succeeded after a
crash mid-way.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.events import EventType

log = structlog.get_logger(__name__)

# A handler receives the raw event row (id + event_type + decoded
# payload + organization_id). Return value is ignored. Raising
# triggers retry on this row only — other subscribers for the same
# event already ran or will run on the next sweep depending on
# ordering (see dispatch_event).
Handler = Callable[["EventContext"], Awaitable[None]]


class EventContext:
    """Decoded view of one outbox row passed to handlers. Plain
    object (not a Pydantic model) — handlers are trusted code in our
    own process, no need for parsing overhead."""

    __slots__ = ("event_id", "event_type", "organization_id", "payload", "occurred_at")

    def __init__(
        self,
        *,
        event_id: uuid.UUID,
        event_type: str,
        organization_id: uuid.UUID | None,
        payload: dict[str, Any] | None,
        occurred_at: Any,
    ) -> None:
        self.event_id = event_id
        self.event_type = event_type
        self.organization_id = organization_id
        self.payload = payload or {}
        self.occurred_at = occurred_at


_SUBSCRIBERS: dict[EventType, list[Handler]] = {}


def subscribe(event_type: EventType) -> Callable[[Handler], Handler]:
    """Decorator: register a handler for an event type.

    >>> @subscribe(EventType.lead_created)
    ... async def my_handler(ctx: EventContext) -> None:
    ...     ...
    """

    def _register(fn: Handler) -> Handler:
        _SUBSCRIBERS.setdefault(event_type, []).append(fn)
        return fn

    return _register


async def dispatch_event(ctx: EventContext) -> None:
    """Invoke every subscriber for this event_type. If one raises,
    the OutboxEvent row gets `attempt_count += 1` and `last_error`
    set; other subscribers for the SAME row are skipped on this
    attempt (they'll retry on the next sweep). This is intentional:
    the row is the atomic retry unit, not the (row, subscriber)
    pair — keeping per-subscriber state would mean a second table
    and we don't have a webhook fan-out yet to justify it.
    """
    try:
        event_type = EventType(ctx.event_type)
    except ValueError:
        # Unknown event_type in the table — most likely a code
        # rollback dropped the EventType member but the row stayed.
        # Mark as a permanent error so the dispatcher doesn't loop.
        raise RuntimeError(f"Unknown event_type: {ctx.event_type!r}") from None

    handlers = _SUBSCRIBERS.get(event_type, [])
    if not handlers:
        # No handler registered: still a successful dispatch
        # (treat as "delivered nowhere on purpose"). Logged at debug
        # so ops can spot accidental drops.
        log.debug(
            "outbox.no_subscribers",
            event_id=str(ctx.event_id),
            event_type=ctx.event_type,
        )
        return

    for handler in handlers:
        await handler(ctx)


def _parse_payload(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("outbox.payload_invalid_json", error=str(e))
        return None


# -- v1 in-process subscribers ---------------------------------
# Logging-only handlers so the pipeline is provably end-to-end
# from day one. Webhook fan-out registers itself here when the next
# cluster lands.


@subscribe(EventType.lead_created)
async def _log_lead_created(ctx: EventContext) -> None:
    log.info(
        "event.lead_created",
        event_id=str(ctx.event_id),
        organization_id=str(ctx.organization_id) if ctx.organization_id else None,
        lead_id=ctx.payload.get("lead_id"),
    )


@subscribe(EventType.lead_stage_changed)
async def _log_lead_stage_changed(ctx: EventContext) -> None:
    log.info(
        "event.lead_stage_changed",
        event_id=str(ctx.event_id),
        organization_id=str(ctx.organization_id) if ctx.organization_id else None,
        lead_id=ctx.payload.get("lead_id"),
        from_stage=ctx.payload.get("from"),
        to_stage=ctx.payload.get("to"),
    )


@subscribe(EventType.deal_created)
async def _log_deal_created(ctx: EventContext) -> None:
    log.info(
        "event.deal_created",
        event_id=str(ctx.event_id),
        organization_id=str(ctx.organization_id) if ctx.organization_id else None,
        deal_id=ctx.payload.get("deal_id"),
    )


@subscribe(EventType.deal_stage_changed)
async def _log_deal_stage_changed(ctx: EventContext) -> None:
    log.info(
        "event.deal_stage_changed",
        event_id=str(ctx.event_id),
        organization_id=str(ctx.organization_id) if ctx.organization_id else None,
        deal_id=ctx.payload.get("deal_id"),
        from_stage=ctx.payload.get("from"),
        to_stage=ctx.payload.get("to"),
    )


@subscribe(EventType.deal_won)
async def _log_deal_won(ctx: EventContext) -> None:
    log.info(
        "event.deal_won",
        event_id=str(ctx.event_id),
        organization_id=str(ctx.organization_id) if ctx.organization_id else None,
        deal_id=ctx.payload.get("deal_id"),
        value=ctx.payload.get("value"),
    )


@subscribe(EventType.deal_lost)
async def _log_deal_lost(ctx: EventContext) -> None:
    log.info(
        "event.deal_lost",
        event_id=str(ctx.event_id),
        organization_id=str(ctx.organization_id) if ctx.organization_id else None,
        deal_id=ctx.payload.get("deal_id"),
    )


# -- Outgoing-webhook fanout ----------------------------------
# Registered against EVERY EventType. For each event, this looks
# up the org's `WebhookEndpoint` rows whose `enabled_events` matches
# the event_type (or is `["*"]`) and enqueues one `deliver_webhook`
# arq job per match. The arq job handles HTTP POST + retry + the
# per-delivery row.
#
# Imported lazily because both the worker (arq) and the API import
# this module on startup; if we eager-imported the arq queue helper
# here it would try to open a Redis pool at import time, before the
# worker's startup hook has run.


async def _fanout_to_webhooks(ctx: EventContext) -> None:
    """Enqueue one delivery job per matching webhook endpoint for
    this org. Platform events (organization_id IS NULL) currently
    DON'T fan out — that's a deliberate v1 choice; "platform-level
    webhooks" would need their own subscription model.
    """
    if ctx.organization_id is None:
        return

    # Imported here (not at module top) so the API process doesn't
    # pull in arq + redis just to import events_dispatcher.
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import WebhookEndpoint
    from app.worker.queue import enqueue

    async with SessionLocal() as db:
        result = await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.organization_id == ctx.organization_id,
                WebhookEndpoint.paused_at.is_(None),
            )
        )
        endpoints = result.scalars().all()

    if not endpoints:
        return

    for ep in endpoints:
        try:
            events = json.loads(ep.enabled_events)
        except json.JSONDecodeError:
            events = []
        if "*" not in events and ctx.event_type not in events:
            continue
        await enqueue(
            "deliver_webhook",
            str(ep.id),
            str(ctx.event_id),
            ctx.event_type,
            ctx.payload,
            ctx.organization_id and str(ctx.organization_id),
        )


for _et in EventType:
    subscribe(_et)(_fanout_to_webhooks)
