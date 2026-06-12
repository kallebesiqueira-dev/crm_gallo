"""Lead → Customer/Company/Deal conversion (plan.md §4).

One POST turns a qualified lead into the structured trio the rest of
the funnel works with: the person (Customer), their firm (Company,
when the lead carries one) and the opportunity (Deal) — atomically,
in a single transaction.

Self-contained module (router + request/response schemas local, the
`trash.py` pattern) so it composes with the shared `models.py` /
`schemas.py` without touching them.

Semantics:
  * The lead itself is left in place — its timeline gains a
    `lead_converted` activity, which doubles as the idempotency
    guard: converting the same lead twice returns 409.
  * Customer dedupe: a live customer in the same org with the same
    (case-insensitive) email is REUSED, mirroring the partial-unique
    index `uq_customers_org_email_live` instead of tripping it.
  * Company dedupe: matched by case-insensitive name within the org.
  * The deal mirrors `POST /api/deals` (audit + activity +
    `deal_created` outbox event, org-scoped sort_index) so
    automations fire exactly as if it had been created by hand.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities import (
    ENTITY_CUSTOMER,
    ENTITY_DEAL,
    ENTITY_LEAD,
    ActivityType,
    record_activity,
)
from app.api._errors import raise_for_duplicate_email
from app.audit import record_audit
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.events import EventType, record_event
from app.models import Activity, Company, Customer, Deal, DealStage, Lead, User

router = APIRouter(prefix="/api/leads", tags=["leads"])


class LeadConvertIn(BaseModel):
    """Optional overrides — sensible defaults come from the lead."""

    deal_title: str | None = Field(default=None, min_length=1, max_length=255)
    deal_value: Decimal | None = Field(default=None, ge=0)


class LeadConvertOut(BaseModel):
    customer_id: uuid.UUID
    company_id: uuid.UUID | None
    deal_id: uuid.UUID
    # True when the entity was matched to an existing row instead of
    # created — the UI can phrase the confirmation accordingly.
    customer_existed: bool
    company_existed: bool


async def _get_lead_or_404(db: AsyncSession, lead_id: uuid.UUID, org_id: uuid.UUID) -> Lead:
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.organization_id == org_id)
    )
    lead = result.scalar_one_or_none()
    if not lead or lead.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


async def _resolve_company(
    db: AsyncSession, lead: Lead, org_id: uuid.UUID, owner_id: uuid.UUID | None
) -> tuple[Company | None, bool]:
    """Reuse the lead's structured link, else match by name, else create
    from the lead's free-text `company`. (None, False) when the lead has
    no company information at all."""
    if lead.company_id is not None:
        existing = (
            await db.execute(
                select(Company).where(
                    Company.id == lead.company_id, Company.organization_id == org_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, True

    name = (lead.company or "").strip()
    if not name:
        return None, False

    matched = (
        await db.execute(
            select(Company)
            .where(
                Company.organization_id == org_id,
                func.lower(Company.name) == name.lower(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if matched is not None:
        return matched, True

    company = Company(
        organization_id=org_id,
        name=name,
        industry=lead.industry,
        country=lead.country,
        size=lead.company_size,
        owner_id=owner_id,
    )
    db.add(company)
    await db.flush()
    return company, False


@router.post(
    "/{lead_id}/convert",
    response_model=LeadConvertOut,
    status_code=status.HTTP_201_CREATED,
)
async def convert_lead(
    lead_id: uuid.UUID,
    payload: LeadConvertIn | None = None,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> LeadConvertOut:
    lead = await _get_lead_or_404(db, lead_id, org_id)
    ensure_can_mutate(user, lead.owner_id)
    overrides = payload or LeadConvertIn()

    # Idempotency guard: the lead_converted activity on the lead IS the
    # conversion marker — a second click must not mint a duplicate trio.
    already = (
        await db.execute(
            select(Activity.id)
            .where(
                Activity.organization_id == org_id,
                Activity.entity_type == ENTITY_LEAD,
                Activity.entity_id == lead.id,
                Activity.type == ActivityType.lead_converted.value,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if already is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead has already been converted.",
        )

    owner_id = lead.owner_id or user.id
    company, company_existed = await _resolve_company(db, lead, org_id, owner_id)

    # Customer: reuse a live same-email contact instead of tripping the
    # partial-unique index; otherwise carry the lead's identity over.
    customer: Customer | None = None
    if lead.email:
        customer = (
            await db.execute(
                select(Customer)
                .where(
                    Customer.organization_id == org_id,
                    func.lower(Customer.email) == lead.email.lower(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
    customer_existed = customer is not None
    if customer is None:
        customer = Customer(
            organization_id=org_id,
            first_name=lead.first_name,
            last_name=lead.last_name,
            email=lead.email,
            phone=lead.phone,
            company=lead.company,
            industry=lead.industry,
            country=lead.country,
            notes=lead.notes,
            company_id=company.id if company else None,
            owner_id=owner_id,
        )
        db.add(customer)
    elif customer.company_id is None and company is not None:
        # Enrich, never overwrite: an existing contact only gains the
        # account link when it had none.
        customer.company_id = company.id

    deal = Deal(
        organization_id=org_id,
        title=overrides.deal_title or (lead.company or f"{lead.first_name} {lead.last_name}"),
        value=overrides.deal_value if overrides.deal_value is not None else (lead.budget or 0),
        stage=DealStage.new,
        owner_id=owner_id,
        company_id=company.id if company else None,
    )
    db.add(deal)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise_for_duplicate_email(exc, "customer")

    # Link after the flush so both rows have ids regardless of insert order.
    deal.customer_id = customer.id

    # Same org-scoped bottom-of-column placement as POST /api/deals.
    max_index = (
        await db.execute(
            select(Deal.sort_index)
            .where(
                Deal.organization_id == org_id,
                Deal.stage == deal.stage,
                Deal.id != deal.id,
            )
            .order_by(Deal.sort_index.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    deal.sort_index = (max_index or 0) + 1

    await record_audit(
        db,
        actor=user,
        action="lead.convert",
        entity_type="lead",
        entity_id=lead.id,
        organization_id=org_id,
        metadata={
            "customer_id": customer.id,
            "company_id": company.id if company else None,
            "deal_id": deal.id,
            "customer_existed": customer_existed,
            "company_existed": company_existed,
        },
    )
    conversion_meta = {
        "lead_id": str(lead.id),
        "customer_id": str(customer.id),
        "company_id": str(company.id) if company else None,
        "deal_id": str(deal.id),
    }
    await record_activity(
        db,
        entity_type=ENTITY_LEAD,
        entity_id=lead.id,
        activity_type=ActivityType.lead_converted,
        organization_id=org_id,
        actor=user,
        metadata=conversion_meta,
    )
    await record_activity(
        db,
        entity_type=ENTITY_CUSTOMER,
        entity_id=customer.id,
        activity_type=ActivityType.lead_converted,
        organization_id=org_id,
        actor=user,
        metadata=conversion_meta,
    )
    await record_activity(
        db,
        entity_type=ENTITY_DEAL,
        entity_id=deal.id,
        activity_type=ActivityType.created,
        organization_id=org_id,
        actor=user,
        metadata={"stage": deal.stage.value, "source": "lead_conversion"},
    )
    # Outbox parity with POST /api/deals — automations on deal_created
    # must fire for converted deals too.
    await record_event(
        db,
        event_type=EventType.deal_created,
        organization_id=org_id,
        payload={
            "deal_id": deal.id,
            "owner_id": deal.owner_id,
            "stage": deal.stage.value,
            "source": "lead_conversion",
        },
    )
    # Same parity for the contact: a customer minted by conversion is
    # as "created" as one typed in by hand — but a REUSED contact must
    # not fire a second welcome automation.
    if not customer_existed:
        await record_event(
            db,
            event_type=EventType.customer_created,
            organization_id=org_id,
            payload={
                "customer_id": customer.id,
                "owner_id": customer.owner_id,
                "company_id": customer.company_id,
                "actor_user_id": user.id,
                "source": "lead_conversion",
            },
        )

    await db.commit()
    return LeadConvertOut(
        customer_id=customer.id,
        company_id=company.id if company else None,
        deal_id=deal.id,
        customer_existed=customer_existed,
        company_existed=company_existed,
    )
