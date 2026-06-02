"""Pricing catalog — single source of truth for plan prices and features.

Prices are in EUR, positioned in the lower-mid European CRM market
(competitive with Pipedrive Essential/Advanced, monday CRM Starter).

The Free plan is fully self-serve. Standard and Premium go through Stripe
Checkout. Stripe Price IDs are resolved from environment variables so the
same code runs against test/live keys without redeploy.

Future P2: move the display catalog to a DB table so admins can edit copy
without a deploy. Prices themselves stay tied to Stripe Price IDs.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from app.config import get_settings
from app.money import q2
from app.models import BillingCycle, Plan

FREE_SEAT_LIMIT = 2
YEARLY_DISCOUNT = Decimal("0.20")  # 20% off when paying annually
TRIAL_DAYS_PREMIUM = 14  # Premium ships with a 14-day trial


@dataclass(frozen=True)
class PlanDescriptor:
    id: Plan
    name: str
    tagline: str
    monthly_eur: Decimal  # exact money (ADR-015); PlanOut serializes to float
    seat_limit: int | None  # None = unlimited
    features: list[str] = field(default_factory=list)
    highlighted: bool = False
    requires_payment: bool = False
    trial_days: int = 0

    @property
    def yearly_eur_per_user(self) -> Decimal:
        """Effective monthly price when paying annually."""
        return q2(self.monthly_eur * (1 - YEARLY_DISCOUNT))

    @property
    def yearly_total_eur(self) -> Decimal:
        return q2(self.yearly_eur_per_user * 12)


CATALOG: dict[Plan, PlanDescriptor] = {
    Plan.free: PlanDescriptor(
        id=Plan.free,
        name="Free",
        tagline="Get started and validate with your team.",
        monthly_eur=Decimal("0"),
        seat_limit=FREE_SEAT_LIMIT,
        features=[
            "Up to 2 users",
            "Leads, customers, deals and pipeline",
            "AI scoring (lightweight model)",
            "Email support",
        ],
    ),
    Plan.standard: PlanDescriptor(
        id=Plan.standard,
        name="Standard",
        tagline="For growing sales teams.",
        monthly_eur=Decimal("19.00"),
        seat_limit=None,
        features=[
            "Unlimited users",
            "Everything in Free",
            "Advanced AI scoring (Claude Sonnet)",
            "Unlimited AI assistant",
            "Reports and visual charts",
            "Trash with restore",
            "Priority support",
        ],
        highlighted=True,
        requires_payment=True,
    ),
    Plan.premium: PlanDescriptor(
        id=Plan.premium,
        name="Premium",
        tagline="For teams that scale with automation.",
        monthly_eur=Decimal("49.00"),
        seat_limit=None,
        features=[
            "Everything in Standard",
            "Workflow automations",
            "Email and calendar integrations",
            "RAG: assistant with knowledge base",
            "API + Webhooks",
            "Full audit log",
            "Dedicated account manager",
        ],
        requires_payment=True,
        trial_days=TRIAL_DAYS_PREMIUM,
    ),
}


def get_plan(plan: Plan) -> PlanDescriptor:
    return CATALOG[plan]


def list_plans() -> list[PlanDescriptor]:
    return [CATALOG[p] for p in (Plan.free, Plan.standard, Plan.premium)]


def resolve_stripe_price_id(plan: Plan, cycle: BillingCycle) -> str | None:
    """Look up the Stripe Price ID for (plan, billing cycle).

    Returns None when not configured — the caller decides whether that's
    a hard error (production) or graceful skip (dev without keys).
    """
    settings = get_settings()
    key = f"stripe_price_{plan.value}_{cycle.value}"
    return getattr(settings, key, "") or None
