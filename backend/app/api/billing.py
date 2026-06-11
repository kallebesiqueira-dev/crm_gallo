"""Billing endpoints — plan catalog, current plan, Stripe checkout & portal, webhook.

The Free plan is fully self-serve and does NOT touch Stripe. Standard and
Premium go through Stripe Checkout; the webhook is the source of truth.

Multi-tenant: billing lives on `Organization`. Every endpoint here resolves
the current org via `get_current_org` (derived from the user's
`last_active_org_id`). The Stripe customer maps 1:1 to an Organization,
not a User — a single user across multiple orgs has one Stripe Customer
per org.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.billing.catalog import (
    FREE_SEAT_LIMIT,
    SUPPORTED_CURRENCIES,
    get_plan,
    list_plans,
)
from app.config import get_settings
from app.database import get_db
from app.deps import get_current_org, require_roles
from app.logging_setup import get_logger
from app.models import Organization, OrgMembership, Plan, User, UserRole
from app.rate_limit import limiter
from app.schemas import BillingMe, PlanOut, UpgradeRequest
from app.services.stripe_service import (
    PUBLIC_PLAN_KEYS,
    StripeError,
    StripeNotConfigured,
    create_checkout_session,
    create_portal_session,
    create_public_checkout_session,
    process_event,
    verify_webhook,
)

log = get_logger(__name__)
settings = get_settings()


async def _stripe_webhook_ip_guard(request: Request) -> None:
    """600 req/min per IP on the unauthenticated Stripe webhook path.
    Stripe sends at most a few events/second under peak load; this cap
    stops DDoS without touching the HMAC-verified happy path."""
    from app.redis_client import get_redis

    ip = (request.client.host if request.client else None) or "unknown"
    r = get_redis()
    key = f"stripe_wh_ip:{ip}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 60)
    if count > 600:
        raise HTTPException(status_code=429, detail="Too Many Requests")


router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutResponse(BaseModel):
    url: str


class CheckoutRequest(UpgradeRequest):
    """UpgradeRequest + currency (plan.md §6). Local subclass so the
    shared schemas module stays untouched; defaults to EUR so existing
    frontend calls keep working unchanged."""

    currency: str = "eur"


class PortalRequest(BaseModel):
    return_url: str | None = None


@router.get("/plans", response_model=list[PlanOut])
async def get_plans() -> list[PlanOut]:
    """Public-ish: anyone can see the catalog. Used by the marketing page."""
    return [
        PlanOut(
            id=p.id,
            name=p.name,
            tagline=p.tagline,
            monthly_eur=p.monthly_eur,
            yearly_eur_per_user=p.yearly_eur_per_user,
            yearly_total_eur=p.yearly_total_eur,
            seat_limit=p.seat_limit,
            features=p.features,
            highlighted=p.highlighted,
            requires_payment=p.requires_payment,
            trial_days=p.trial_days,
        )
        for p in list_plans()
    ]


async def _seats_used(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Count active memberships in the given org. The legacy
    `is_active` check still applies — if a user is disabled they don't
    consume a seat even if their membership row exists."""
    return (
        await db.execute(
            select(func.count())
            .select_from(OrgMembership)
            .join(User, User.id == OrgMembership.user_id)
            .where(
                OrgMembership.organization_id == org_id,
                User.is_active.is_(True),
            )
        )
    ).scalar_one()


@router.get("/me", response_model=BillingMe)
async def my_billing(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> BillingMe:
    descriptor = get_plan(org.plan)
    seats_used = await _seats_used(db, org.id)
    seats_remaining = (
        max(0, descriptor.seat_limit - seats_used) if descriptor.seat_limit is not None else None
    )
    return BillingMe(
        plan=org.plan,
        billing_cycle=org.billing_cycle,
        seat_limit=descriptor.seat_limit,
        seats_used=seats_used,
        seats_remaining=seats_remaining,
        plan_started_at=org.plan_started_at,
        plan_renewed_at=org.plan_renewed_at,
        plan_canceled_at=org.plan_canceled_at,
        trial_ends_at=org.trial_ends_at,
        stripe_configured=bool(settings.stripe_secret_key),
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    payload: CheckoutRequest,
    user: User = Depends(require_roles(UserRole.admin)),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    """Admin starts a paid-plan checkout. Returns Stripe Checkout URL."""
    if payload.plan == Plan.free:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Free plan does not require checkout.",
        )
    currency = payload.currency.lower()
    if currency not in SUPPORTED_CURRENCIES:
        # Friendly 400 over a pydantic 422 — the supported set is product
        # config, not request grammar.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported currency '{payload.currency}'."
            f" Supported: {', '.join(SUPPORTED_CURRENCIES)}.",
        )
    try:
        url = await create_checkout_session(
            org=org,
            actor=user,
            plan=payload.plan,
            cycle=payload.billing_cycle,
            db=db,
            currency=currency,
        )
    except StripeNotConfigured as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except StripeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return CheckoutResponse(url=url)


