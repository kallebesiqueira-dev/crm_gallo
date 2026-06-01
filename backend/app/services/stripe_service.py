"""Stripe integration — Checkout, Customer Portal, Webhook handling.

Design choices:
- Library `stripe` (sync HTTP under the hood) called in async endpoints via
  `asyncio.to_thread` so we don't block the event loop.
- All paid plans go through Stripe Checkout. The webhook is the source of
  truth for subscription state — never trust the success redirect alone.
- Webhook events are deduplicated via `stripe_events` table.
- When STRIPE_SECRET_KEY is empty, every call here raises StripeNotConfigured
  so callers can show a friendly error instead of a 500.

Multi-tenant model: ONE Stripe Customer per `Organization`. Webhooks update
`Organization.plan / .billing_cycle / .stripe_*`, never the user. The
"actor" of a webhook-driven audit is None (system event); the
`organization_id` is the tenant context.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.billing.catalog import resolve_stripe_price_id
from app.config import get_settings
from app.logging_setup import get_logger
from app.models import BillingCycle, Organization, Plan, StripeEvent, User

log = get_logger(__name__)
settings = get_settings()


class StripeNotConfigured(RuntimeError):
    """Raised when paid-plan flow runs without STRIPE_SECRET_KEY set."""


class StripeError(RuntimeError):
    """Wraps Stripe SDK errors with our own message."""


def _ensure_configured() -> None:
    if not settings.stripe_secret_key:
        raise StripeNotConfigured(
            "Stripe is not configured. Set STRIPE_SECRET_KEY to enable paid plans."
        )
    stripe.api_key = settings.stripe_secret_key


# ---------- Customer ----------


async def get_or_create_customer(org: Organization, actor: User | None, db: AsyncSession) -> str:
    """Return the org's Stripe customer id, creating one if needed.

    `actor` is the user who triggered the action (admin starting checkout)
    so the Stripe customer record carries something human-readable in the
    `name` field. None is acceptable — webhook-driven flows can call this
    without a user context.
    """
    _ensure_configured()
    if org.stripe_customer_id:
        return org.stripe_customer_id

    def _create() -> Any:
        return stripe.Customer.create(
            email=actor.email if actor else None,
            name=org.name,
            metadata={
                "organization_id": str(org.id),
                "organization_slug": org.slug,
                "created_by_user_id": str(actor.id) if actor else "system",
            },
        )

    try:
        customer = await asyncio.to_thread(_create)
    except stripe.StripeError as e:
        raise StripeError(f"Stripe customer create failed: {e}") from e

    org.stripe_customer_id = customer.id
    await db.commit()
    await db.refresh(org)
    return customer.id


# ---------- Checkout ----------


async def create_checkout_session(
    *,
    org: Organization,
    actor: User,
    plan: Plan,
    cycle: BillingCycle,
    db: AsyncSession,
) -> str:
    """Returns a Stripe Checkout URL the frontend should redirect to."""
    _ensure_configured()

    if plan == Plan.free:
        raise StripeError("Free plan does not require Stripe checkout.")

    price_id = resolve_stripe_price_id(plan, cycle)
    if not price_id:
        raise StripeError(
            f"No Stripe Price ID configured for {plan.value}/{cycle.value}. "
            "Set STRIPE_PRICE_* env vars."
        )

    customer_id = await get_or_create_customer(org, actor, db)

    def _create_session() -> Any:
        from app.billing.catalog import get_plan

        descriptor = get_plan(plan)
        subscription_data: dict[str, Any] = {
            # `organization_id` is what every webhook handler will key on.
            # `started_by` keeps the audit trail useful.
            "metadata": {
                "organization_id": str(org.id),
                "started_by": str(actor.id),
                "plan": plan.value,
            },
        }
        if descriptor.trial_days > 0:
            subscription_data["trial_period_days"] = descriptor.trial_days

        return stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            allow_promotion_codes=True,
            billing_address_collection="auto",
            success_url=settings.stripe_success_url,
            cancel_url=settings.stripe_cancel_url,
            subscription_data=subscription_data,
            metadata={
                "organization_id": str(org.id),
                "started_by": str(actor.id),
                "plan": plan.value,
                "cycle": cycle.value,
            },
        )

    try:
        session = await asyncio.to_thread(_create_session)
    except stripe.StripeError as e:
        raise StripeError(f"Stripe checkout create failed: {e}") from e

    await record_audit(
        db,
        actor=actor,
        action="billing.checkout_session.create",
        entity_type="billing",
        entity_id=org.id,
        organization_id=org.id,
        metadata={"plan": plan.value, "cycle": cycle.value, "session_id": session.id},
    )
    await db.commit()
    return session.url


# ---------- Customer Portal ----------


async def create_portal_session(*, org: Organization, return_url: str, db: AsyncSession) -> str:
    """Returns a Stripe Customer Portal URL — used for self-serve billing
    management (update card, cancel, view invoices)."""
    _ensure_configured()
    customer_id = await get_or_create_customer(org, actor=None, db=db)

    def _create() -> Any:
        return stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )

    try:
        session = await asyncio.to_thread(_create)
    except stripe.StripeError as e:
        raise StripeError(f"Stripe portal create failed: {e}") from e
    return session.url


# ---------- Webhooks ----------


def verify_webhook(payload: bytes, signature: str) -> dict[str, Any]:
    """Construct and verify a Stripe event from raw body + signature."""
    if not settings.stripe_webhook_secret:
        raise StripeNotConfigured("STRIPE_WEBHOOK_SECRET is not configured.")
    try:
        event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
    except (stripe.SignatureVerificationError, ValueError) as e:
        raise StripeError(f"Invalid webhook signature: {e}") from e
    return event


async def process_event(event: dict[str, Any], db: AsyncSession) -> None:
    """Idempotent processing of a Stripe event."""
    event_id: str = event["id"]
    event_type: str = event["type"]

    # Dedupe — Stripe retries deliveries. We log every event, then act only
    # the first time we see the id.
    existing = await db.execute(select(StripeEvent).where(StripeEvent.id == event_id))
    if existing.scalar_one_or_none() is not None:
        log.info("stripe_event.dedup", event_id=event_id, type=event_type)
        return

    db.add(
        StripeEvent(
            id=event_id,
            type=event_type,
            payload=json.dumps(event, default=str),
        )
    )

    handler = _HANDLERS.get(event_type)
    if handler is not None:
        await handler(event, db)
    else:
        log.info("stripe_event.unhandled", event_id=event_id, type=event_type)

    # Mark processed.
    row = (await db.execute(select(StripeEvent).where(StripeEvent.id == event_id))).scalar_one()
    row.processed_at = datetime.now(UTC)
    await db.commit()


async def _find_org_by_customer(customer_id: str, db: AsyncSession) -> Organization | None:
    return (
        await db.execute(select(Organization).where(Organization.stripe_customer_id == customer_id))
    ).scalar_one_or_none()


async def _on_checkout_completed(event: dict[str, Any], db: AsyncSession) -> None:
    session = event["data"]["object"]
    metadata = session.get("metadata", {}) or {}
    org_id = metadata.get("organization_id")
    plan_raw = metadata.get("plan")
    cycle_raw = metadata.get("cycle", "monthly")
    subscription_id = session.get("subscription")

    if not org_id or not plan_raw:
        log.warning(
            "checkout.session.completed missing metadata",
            session_id=session.get("id"),
        )
        return

    org = await db.get(Organization, org_id)
    if not org:
        log.warning("checkout.session.completed org not found", organization_id=org_id)
        return

    org.plan = Plan(plan_raw)
    org.billing_cycle = BillingCycle(cycle_raw)
    org.stripe_subscription_id = subscription_id
    now = datetime.now(UTC)
    org.plan_started_at = org.plan_started_at or now
    org.plan_renewed_at = now
    org.plan_canceled_at = None

    await record_audit(
        db,
        actor=None,
        action="billing.subscription.activated",
        entity_type="billing",
        entity_id=org.id,
        organization_id=org.id,
        metadata={"plan": org.plan.value, "subscription_id": subscription_id},
    )


async def _on_invoice_paid(event: dict[str, Any], db: AsyncSession) -> None:
    invoice = event["data"]["object"]
    customer_id = invoice.get("customer")
    if not customer_id:
        return
    org = await _find_org_by_customer(customer_id, db)
    if not org:
        return
    org.plan_renewed_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=None,
        action="billing.invoice.paid",
        entity_type="billing",
        entity_id=org.id,
        organization_id=org.id,
        metadata={"invoice_id": invoice.get("id"), "amount": invoice.get("amount_paid")},
    )


async def _on_subscription_deleted(event: dict[str, Any], db: AsyncSession) -> None:
    subscription = event["data"]["object"]
    customer_id = subscription.get("customer")
    if not customer_id:
        return
    org = await _find_org_by_customer(customer_id, db)
    if not org:
        return
    org.plan = Plan.free
    org.plan_canceled_at = datetime.now(UTC)
    org.stripe_subscription_id = None
    await record_audit(
        db,
        actor=None,
        action="billing.subscription.canceled",
        entity_type="billing",
        entity_id=org.id,
        organization_id=org.id,
    )


_HANDLERS = {
    "checkout.session.completed": _on_checkout_completed,
    "invoice.paid": _on_invoice_paid,
    "invoice.payment_succeeded": _on_invoice_paid,
    "customer.subscription.deleted": _on_subscription_deleted,
}
