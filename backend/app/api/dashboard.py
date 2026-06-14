import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.models import (
    Customer,
    Deal,
    DealStage,
    Lead,
    LeadStage,
    Quote,
    QuoteStatus,
    Task,
    TaskStatus,
    User,
)
from app.money import ZERO, q2
from app.redis_client import get_redis
from app.schemas import DashboardStats, FunnelStageStat, HojeResponse, MonthValue, QuotesSummary
from app.services import fx

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_CACHE_TTL = 60  # seconds — stale stats for at most 1 minute is fine for a dashboard


async def invalidate_dashboard_cache(org_id: uuid.UUID) -> None:
    """Best-effort cache bust — called by mutation endpoints in leads/deals/customers/tasks."""
    try:
        await get_redis().delete(f"dashboard:stats:{org_id}")
    except Exception:
        pass


# EUR conversion now comes from `app.services.fx` (live ECB rates, refreshed
# by the `refresh_fx_rates` worker cron, with a static fallback when the
# table is empty). The headline aggregates stay EUR-canonical; the response
# also carries the rate set + as-of date so the frontend can display-convert.
CLOSED_DEAL_STAGES = {DealStage.won, DealStage.lost}

# Funnel stages shown on the dashboard (ordered; lost excluded).
FUNNEL_STAGES = [
    DealStage.new,
    DealStage.qualified,
    DealStage.proposal_sent,
    DealStage.negotiation,
    DealStage.won,
]


@router.get("/stats", response_model=DashboardStats)
async def stats(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> DashboardStats:
    # Serve from Redis cache when available — 60s TTL means at most one
    # DB round-trip per org per minute instead of one per page load.
    cache_key = f"dashboard:stats:{org_id}"
    r = get_redis()
    try:
        cached = await r.get(cache_key)
        if cached:
            return DashboardStats.model_validate_json(cached)
    except Exception:
        pass  # Redis miss or error — fall through to DB

    # Live EUR conversion multipliers (amount-in-ccy → EUR), plus provenance
    # for the response. One snapshot reused across every aggregate below.
    fx_snap = await fx.get_snapshot(db)
    fx_mult = fx_snap.to_eur_multipliers()

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
    # Raw per-currency sums alongside the EUR approximation (plan.md §6:
    # display-only, no conversion) — the widget shows "what you actually
    # have" when the pipeline spans currencies.
    pipeline_by_currency: dict[str, Decimal] = {}
    for value, currency in open_deals:
        pipeline_value += (value or ZERO) * fx_mult.get(currency.value, Decimal("1"))
        pipeline_by_currency[currency.value] = pipeline_by_currency.get(currency.value, ZERO) + (
            value or ZERO
        )

    # Pipeline funnel — count + EUR value per stage (lost excluded).
    funnel_rows = (
        await db.execute(
            select(Deal.stage, Deal.value, Deal.currency).where(
                Deal.organization_id == org_id,
                Deal.stage.in_(FUNNEL_STAGES),
            )
        )
    ).all()
    funnel_count: dict[DealStage, int] = {s: 0 for s in FUNNEL_STAGES}
    funnel_value: dict[DealStage, Decimal] = {s: ZERO for s in FUNNEL_STAGES}
    for stage, value, currency in funnel_rows:
        funnel_count[stage] += 1
        funnel_value[stage] += (value or ZERO) * fx_mult.get(currency.value, Decimal("1"))
    pipeline_funnel = [
        FunnelStageStat(stage=s.value, count=funnel_count[s], value_eur=float(q2(funnel_value[s])))
        for s in FUNNEL_STAGES
    ]

    # Monthly revenue — won deals by month (last 12 months) + total.
    won_rows = (
        await db.execute(
            select(Deal.value, Deal.currency, Deal.updated_at).where(
                Deal.organization_id == org_id, Deal.stage == DealStage.won
            )
        )
    ).all()
    now = datetime.now(UTC)
    month_keys: list[str] = []
    yy, mm = now.year, now.month
    for _ in range(12):
        month_keys.append(f"{yy:04d}-{mm:02d}")
        mm -= 1
        if mm == 0:
            mm = 12
            yy -= 1
    month_keys.reverse()
    rev_by_month: dict[str, Decimal] = {k: ZERO for k in month_keys}
    revenue_total = ZERO
    for value, currency, updated in won_rows:
        eur_val = (value or ZERO) * fx_mult.get(currency.value, Decimal("1"))
        revenue_total += eur_val
        key = f"{updated.year:04d}-{updated.month:02d}"
        if key in rev_by_month:
            rev_by_month[key] += eur_val
    monthly_revenue = [
        MonthValue(month=k, value_eur=float(q2(rev_by_month[k]))) for k in month_keys
    ]

    # Quotes summary — value by status + open/overdue (sent, by valid_until).
    quote_rows = (
        await db.execute(
            select(Quote.status, Quote.total, Quote.currency, Quote.valid_until).where(
                Quote.organization_id == org_id
            )
        )
    ).all()
    today = now.date()
    q_total = q_out = q_acc = q_rej = q_open = q_overdue = ZERO
    for status, total, currency, valid_until in quote_rows:
        eur_val = (total or ZERO) * fx_mult.get(currency.value, Decimal("1"))
        q_total += eur_val
        if status in (QuoteStatus.draft, QuoteStatus.sent):
            q_out += eur_val
        elif status == QuoteStatus.accepted:
            q_acc += eur_val
        elif status in (QuoteStatus.declined, QuoteStatus.expired):
            q_rej += eur_val
        if status == QuoteStatus.sent:
            if valid_until is not None and valid_until < today:
                q_overdue += eur_val
            else:
                q_open += eur_val
    quotes_summary = QuotesSummary(
        total_eur=float(q2(q_total)),
        outstanding_eur=float(q2(q_out)),
        accepted_eur=float(q2(q_acc)),
        rejected_eur=float(q2(q_rej)),
        open_eur=float(q2(q_open)),
        overdue_eur=float(q2(q_overdue)),
    )

    result = DashboardStats(
        total_leads=total_leads,
        leads_by_stage=by_stage,
        won_count=won,
        lost_count=lost,
        conversion_rate=conversion_rate,
        avg_ai_score=float(avg_score) if avg_score is not None else None,
        total_customers=total_customers,
        total_deals=total_deals,
        pipeline_value_eur=float(q2(pipeline_value)),
        pipeline_value_by_currency={
            k: float(q2(v)) for k, v in sorted(pipeline_by_currency.items())
        },
        open_tasks=open_tasks,
        pipeline_funnel=pipeline_funnel,
        monthly_revenue=monthly_revenue,
        revenue_total_eur=float(q2(revenue_total)),
        quotes=quotes_summary,
        fx_rates={k: float(v) for k, v in fx_snap.rates.items()},
        fx_as_of=fx_snap.as_of,
        fx_source=fx_snap.source,
    )
    try:
        await r.set(cache_key, result.model_dump_json(), ex=_CACHE_TTL)
    except Exception:
        pass  # best-effort cache write
    return result


def _deal_to_today_item(row: Deal, customer_name: str | None) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "value": float(row.value),
        "currency": row.currency.value if row.currency else "EUR",
        "stage": row.stage,
        "next_action_type": row.next_action_type,
        "next_action_at": row.next_action_at,
        "customer_name": customer_name,
        "owner_id": row.owner_id,
        "version": row.version,
    }


