"""AI-credit enforcement (plan quota on user-facing AI actions).

Model (decided with the owner): **1 credit = 1 AI action**. An org's monthly
allowance comes from its plan (`catalog.ai_credits`; None = unlimited). Usage
is counted straight off the `llm_usage` rows for the current calendar month —
no separate counter to keep in sync. The window resets on the 1st (UTC).

Only **user-initiated** actions are gated (manual lead scoring, the assistant,
customer summaries). Background re-scoring in the worker is NOT gated, so
automations never break silently.

`ensure_credits` raises 402 when the allowance is spent; `credit_status`
powers the usage meter (`GET /api/llm-usage/credits`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.catalog import get_plan
from app.models import LlmUsage, Organization


def _period_start(now: datetime | None = None) -> datetime:
    n = now or datetime.now(UTC)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_period_start(now: datetime | None = None) -> datetime:
    s = _period_start(now)
    return s.replace(year=s.year + 1, month=1) if s.month == 12 else s.replace(month=s.month + 1)


async def _plan_limit(db: AsyncSession, org_id: uuid.UUID) -> int | None:
    """Monthly AI-credit allowance for the org's plan. None = unlimited (or
    unknown org — never block on a missing org)."""
    plan = (
        await db.execute(select(Organization.plan).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if plan is None:
        return None
    return get_plan(plan).ai_credits


async def _used_this_period(db: AsyncSession, org_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(LlmUsage)
            .where(
                LlmUsage.organization_id == org_id,
                LlmUsage.created_at >= _period_start(),
            )
        )
    ).scalar_one()


async def credit_status(db: AsyncSession, org_id: uuid.UUID) -> dict:
    """Current-month AI-credit usage for the org — feeds the UI meter."""
    limit = await _plan_limit(db, org_id)
    used = await _used_this_period(db, org_id)
    unlimited = limit is None
    return {
        "used": used,
        "limit": limit,
        "remaining": None if unlimited else max(0, limit - used),
        "unlimited": unlimited,
        "resets_at": _next_period_start(),
    }


async def ensure_credits(db: AsyncSession, org_id: uuid.UUID) -> None:
    """Raise 402 when the org has spent its monthly AI allowance. No-op for
    unlimited plans. Call BEFORE a user-initiated LLM action."""
    limit = await _plan_limit(db, org_id)
    if limit is None:
        return
    if await _used_this_period(db, org_id) >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Monthly AI credits exhausted for your plan — upgrade for more.",
        )
