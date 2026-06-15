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
from app.models import BillingCycle, Plan
from app.money import q2

FREE_SEAT_LIMIT = 2
YEARLY_DISCOUNT = Decimal("0.20")  # 20% off when paying annually
TRIAL_DAYS_PREMIUM = 14  # Premium ships with a 14-day trial

# Multi-currency (plan.md §6). These are POSITIONED price points per
# market, not FX conversions — round numbers a CH/UK/BR buyer expects
# to see, set once per pricing review. EUR stays the canonical price;
# Stripe enforces whatever the per-currency Price ID actually says.
SUPPORTED_CURRENCIES = ("eur", "chf", "gbp", "brl")


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
    # Positioned monthly price per non-EUR currency ("chf"/"gbp"/"brl").
    # EUR lives in `monthly_eur`; absent key = currency not offered.
    monthly_prices: dict[str, Decimal] = field(default_factory=dict)

    @property
    def yearly_eur_per_user(self) -> Decimal:
        """Effective monthly price when paying annually."""
        return q2(self.monthly_eur * (1 - YEARLY_DISCOUNT))

    @property
    def yearly_total_eur(self) -> Decimal:
        return q2(self.yearly_eur_per_user * 12)

    def monthly_price(self, currency: str = "eur") -> Decimal:
        """Monthly price point in `currency`. KeyError on a currency this
        plan doesn't list — callers validate against SUPPORTED_CURRENCIES
        first, so a KeyError here means a catalog gap, not user error."""
        if currency == "eur":
            return self.monthly_eur
        return self.monthly_prices[currency]

    def yearly_price_per_user(self, currency: str = "eur") -> Decimal:
        return q2(self.monthly_price(currency) * (1 - YEARLY_DISCOUNT))


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
        monthly_prices={
            "chf": Decimal("19.00"),
            "gbp": Decimal("17.00"),
            "brl": Decimal("99.00"),
        },
        seat_limit=None,
        features=[
            "Unlimited users",
            "Everything in Free",
            "Advanced AI scoring",
            "Unlimited AI assistant",
            "Quotes & PDF proposals",
            "Reports and visual charts",
            "Priority support",
        ],
        highlighted=True,
        requires_payment=True,
    ),
    Plan.business: PlanDescriptor(
        id=Plan.business,
        name="Business",
        tagline="For teams closing deals end-to-end.",
        monthly_eur=Decimal("39.00"),
        monthly_prices={
            "chf": Decimal("39.00"),
            "gbp": Decimal("34.00"),
            "brl": Decimal("199.00"),
        },
        seat_limit=None,
        features=[
            "Everything in Standard",
            "Contracts & e-signature",
            "Bulk imports & exports",
            "Teams & custom pipelines",
            "Full audit log",
            "Outgoing webhooks",
        ],
        requires_payment=True,
    ),
    Plan.premium: PlanDescriptor(
        id=Plan.premium,
        name="Premium",
        tagline="For teams that scale with automation.",
        monthly_eur=Decimal("59.00"),
        monthly_prices={
            "chf": Decimal("59.00"),
            "gbp": Decimal("49.00"),
            "brl": Decimal("299.00"),
        },
        seat_limit=None,
        features=[
            "Everything in Business",
            "Workflow automations",
            "WhatsApp integration",
            "Public API + API keys",
            "Dedicated account manager",
        ],
        requires_payment=True,
        trial_days=TRIAL_DAYS_PREMIUM,
    ),
}


def get_plan(plan: Plan) -> PlanDescriptor:
    return CATALOG[plan]


def list_plans() -> list[PlanDescriptor]:
    return [CATALOG[p] for p in (Plan.free, Plan.standard, Plan.business, Plan.premium)]


def resolve_stripe_price_id(plan: Plan, cycle: BillingCycle, currency: str = "eur") -> str | None:
    """Look up the Stripe Price ID for (plan, billing cycle, currency).

    EUR keeps the legacy `STRIPE_PRICE_{PLAN}_{CYCLE}` env names so
    existing deployments need zero changes; other currencies append the
    code (`..._CHF` / `..._GBP` / `..._BRL`). Returns None when not
    configured — the caller decides whether that's a hard error
    (production) or graceful skip (dev without keys / currency not yet
    provisioned in Stripe).
    """
    settings = get_settings()
    key = f"stripe_price_{plan.value}_{cycle.value}"
    if currency != "eur":
        key = f"{key}_{currency}"
    return getattr(settings, key, "") or None
