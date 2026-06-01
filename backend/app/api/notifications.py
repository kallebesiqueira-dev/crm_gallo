"""Per-user notification inbox.

Surface:
  * GET    /api/notifications?unread=true|false                list
  * GET    /api/notifications/counts                           bell badge
  * POST   /api/notifications/{id}/read                        mark one read
  * POST   /api/notifications/mark-all-read                    bulk
  * DELETE /api/notifications/{id}                             dismiss

Everything is scoped to the authenticated user (NOT the org); a
user with memberships in multiple orgs still gets a unified bell.
We filter by `organization_id == current_org_id` too so a user
who switches orgs only sees bell items relevant to the active
workspace — multi-org bell unification is a P3 product call.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.models import Notification, User
from app.schemas import NotificationCounts, NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _serialize(n: Notification, name: str | None) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        type=n.type,
        title=n.title,
        body=n.body,
        link_url=n.link_url,
        metadata_json=n.metadata_json,
        actor_user_id=n.actor_user_id,
        actor_name=name,
        read_at=n.read_at,
        created_at=n.created_at,
    )


async def _get_or_404(
    db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID
) -> Notification:
    """User-scoped fetch — 404 (not 403) when targeting someone
    else's notification so the URL space doesn't leak."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    n = result.scalar_one_or_none()
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return n


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    unread: bool | None = Query(
        default=None,
        description="true = unread only, false = read only, omit = both",
    ),
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationOut]:
    actor = aliased(User)
    stmt = (
        select(Notification, actor.full_name)
        .outerjoin(actor, actor.id == Notification.actor_user_id)
        .where(
            Notification.user_id == user.id,
            Notification.organization_id == org_id,
        )
        .order_by(desc(Notification.created_at), desc(Notification.id))
        .limit(limit)
        .offset(offset)
    )
    if unread is True:
        stmt = stmt.where(Notification.read_at.is_(None))
    elif unread is False:
        stmt = stmt.where(Notification.read_at.is_not(None))
    result = await db.execute(stmt)
    return [_serialize(n, name) for n, name in result.all()]


@router.get("/counts", response_model=NotificationCounts)
async def notification_counts(
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> NotificationCounts:
    """Bell-badge endpoint. Cheap COUNT against the partial unread
    index — the SPA can poll this every N seconds without burning
    bandwidth on the full list."""
    n = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.organization_id == org_id,
                Notification.read_at.is_(None),
            )
        )
    ).scalar_one()
    return NotificationCounts(unread=n)


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> NotificationOut:
    n = await _get_or_404(db, notification_id, user.id)
    # No-op if already read so re-clicking doesn't drift the
    # timestamp.
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(n)
    actor_name = None
    if n.actor_user_id is not None:
        actor = await db.get(User, n.actor_user_id)
        actor_name = actor.full_name if actor else None
    return _serialize(n, actor_name)


@router.post("/mark-all-read", response_model=NotificationCounts)
async def mark_all_read(
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> NotificationCounts:
    """Zero out the bell for the active org. Returns the new counts
    so the SPA can avoid a follow-up `/counts` call."""
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.organization_id == org_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()
    return NotificationCounts(unread=0)


# Skip `-> None` annotation on the 204 (see notes.delete_note's
# comment for the FastAPI + future-annotations interaction).
@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    n = await _get_or_404(db, notification_id, user.id)
    await db.delete(n)
    await db.commit()