class PublicCheckoutRequest(BaseModel):
    # Plan KEY only — the price is resolved + validated server-side. The client
    # never sends an amount or a Stripe price id.
    plan: str


@router.post("/create-checkout-session", response_model=CheckoutResponse)
@limiter.limit(f"{settings.rate_limit_register_per_minute}/minute")
async def create_checkout_session_public(
    request: Request, payload: PublicCheckoutRequest
) -> CheckoutResponse:
    """Public landing checkout — no auth, per-IP rate-limited.

    The frontend sends only a plan key (standard/business/premium, or the
    starter/pro/enterprise aliases); the price is resolved server-side so a
    tampered request can never choose its own amount. Returns a hosted Stripe
    Checkout URL. 503 when Stripe isn't configured (frontend falls back to the
    direct link / sign-up).
    """
    plan_key = (payload.plan or "").strip().lower()
    if plan_key not in PUBLIC_PLAN_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or non-payable plan.",
        )
    try:
        url = await create_public_checkout_session(plan_key)
    except StripeNotConfigured as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except StripeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return CheckoutResponse(url=url)


@router.post("/portal", response_model=CheckoutResponse)
async def portal(
    payload: PortalRequest,
    _: User = Depends(require_roles(UserRole.admin)),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    """Admin opens the Stripe Customer Portal (manage card, cancel, invoices)."""
    return_url = payload.return_url or settings.stripe_success_url.split("?")[0]
    try:
        url = await create_portal_session(org=org, return_url=return_url, db=db)
    except StripeNotConfigured as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except StripeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return CheckoutResponse(url=url)


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(_stripe_webhook_ip_guard),
) -> None:
    """Stripe-signed webhook receiver. Idempotent by event id.

    No `get_current_user` here — webhooks are unauthenticated (Stripe is the
    caller). Signature verification + the per-org metadata in the payload
    are what bind events to a tenant.
    """
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    payload = await request.body()
    try:
        event = verify_webhook(payload, stripe_signature)
    except StripeNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except StripeError as e:
        log.warning("stripe_webhook.invalid_signature", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid signature") from e

    try:
        await process_event(event, db)
    except Exception as e:
        log.exception("stripe_webhook.processing_failed", error=str(e))
        # Return 500 so Stripe retries — we don't want to swallow real failures.
        raise HTTPException(status_code=500, detail="Webhook processing failed") from e


@router.post("/upgrade", response_model=BillingMe)
async def upgrade(
    payload: UpgradeRequest,
    user: User = Depends(require_roles(UserRole.admin)),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> BillingMe:
    """Internal/admin-override upgrade — bypasses Stripe.

    DO NOT expose to end users in production. Useful for: demo accounts,
    support promo upgrades, automated tests. UI hides this for non-admins.
    """
    if payload.plan == Plan.free:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Downgrade to Free is handled via Stripe cancellation.",
        )

    previous_plan = org.plan
    now = datetime.now(UTC)
    org.plan = payload.plan
    org.billing_cycle = payload.billing_cycle
    if previous_plan == Plan.free:
        org.plan_started_at = now
    org.plan_renewed_at = now

    await record_audit(
        db,
        actor=user,
        action="billing.upgrade.manual",
        entity_type="billing",
        entity_id=org.id,
        organization_id=org.id,
        metadata={
            "from": previous_plan.value,
            "to": payload.plan.value,
            "cycle": payload.billing_cycle.value,
        },
    )
    await db.commit()
    await db.refresh(org)

    descriptor = get_plan(org.plan)
    seats_used = await _seats_used(db, org.id)
    return BillingMe(
        plan=org.plan,
        billing_cycle=org.billing_cycle,
        seat_limit=descriptor.seat_limit,
        seats_used=seats_used,
        seats_remaining=(
            None if descriptor.seat_limit is None else max(0, descriptor.seat_limit - seats_used)
        ),
        plan_started_at=org.plan_started_at,
        plan_renewed_at=org.plan_renewed_at,
        plan_canceled_at=org.plan_canceled_at,
        trial_ends_at=org.trial_ends_at,
        stripe_configured=bool(settings.stripe_secret_key),
    )


# Helper used by auth.register to enforce the seat limit per-org.
async def can_accept_new_user(db: AsyncSession, org_id: uuid.UUID) -> tuple[bool, str | None]:
    """True if the given org can accept one more member without breaching
    its plan's seat limit. Paid plans currently have no cap.
    """
    org = await db.get(Organization, org_id)
    if org is None:
        return False, "Organization not found"
    descriptor = get_plan(org.plan)
    if descriptor.seat_limit is None:
        return True, None
    seats = await _seats_used(db, org_id)
    if seats < descriptor.seat_limit:
        return True, None
    return (
        False,
        f"Plan '{descriptor.name}' allows up to {FREE_SEAT_LIMIT} users. "
        "Please upgrade to Standard or Premium to add more.",
    )
