"""Admin-only audit log query API.

The audit ledger itself is written by `app.audit.record_audit` on
every mutation; this module exposes it for the admin UI to browse.
Org-scoped: each call is filtered by the caller's current
organization (system events with `organization_id IS NULL` are
visible too, since they relate to the org's users — login,
password resets, MFA enrollment).

Filters: `actor_id`, `action`, `entity_type`, `since`, `until`.
Cursor-style pagination would be ideal but limit/offset is good
enough for a log a human eyeballs; we cap `limit` at 200 to bound
the response size.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database import get_db
from app.deps import get_current_org_id, require_roles
from app.models import AuditLog, OrgMembership, User, UserRole
from app.schemas import AuditLogOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
async def list_audit(
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    # Admin OR manager: managers run a lot of the day-to-day moderation
    # so they need visibility into who did what. Pure sales_agent users
    # do NOT see the ledger — it includes other people's actions in
    # the org and isn't theirs to inspect.
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
) -> list[AuditLogOut]:
    # Members-of-this-org subquery — used to widen the filter to
    # include system audit rows (org_id IS NULL) whose actor belongs
    # to this org. Captures user.login, user.password_reset,
    # user.mfa_enabled, etc. — events that have no org context server-
    # side but are clearly attributable to one of THIS org's users.
    org_member_ids = select(OrgMembership.user_id).where(OrgMembership.organization_id == org_id)
    actor = aliased(User)
    stmt = (
        select(AuditLog, actor.email, actor.full_name)
        .outerjoin(actor, actor.id == AuditLog.actor_id)
        .where(
            (AuditLog.organization_id == org_id)
            | (AuditLog.organization_id.is_(None) & AuditLog.actor_id.in_(org_member_ids))
        )
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(limit)
        .offset(offset)
    )

    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action:
        # ILIKE for substring match on the action vocabulary
        # ("lead.create", "user.login", etc) — admins typically
        # remember the prefix.
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if since:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until:
        stmt = stmt.where(AuditLog.created_at <= until)

    result = await db.execute(stmt)
    out: list[AuditLogOut] = []
    for row in result.all():
        audit, email, name = row
        out.append(
            AuditLogOut(
                id=audit.id,
                organization_id=audit.organization_id,
                actor_id=audit.actor_id,
                actor_email=email,
                actor_name=name,
                action=audit.action,
                entity_type=audit.entity_type,
                entity_id=audit.entity_id,
                metadata_json=audit.metadata_json,
                created_at=audit.created_at,
            )
        )
    return out
