"""Outgoing webhooks CRUD — admin-only, per-org.

Endpoints are created here by an admin; the actual delivery happens
from `app.worker.jobs.deliver_webhook` after the outbox dispatcher's
fanout subscriber enqueues one job per (endpoint, event) pair.

Trust boundary notes:
  * `url` is stored as-is — receivers are the org's own infra. Block
    private RFC1918 ranges only as a "do not foot-gun" check; a
    determined admin can still point at a public reverse proxy.
  * `secret` is generated server-side via `app.webhook_sign`. Plaintext
    returned ONCE on create. After that it's only used internally by
    `deliver_webhook` to sign the body; never re-exposed via GET.
  * Endpoint update doesn't rotate the secret — that's a dedicated
    `POST /{id}/rotate-secret` (followup, not in v1) so the action
    can't happen accidentally inside a generic patch payload.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import uuid
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import get_current_org_id, get_current_user, require_roles
from app.events import EventType
from app.models import User, UserRole, WebhookDelivery, WebhookEndpoint
from app.schemas import (
    WebhookDeliveryOut,
    WebhookEndpointCreate,
    WebhookEndpointCreated,
    WebhookEndpointOut,
    WebhookEndpointUpdate,
)
from app.webhook_sign import generate_secret

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# Vocabulary the create endpoint accepts in `enabled_events`. "*" is
# the explicit wildcard meaning "every current and future EventType"
# — preferred over an empty list so the admin's intent is unambiguous.
_KNOWN_EVENT_SLUGS: set[str] = {e.value for e in EventType}
_WILDCARD = "*"


def _validate_event_slugs(events: list[str]) -> None:
    if not events:
        raise HTTPException(
            status_code=400,
            detail="enabled_events must be non-empty (use ['*'] for all events)",
        )
    for slug in events:
        if slug != _WILDCARD and slug not in _KNOWN_EVENT_SLUGS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown event type: {slug!r}",
            )


def _validate_url(url: str) -> None:
    """Reject obviously-unsafe targets so a misconfigured admin can't
    point at the loopback / internal infra by accident. This is a
    foot-gun guard, NOT a security boundary — anyone with admin can
    still aim at a public reverse proxy that fronts internal infra.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="url must use http(s)")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="url missing hostname")
    # Block plain `localhost` regardless of resolution.
    if parsed.hostname.lower() in ("localhost", "ip6-localhost"):
        raise HTTPException(status_code=400, detail="loopback URL not allowed")
    try:
        # gethostbyname returns ONE address even if A/AAAA records
        # diverge — DNS rebinding could still slip through; the
        # rebinding mitigation is "lock down receiver firewalls",
        # not this check.
        resolved = socket.gethostbyname(parsed.hostname)
        ip = ipaddress.ip_address(resolved)
        if ip.is_loopback or ip.is_private or ip.is_link_local:
            raise HTTPException(
                status_code=400, detail="private/loopback URL not allowed"
            )
    except (socket.gaierror, ValueError):
        # DNS doesn't resolve right now. We don't refuse the create —
        # the receiver might come online later. Delivery will just
        # fail until DNS recovers.
        pass


def _to_out(ep: WebhookEndpoint) -> WebhookEndpointOut:
    try:
        events = json.loads(ep.enabled_events)
    except json.JSONDecodeError:
        events = []
    return WebhookEndpointOut(
        id=ep.id,
        organization_id=ep.organization_id,
        url=ep.url,
        description=ep.description,
        enabled_events=events,
        paused_at=ep.paused_at,
        consecutive_failures=ep.consecutive_failures,
        last_success_at=ep.last_success_at,
        last_failure_at=ep.last_failure_at,
        created_at=ep.created_at,
    )


@router.get("", response_model=list[WebhookEndpointOut])
async def list_webhooks(
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[WebhookEndpointOut]:
    result = await db.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.organization_id == org_id)
        .order_by(desc(WebhookEndpoint.created_at))
    )
    return [_to_out(ep) for ep in result.scalars().all()]


