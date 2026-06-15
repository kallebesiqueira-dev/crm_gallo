"""LLM usage / cost observability — admin-facing, per-org.

Read-only aggregates over `llm_usage` rows for the current org (RLS scopes
them). Gated to admin/manager since spend data is operationally sensitive.
Rows are written best-effort by `app.services.llm_usage.persist_usage` at the
blocking LLM call sites (lead scoring, customer summary).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_org_id, get_current_user, require_roles
from app.models import LlmUsage, User, UserRole
from app.schemas import AiCreditStatus, LlmUsageSummary, LlmUsageUseCaseStat
from app.services import ai_credits

router = APIRouter(prefix="/api/llm-usage", tags=["llm-usage"])


@router.get("/summary", response_model=LlmUsageSummary)
async def usage_summary(
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> LlmUsageSummary:
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    rows = (
        await db.execute(
            select(
                LlmUsage.use_case,
                func.count().label("calls"),
                func.coalesce(func.sum(LlmUsage.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(LlmUsage.output_tokens), 0).label("output_tokens"),
            )
            .where(LlmUsage.organization_id == org_id, LlmUsage.created_at >= cutoff)
            .group_by(LlmUsage.use_case)
            .order_by(func.count().desc())
        )
    ).all()

    by_use_case = [
        LlmUsageUseCaseStat(
            use_case=r.use_case,
            calls=r.calls,
            input_tokens=int(r.input_tokens),
            output_tokens=int(r.output_tokens),
        )
        for r in rows
    ]
    return LlmUsageSummary(
        window_days=window_days,
        total_calls=sum(s.calls for s in by_use_case),
        total_input_tokens=sum(s.input_tokens for s in by_use_case),
        total_output_tokens=sum(s.output_tokens for s in by_use_case),
        by_use_case=by_use_case,
    )


@router.get("/credits", response_model=AiCreditStatus)
async def ai_credit_status(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> AiCreditStatus:
    """Current-month AI-credit usage for the caller's org (1 credit = 1 AI
    action) — powers the usage meter. Open to any member."""
    return AiCreditStatus(**await ai_credits.credit_status(db, org_id))
