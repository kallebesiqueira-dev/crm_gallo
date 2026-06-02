import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.models import Customer, Deal, DealStage, Lead, LeadStage, Task, TaskStatus, User
from app.money import ZERO, q2
from app.schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Rough conversion to EUR for quick pipeline-value approximation.
# In production, fetch live rates and persist them. Decimal so the
# Numeric deal values (also Decimal) multiply without a float mix.
FX_TO_EUR = {
    "EUR": Decimal("1"),
    "CHF": Decimal("1.04"),
    "USD": Decimal("0.93"),
    "GBP": Decimal("1.17"),
}

CLOSED_DEAL_STAGES = {DealStage.won, DealStage.lost}


@router.get("/stats", response_model=DashboardStats)
async def stats(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> DashboardStats:
    # Every aggregate filters by the current org — without it the dashboard
    # would leak counts across tenants (a tiny but real existence leak:
    # "this install has 12k leads" tells you something about other orgs).
    total_leads = (
        await db.execute(
            select(func.count()).select_from(Lead).where(Lead.organization_id == org_id)
        )
    ).scalar_one()

    by_stage_result = await db.execute(
        select(Lead.stage, func.count()).where(Lead.organization_id == org_id).group_by(Lead.stage)
    )
    by_stage: dict[str, int] = {s.value: 0 for s in LeadStage}
    for stage, count in by_stage_result.all():
        by_stage[stage.value] = count

    won = by_stage.get(LeadStage.won.value, 0)
    lost = by_stage.get(LeadStage.lost.value, 0)
    closed = won + lost
    conversion_rate = round(won / closed, 4) if closed else 0.0

    avg_score = (
        await db.execute(select(func.avg(Lead.ai_score)).where(Lead.organization_id == org_id))
    ).scalar_one()

    total_customers = (
        await db.execute(
            select(func.count()).select_from(Customer).where(Customer.organization_id == org_id)
        )
    ).scalar_one()
    total_deals = (
        await db.execute(
            select(func.count()).select_from(Deal).where(Deal.organization_id == org_id)
        )
    ).scalar_one()
    open_tasks = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.organization_id == org_id,
                Task.status != TaskStatus.done,
            )
        )
    ).scalar_one()

    # Pipeline value = OPEN deals only (exclude won/lost).
    open_deals = (
        await db.execute(
            select(Deal.value, Deal.currency).where(
                Deal.organization_id == org_id,
                Deal.stage.notin_(CLOSED_DEAL_STAGES),
            )
        )
    ).all()
    pipeline_value = ZERO
    for value, currency in open_deals:
        pipeline_value += (value or ZERO) * FX_TO_EUR.get(currency.value, Decimal("1"))

    return DashboardStats(
        total_leads=total_leads,
        leads_by_stage=by_stage,
        won_count=won,
        lost_count=lost,
        conversion_rate=conversion_rate,
        avg_ai_score=float(avg_score) if avg_score is not None else None,
        total_customers=total_customers,
        total_deals=total_deals,
        pipeline_value_eur=float(q2(pipeline_value)),
        open_tasks=open_tasks,
    )
