"""Admin-only outbox inspection API (ADR-007).

Read-only window into the `outbox_events` table for ops triage:
  * `status=pending` — unprocessed AND under the retry cap (still flying)
  * `status=failed`  — unprocessed AND at the retry cap (DLQ-flagged)
  * `status=processed` — already delivered
  * unset → everything, newest first

Org-scoped: only rows whose `organization_id` matches the caller's
current org (platform events with `organization_id IS NULL` are
intentionally NOT returned here — that surface belongs to a future
platform-admin tool, not the tenant-admin UI).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_org_id, require_roles
from app.events import OUTBOX_MAX_ATTEMPTS
from app.models import OutboxEvent, User, UserRole
from app.schemas import OutboxEventOut

router = APIRouter(prefix="/api/outbox", tags=["outbox"])


@router.get("", response_model=list[OutboxEventOut])
async def list_outbox(
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    status: (
        Annotated[Literal["pending", "failed", "processed"], Query()] | None
    ) = None,
    event_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    # Admin OR manager — outbox is operationally close to audit:
    # someone has to be able to see "why didn't my webhook fire?"
    # without bumping to platform admin.
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[OutboxEventOut]:
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.organization_id == org_id)
        .order_by(desc(OutboxEvent.occurred_at), desc(OutboxEvent.id))
        .limit(limit)
        .offset(offset)
    )
    if status == "pending":
        stmt = stmt.where(
            OutboxEvent.processed_at.is_(None),
            OutboxEvent.attempt_count < OUTBOX_MAX_ATTEMPTS,
        )
    elif status == "failed":
        stmt = stmt.where(
            OutboxEvent.processed_at.is_(None),
            OutboxEvent.attempt_count >= OUTBOX_MAX_ATTEMPTS,
        )
    elif status == "processed":
        stmt = stmt.where(OutboxEvent.processed_at.is_not(None))
    if event_type:
        stmt = stmt.where(OutboxEvent.event_type == event_type)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        OutboxEventOut(
            id=r.id,
            organization_id=r.organization_id,
            event_type=r.event_type,
            payload=r.payload,
            occurred_at=r.occurred_at,
            processed_at=r.processed_at,
            attempt_count=r.attempt_count,
            last_error=r.last_error,
        )
        for r in rows
    ]