@router.get("/hoje", response_model=HojeResponse)
async def get_hoje(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> HojeResponse:
    now = datetime.now(UTC)
    today_start = datetime.combine(now.date(), time.min).replace(tzinfo=UTC)
    today_end = datetime.combine(now.date(), time.max).replace(tzinfo=UTC)
    stale_cutoff = now - timedelta(days=7)
    open_stages = [DealStage.won, DealStage.lost]

    base_q = (
        select(Deal, Customer.first_name, Customer.last_name)
        .outerjoin(Customer, Deal.customer_id == Customer.id)
        .where(Deal.organization_id == org_id, Deal.stage.notin_(open_stages))
    )

    async def _fetch_deals(stmt) -> list[dict]:
        rows = (await db.execute(stmt.order_by(Deal.next_action_at.asc().nullslast()))).all()
        result = []
        for deal, first, last in rows:
            name = " ".join(filter(None, [first, last])) or None
            result.append(_deal_to_today_item(deal, name))
        return result

    overdue_deals = await _fetch_deals(base_q.where(Deal.next_action_at < now))
    today_deals = await _fetch_deals(
        base_q.where(Deal.next_action_at.between(today_start, today_end))
    )
    no_action_deals = await _fetch_deals(base_q.where(Deal.next_action_at.is_(None)))
    stale_deals = await _fetch_deals(
        base_q.where(Deal.next_action_at.is_(None), Deal.updated_at < stale_cutoff)
    )

    task_base = select(Task).where(Task.organization_id == org_id, Task.status != TaskStatus.done)
    today_task_rows = (
        (
            await db.execute(
                task_base.where(Task.due_date == now.date()).order_by(Task.due_date.asc())
            )
        )
        .scalars()
        .all()
    )
    overdue_task_rows = (
        (
            await db.execute(
                task_base.where(Task.due_date < now.date()).order_by(Task.due_date.asc())
            )
        )
        .scalars()
        .all()
    )

    def _task_item(t: Task) -> dict:
        return {
            "id": t.id,
            "title": t.title,
            "due_date": t.due_date,
            "priority": t.priority,
            "customer_name": None,
            "version": t.version,
        }

    return HojeResponse(
        overdue_deals=overdue_deals,
        today_deals=today_deals,
        no_action_deals=no_action_deals,
        stale_deals=stale_deals,
        today_tasks=[_task_item(t) for t in today_task_rows],
        overdue_tasks=[_task_item(t) for t in overdue_task_rows],
    )