@router.post(
    "",
    response_model=WebhookEndpointCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook(
    payload: WebhookEndpointCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointCreated:
    _validate_url(payload.url)
    _validate_event_slugs(payload.enabled_events)

    secret = generate_secret()
    ep = WebhookEndpoint(
        organization_id=org_id,
        url=payload.url,
        secret=secret,
        description=payload.description,
        enabled_events=json.dumps(payload.enabled_events),
        created_by_user_id=user.id,
    )
    db.add(ep)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="webhook.create",
        entity_type="webhook_endpoint",
        entity_id=ep.id,
        organization_id=org_id,
        metadata={"url": ep.url, "enabled_events": payload.enabled_events},
    )
    await db.commit()
    await db.refresh(ep)
    base = _to_out(ep)
    return WebhookEndpointCreated(**base.model_dump(), secret=secret)


async def _get_or_404(
    db: AsyncSession, webhook_id: uuid.UUID, org_id: uuid.UUID
) -> WebhookEndpoint:
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == webhook_id,
            WebhookEndpoint.organization_id == org_id,
        )
    )
    ep = result.scalar_one_or_none()
    if ep is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return ep


@router.get("/{webhook_id}", response_model=WebhookEndpointOut)
async def get_webhook(
    webhook_id: uuid.UUID,
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointOut:
    ep = await _get_or_404(db, webhook_id, org_id)
    return _to_out(ep)


@router.patch("/{webhook_id}", response_model=WebhookEndpointOut)
async def update_webhook(
    webhook_id: uuid.UUID,
    payload: WebhookEndpointUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointOut:
    ep = await _get_or_404(db, webhook_id, org_id)
    changes = payload.model_dump(exclude_unset=True)

    if "enabled_events" in changes and changes["enabled_events"] is not None:
        _validate_event_slugs(changes["enabled_events"])
        ep.enabled_events = json.dumps(changes["enabled_events"])
    if "description" in changes:
        ep.description = changes["description"]
    if "paused" in changes:
        if changes["paused"]:
            ep.paused_at = datetime.now(UTC)
        else:
            ep.paused_at = None
            # Unpause resets the failure counter so the auto-pause
            # threshold doesn't fire again on the very next failure.
            ep.consecutive_failures = 0

    await record_audit(
        db,
        actor=user,
        action="webhook.update",
        entity_type="webhook_endpoint",
        entity_id=ep.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await db.refresh(ep)
    return _to_out(ep)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    ep = await _get_or_404(db, webhook_id, org_id)
    await record_audit(
        db,
        actor=user,
        action="webhook.delete",
        entity_type="webhook_endpoint",
        entity_id=ep.id,
        organization_id=org_id,
        metadata={"url": ep.url},
    )
    await db.delete(ep)
    await db.commit()


@router.get(
    "/{webhook_id}/deliveries",
    response_model=list[WebhookDeliveryOut],
)
async def list_deliveries(
    webhook_id: uuid.UUID,
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WebhookDeliveryOut]:
    # Existence/ownership check on the parent endpoint — returns 404
    # for foreign-org endpoints (no enumeration of other orgs' IDs).
    await _get_or_404(db, webhook_id, org_id)
    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == webhook_id)
        .order_by(desc(WebhookDelivery.scheduled_for), desc(WebhookDelivery.id))
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [
        WebhookDeliveryOut(
            id=d.id,
            endpoint_id=d.endpoint_id,
            event_id=d.event_id,
            event_type=d.event_type,
            attempt=d.attempt,
            status=d.status,
            response_code=d.response_code,
            response_body_excerpt=d.response_body_excerpt,
            error=d.error,
            latency_ms=d.latency_ms,
            scheduled_for=d.scheduled_for,
            finished_at=d.finished_at,
        )
        for d in rows
    ]
