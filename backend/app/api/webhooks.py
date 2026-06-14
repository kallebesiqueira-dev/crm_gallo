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
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import get_current_org_id, require_roles
from app.events import EventType
from app.models import User, UserRole, WebhookDelivery, WebhookEndpoint
from app.schemas import (
    WebhookDeliveryOut,
    WebhookDeliveryStats,
    WebhookEndpointCreate,
    WebhookEndpointCreated,
    WebhookEndpointOut,
    WebhookEndpointUpdate,
    WebhookTestResult,
)
from app.webhook_sign import SIGNATURE_HEADER, generate_secret, sign_payload

# Inline test-ping tunables — kept local to the request path so we don't
# import the worker module (and its heavy deps) just to send one POST.
_TEST_HTTP_TIMEOUT_S = 10.0
_TEST_RESPONSE_EXCERPT_BYTES = 2048

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
            raise HTTPException(status_code=400, detail="private/loopback URL not allowed")
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


@router.post("/{webhook_id}/rotate-secret", response_model=WebhookEndpointCreated)
async def rotate_secret(
    webhook_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointCreated:
    """Mint a fresh signing secret for an existing endpoint.

    Dedicated route (not folded into PATCH) so rotation is always an
    explicit, intentional act — never a side effect of a generic update.
    Returns the new plaintext secret ONCE, exactly like create; the old
    secret stops signing immediately, so the receiver must be updated in
    lockstep (deliveries signed with the old secret will fail to verify).
    """
    ep = await _get_or_404(db, webhook_id, org_id)
    secret = generate_secret()
    ep.secret = secret
    await record_audit(
        db,
        actor=user,
        action="webhook.rotate_secret",
        entity_type="webhook_endpoint",
        entity_id=ep.id,
        organization_id=org_id,
        metadata={"url": ep.url},
    )
    await db.commit()
    await db.refresh(ep)
    base = _to_out(ep)
    return WebhookEndpointCreated(**base.model_dump(), secret=secret)


@router.post("/{webhook_id}/test", response_model=WebhookTestResult)
async def test_webhook(
    webhook_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> WebhookTestResult:
    """Send a synthetic `webhook.test` event to the endpoint, inline.

    Unlike a real delivery (worker, retries, auto-pause), the test ping
    is a one-shot synchronous POST so the admin sees the receiver's HTTP
    status right away. It records a `WebhookDelivery` row for the history
    table but does NOT mutate `consecutive_failures` / `last_*_at` — a
    test must not nudge a healthy endpoint toward auto-pause. Works even
    while the endpoint is paused (that's the point: verify before
    unpausing).
    """
    ep = await _get_or_404(db, webhook_id, org_id)

    event_id = uuid.uuid4()
    body = json.dumps(
        {
            "event_id": str(event_id),
            "event_type": "webhook.test",
            "organization_id": str(org_id),
            "payload": {
                "message": "Test delivery from Gallo CRM",
                "test": True,
            },
        },
        sort_keys=True,
    ).encode("utf-8")
    signature = sign_payload(ep.secret, body)

    delivery = WebhookDelivery(
        endpoint_id=ep.id,
        event_id=event_id,
        event_type="webhook.test",
        attempt=1,
    )

    started = time.perf_counter()
    response_code: int | None = None
    excerpt: str | None = None
    err: str | None = None
    succeeded = False
    try:
        async with httpx.AsyncClient(timeout=_TEST_HTTP_TIMEOUT_S) as client:
            r = await client.post(
                ep.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "CRM-Gallo-Webhook/1.0",
                    SIGNATURE_HEADER: signature,
                    "X-CRM-Event-Id": str(event_id),
                    "X-CRM-Event-Type": "webhook.test",
                },
            )
        response_code = r.status_code
        excerpt = r.text[:_TEST_RESPONSE_EXCERPT_BYTES] or None
        succeeded = 200 <= r.status_code < 300
        if not succeeded:
            err = f"HTTP {r.status_code}"
    except httpx.HTTPError as e:
        err = f"{type(e).__name__}: {e}"

    delivery.latency_ms = int((time.perf_counter() - started) * 1000)
    delivery.response_code = response_code
    delivery.response_body_excerpt = excerpt
    delivery.error = err
    delivery.status = "success" if succeeded else "failed"
    delivery.finished_at = datetime.now(UTC)
    db.add(delivery)

    await record_audit(
        db,
        actor=user,
        action="webhook.test",
        entity_type="webhook_endpoint",
        entity_id=ep.id,
        organization_id=org_id,
        metadata={"url": ep.url, "delivered": succeeded, "response_code": response_code},
    )
    await db.commit()
    await db.refresh(delivery)

    return WebhookTestResult(
        delivered=succeeded,
        response_code=response_code,
        latency_ms=delivery.latency_ms,
        error=err,
        delivery_id=delivery.id,
    )


@router.get("/{webhook_id}/metrics", response_model=WebhookDeliveryStats)
async def webhook_metrics(
    webhook_id: uuid.UUID,
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    window_days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> WebhookDeliveryStats:
    """Aggregate delivery health for one endpoint over the last
    `window_days` (default 7). Counts + latency percentiles come from
    `webhook_deliveries`; `success_rate` is over terminal attempts only.
    """
    await _get_or_404(db, webhook_id, org_id)
    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    succeeded_col = func.count().filter(WebhookDelivery.status == "success")
    failed_col = func.count().filter(WebhookDelivery.status == "failed")
    pending_col = func.count().filter(WebhookDelivery.status == "pending")
    row = (
        await db.execute(
            select(
                func.count().label("total"),
                succeeded_col.label("succeeded"),
                failed_col.label("failed"),
                pending_col.label("pending"),
                func.avg(WebhookDelivery.latency_ms).label("avg_latency"),
                func.percentile_cont(0.5)
                .within_group(WebhookDelivery.latency_ms.asc())
                .label("p50"),
                func.percentile_cont(0.95)
                .within_group(WebhookDelivery.latency_ms.asc())
                .label("p95"),
            ).where(
                WebhookDelivery.endpoint_id == webhook_id,
                WebhookDelivery.scheduled_for >= cutoff,
            )
        )
    ).one()

    terminal = (row.succeeded or 0) + (row.failed or 0)
    success_rate = (row.succeeded / terminal) if terminal else None

    def _ms(v: float | None) -> int | None:
        return int(round(v)) if v is not None else None

    return WebhookDeliveryStats(
        window_days=window_days,
        total=row.total or 0,
        succeeded=row.succeeded or 0,
        failed=row.failed or 0,
        pending=row.pending or 0,
        success_rate=round(success_rate, 4) if success_rate is not None else None,
        avg_latency_ms=_ms(row.avg_latency),
        p50_latency_ms=_ms(row.p50),
        p95_latency_ms=_ms(row.p95),
    )
