import calendar
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import FX_TO_EUR
from app.audit import record_audit
from app.database import get_db
from app.deps import get_current_org_id, get_current_user, require_roles
from app.models import (
    Deal,
    DealStage,
    GoalMetric,
    GoalPeriod,
    Lead,
    LeadStage,
    SalesGoal,
    User,
    UserRole,
)
from app.money import ZERO, q2
from app.schemas import (
    FunnelStage,
    LeaderboardRow,
    PerformanceSummary,
    SalesGoalCreate,
    SalesGoalOut,
    SalesGoalUpdate,
)

router = APIRouter(prefix="/api/performance", tags=["performance"])

# Creating/editing targets shapes how the team is measured, so gate goal
# mutations to admin/manager. The summary and the goal list are read-only
# and open to any member.
manage = require_roles(UserRole.admin, UserRole.manager)


# ----- period math -----------------------------------------------------------
def _period_start_for_today(period: GoalPeriod, today: date) -> date:
    if period == GoalPeriod.month:
        return date(today.year, today.month, 1)
    if period == GoalPeriod.quarter:
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        return date(today.year, q_start_month, 1)
    return date(today.year, 1, 1)


def _period_end(period: GoalPeriod, start: date) -> date:
    """Exclusive end of the window that begins at `start`."""
    months = {GoalPeriod.month: 1, GoalPeriod.quarter: 3, GoalPeriod.year: 12}[period]
    m = start.month - 1 + months
    y = start.year + m // 12
    m = m % 12 + 1
    day = min(start.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def _as_dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _value_eur(value: Decimal | None, currency) -> Decimal:
    return (value or ZERO) * FX_TO_EUR.get(currency.value, Decimal("1"))


# ----- summary ---------------------------------------------------------------
@router.get("/summary", response_model=PerformanceSummary)
async def summary(
    period: GoalPeriod = Query(GoalPeriod.month),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> PerformanceSummary:
    today = datetime.now(timezone.utc).date()
    start = _period_start_for_today(period, today)
    end = _period_end(period, start)
    start_dt, end_dt = _as_dt(start), _as_dt(end)

    # Deals CLOSED in the window. No `won_at`/`lost_at` columns exist, so we
    # approximate the close moment with `updated_at` of a won/lost deal — the
    # stage transition is the last write in the overwhelming majority of cases.
    won_rows = (
        await db.execute(
            select(Deal.value, Deal.currency, Deal.owner_id, Deal.created_at, Deal.updated_at).where(
                Deal.organization_id == org_id,
                Deal.stage == DealStage.won,
                Deal.updated_at >= start_dt,
                Deal.updated_at < end_dt,
            )
        )
    ).all()
    lost_count = (
        await db.execute(
            select(func.count())
            .select_from(Deal)
            .where(
                Deal.organization_id == org_id,
                Deal.stage == DealStage.lost,
                Deal.updated_at >= start_dt,
                Deal.updated_at < end_dt,
            )
        )
    ).scalar_one()

    won_value = ZERO
    won_count = len(won_rows)
    days: list[float] = []
    per_owner: dict[uuid.UUID | None, list[Decimal | int]] = {}
    for value, currency, owner_id, created_at, updated_at in won_rows:
        eur = _value_eur(value, currency)
        won_value += eur
        if created_at is not None and updated_at is not None:
            days.append(max((updated_at - created_at).total_seconds() / 86400.0, 0.0))
        agg = per_owner.setdefault(owner_id, [ZERO, 0])
        agg[0] += eur
        agg[1] += 1

    closed = won_count + lost_count
    win_rate = round(won_count / closed, 4) if closed else 0.0

    # Owner names for the leaderboard (one lookup, not per-row).
    owner_ids = [oid for oid in per_owner if oid is not None]
    names: dict[uuid.UUID, str] = {}
    if owner_ids:
        for uid, full_name in (
            await db.execute(select(User.id, User.full_name).where(User.id.in_(owner_ids)))
        ).all():
            names[uid] = full_name
    leaderboard = sorted(
        (
            LeaderboardRow(
                owner_id=oid,
                owner_name=names.get(oid, "Unassigned") if oid is not None else "Unassigned",
                won_value_eur=float(q2(agg[0])),
                won_count=int(agg[1]),
            )
            for oid, agg in per_owner.items()
        ),
        key=lambda r: r.won_value_eur,
        reverse=True,
    )

    # Lead funnel + conversion (all-time, org-wide — the lead lifecycle isn't
    # naturally bounded by a sales period).
    funnel_counts: dict[str, int] = {s.value: 0 for s in LeadStage}
    total_leads = 0
    for stage, count in (
        await db.execute(
            select(Lead.stage, func.count()).where(Lead.organization_id == org_id).group_by(Lead.stage)
        )
    ).all():
        funnel_counts[stage.value] = count
        total_leads += count
    leads_won = funnel_counts.get(LeadStage.won.value, 0)
    leads_lost = funnel_counts.get(LeadStage.lost.value, 0)
    lead_conversion_rate = round(leads_won / total_leads, 4) if total_leads else 0.0

    avg_days = round(sum(days) / len(days), 1) if days else None
    med = _median(days)

    return PerformanceSummary(
        period=period,
        period_start=start,
        period_end=end,
        won_value_eur=float(q2(won_value)),
        won_count=won_count,
        lost_count=lost_count,
        win_rate=win_rate,
        lead_funnel=[FunnelStage(stage=s.value, count=funnel_counts[s.value]) for s in LeadStage],
        lead_conversion_rate=lead_conversion_rate,
        leads_lost=leads_lost,
        avg_days_to_close=avg_days,
        median_days_to_close=round(med, 1) if med is not None else None,
        leaderboard=leaderboard,
    )


# ----- goals -----------------------------------------------------------------
async def _attainment(db: AsyncSession, org_id: uuid.UUID, goal: SalesGoal) -> tuple[float, float]:
    """Achieved-so-far against a goal's own window + scope."""
    end = _period_end(goal.period, goal.period_start)
    start_dt, end_dt = _as_dt(goal.period_start), _as_dt(end)
    stmt = select(Deal.value, Deal.currency).where(
        Deal.organization_id == org_id,
        Deal.stage == DealStage.won,
        Deal.updated_at >= start_dt,
        Deal.updated_at < end_dt,
    )
    if goal.owner_id is not None:
        stmt = stmt.where(Deal.owner_id == goal.owner_id)
    if goal.team_id is not None:
        stmt = stmt.where(Deal.team_id == goal.team_id)
    rows = (await db.execute(stmt)).all()
    if goal.metric == GoalMetric.revenue:
        achieved = float(q2(sum((_value_eur(v, c) for v, c in rows), ZERO)))
    else:
        achieved = float(len(rows))
    target = float(goal.target)
    pct = round(achieved / target, 4) if target else 0.0
    return achieved, pct


async def _goal_out(db: AsyncSession, org_id: uuid.UUID, goal: SalesGoal) -> SalesGoalOut:
    achieved, pct = await _attainment(db, org_id, goal)
    return SalesGoalOut(
        id=goal.id,
        owner_id=goal.owner_id,
        team_id=goal.team_id,
        period=goal.period,
        period_start=goal.period_start,
        metric=goal.metric,
        target=float(goal.target),
        attainment=achieved,
        attainment_pct=pct,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


async def _get_goal_or_404(db: AsyncSession, goal_id: uuid.UUID, org_id: uuid.UUID) -> SalesGoal:
    goal = (
        await db.execute(
            select(SalesGoal).where(SalesGoal.id == goal_id, SalesGoal.organization_id == org_id)
        )
    ).scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.get("/goals", response_model=list[SalesGoalOut])
async def list_goals(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[SalesGoalOut]:
    goals = (
        await db.execute(
            select(SalesGoal)
            .where(SalesGoal.organization_id == org_id)
            .order_by(SalesGoal.period_start.desc(), SalesGoal.created_at.desc())
        )
    ).scalars().all()
    return [await _goal_out(db, org_id, g) for g in goals]


@router.post("/goals", response_model=SalesGoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: SalesGoalCreate,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> SalesGoalOut:
    goal = SalesGoal(**payload.model_dump(), organization_id=org_id)
    db.add(goal)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="sales_goal.create",
        entity_type="sales_goal",
        entity_id=goal.id,
        organization_id=org_id,
        metadata={"metric": goal.metric.value, "period": goal.period.value},
    )
    await db.commit()
    await db.refresh(goal)
    return await _goal_out(db, org_id, goal)


@router.patch("/goals/{goal_id}", response_model=SalesGoalOut)
async def update_goal(
    goal_id: uuid.UUID,
    payload: SalesGoalUpdate,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> SalesGoalOut:
    goal = await _get_goal_or_404(db, goal_id, org_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(goal, field, value)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="sales_goal.update",
        entity_type="sales_goal",
        entity_id=goal.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await db.refresh(goal)
    return await _goal_out(db, org_id, goal)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: uuid.UUID,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    goal = await _get_goal_or_404(db, goal_id, org_id)
    await db.delete(goal)
    await record_audit(
        db,
        actor=user,
        action="sales_goal.delete",
        entity_type="sales_goal",
        entity_id=goal_id,
        organization_id=org_id,
    )
    await db.commit()
