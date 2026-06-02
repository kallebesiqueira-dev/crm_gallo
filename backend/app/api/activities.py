"""User-facing activity-timeline query API.

Activities themselves are written by `app.activities.record_activity`
on every meaningful mutation; this module exposes them for the lead /
customer / deal detail pages to render the timeline.

Read-only — there's no public `POST /api/activities` because every
activity is a side-effect of a domain mutation that has its own
endpoint. (A future "manual log" feature like "I called this lead
on Tuesday" would warrant a write endpoint and would map to
`ActivityType.call`.)

Org-scoped via `get_current_org_id`. Inherent RLS scope kicks in
through the GUC the dep sets, but we also filter explicitly so the
generated SQL stays readable + the index `idx_activities_entity_created`
is fully usable.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.models import Activity, User
from app.schemas import ActivityOut

router = APIRouter(prefix="/api/activities", tags=["activities"])


# Anchor to the known entity vocabulary so a typo doesn't quietly
# return an empty list. `Literal` makes FastAPI emit it as an enum
# in OpenAPI too.
EntityType = Literal["lead", "customer", "deal"]


@router.get("", response_model=list[ActivityOut])
async def list_activities(
    entity_type: EntityType,
    entity_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityOut]:
    """Return the activity timeline for a single entity, newest
    first. Org-scoped — a foreign-org `entity_id` simply returns an
    empty list (we don't 404 because the entity itself might not
    exist; the caller already had to find the id from somewhere)."""
    actor = aliased(User)
    stmt = (
        select(Activity, actor.email, actor.full_name)
        .outerjoin(actor, actor.id == Activity.actor_user_id)
        .where(
            Activity.organization_id == org_id,
            Activity.entity_type == entity_type,
            Activity.entity_id == entity_id,
        )
        .order_by(desc(Activity.created_at), desc(Activity.id))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    out: list[ActivityOut] = []
    for activity, email, name in result.all():
        out.append(
            ActivityOut(
                id=activity.id,
                entity_type=activity.entity_type,
                entity_id=activity.entity_id,
                type=activity.type,
                content=activity.content,
                metadata_json=activity.metadata_json,
                actor_user_id=activity.actor_user_id,
                actor_email=email,
                actor_name=name,
                created_at=activity.created_at,
            )
        )
    return out
