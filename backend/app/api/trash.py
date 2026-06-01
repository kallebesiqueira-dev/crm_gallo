"""Trash bin: list, restore, or permanently delete soft-deleted records."""

import uuid
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import (
    PRIVILEGED_ROLES,
    ensure_can_mutate,
    get_current_org_id,
    get_current_user,
    is_privileged,
    require_roles,
)
from app.models import Customer, Deal, Lead, Task, User, UserRole

router = APIRouter(prefix="/api/trash", tags=["trash"])

# `include_deleted=True` opts a SELECT out of the global SoftDeleteMixin
# filter wired in database.py. The trash routes are the only callers
# that need to see deleted rows — every other surface gets the
# auto-exclude for free. We still narrow with `deleted_at IS NOT NULL`
# below: this opt-out turns OFF the implicit `deleted_at IS NULL`
# clause but doesn't ADD `deleted_at IS NOT NULL` (that's our intent).
_SHOW_DELETED = {"include_deleted": True}

EntityType = Literal["lead", "customer", "deal", "task"]

_MODELS: dict[EntityType, type] = {
    "lead": Lead,
    "customer": Customer,
    "deal": Deal,
    "task": Task,
}


def _ownership_column(model):
    """Tasks key off assignee, the rest off owner."""
    return getattr(model, "assignee_id", None) or model.owner_id


class TrashItem(BaseModel):
    id: uuid.UUID
    entity_type: EntityType
    title: str
    deleted_at: str


class TrashCounts(BaseModel):
    lead: int
    customer: int
    deal: int
    task: int


def _title_for(entity_type: str, row) -> str:
    if entity_type in {"lead", "customer"}:
        return f"{row.first_name} {row.last_name}"
    return row.title


def _row_owner(row, kind: str) -> uuid.UUID | None:
    if kind == "task":
        return getattr(row, "assignee_id", None)
    return getattr(row, "owner_id", None)


@router.get("", response_model=list[TrashItem])
async def list_trash(
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[TrashItem]:
    items: list[TrashItem] = []
    for kind, model in _MODELS.items():
        stmt = (
            select(model)
            .where(model.organization_id == org_id, model.deleted_at.is_not(None))
            .execution_options(**_SHOW_DELETED)
        )
        if not is_privileged(user):
            owner_col = _ownership_column(model)
            stmt = stmt.where(owner_col == user.id)
        stmt = stmt.order_by(model.deleted_at.desc())
        result = await db.execute(stmt)
        for row in result.scalars().all():
            items.append(
                TrashItem(
                    id=row.id,
                    entity_type=cast(EntityType, kind),
                    title=_title_for(kind, row),
                    deleted_at=row.deleted_at.isoformat() if row.deleted_at else "",
                )
            )
    items.sort(key=lambda t: t.deleted_at, reverse=True)
    return items


@router.get("/counts", response_model=TrashCounts)
async def counts(
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> TrashCounts:
    result: dict[str, int] = {}
    for kind, model in _MODELS.items():
        stmt = (
            select(func.count())
            .select_from(model)
            .where(model.organization_id == org_id, model.deleted_at.is_not(None))
            .execution_options(**_SHOW_DELETED)
        )
        if not is_privileged(user):
            owner_col = _ownership_column(model)
            stmt = stmt.where(owner_col == user.id)
        n = (await db.execute(stmt)).scalar_one()
        result[kind] = n
    return TrashCounts(**result)


async def _get_trashed_or_404(db, model, entity_id, org_id):
    """Org-scoped fetch of a soft-deleted row, else 404."""
    result = await db.execute(
        select(model)
        .where(
            model.id == entity_id,
            model.organization_id == org_id,
            model.deleted_at.is_not(None),
        )
        .execution_options(**_SHOW_DELETED)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Not found in trash")
    return row


@router.post("/{entity_type}/{entity_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore(
    entity_type: EntityType,
    entity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    model = _MODELS.get(entity_type)
    if not model:
        raise HTTPException(status_code=400, detail="Invalid entity type")
    row = await _get_trashed_or_404(db, model, entity_id, org_id)
    ensure_can_mutate(user, _row_owner(row, entity_type))
    row.deleted_at = None
    await record_audit(
        db,
        actor=user,
        action=f"{entity_type}.restore",
        entity_type=entity_type,
        entity_id=row.id,
        organization_id=org_id,
    )
    await db.commit()


@router.delete("/{entity_type}/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def hard_delete(
    entity_type: EntityType,
    entity_id: uuid.UUID,
    user: User = Depends(require_roles(*PRIVILEGED_ROLES)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    model = _MODELS.get(entity_type)
    if not model:
        raise HTTPException(status_code=400, detail="Invalid entity type")
    row = await _get_trashed_or_404(db, model, entity_id, org_id)
    await record_audit(
        db,
        actor=user,
        action=f"{entity_type}.hard_delete",
        entity_type=entity_type,
        entity_id=row.id,
        organization_id=org_id,
    )
    await db.delete(row)
    await db.commit()


@router.post("/empty", status_code=status.HTTP_204_NO_CONTENT)
async def empty_trash(
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Admin-only nuclear option: permanently delete every soft-deleted record
    in the current organization. Other orgs' trash is unaffected."""
    purged: dict[str, int] = {}
    for kind, model in _MODELS.items():
        result = await db.execute(
            select(model)
            .where(model.organization_id == org_id, model.deleted_at.is_not(None))
            .execution_options(**_SHOW_DELETED)
        )
        rows = list(result.scalars().all())
        purged[kind] = len(rows)
        for row in rows:
            await db.delete(row)
    await record_audit(
        db,
        actor=user,
        action="trash.empty",
        entity_type="trash",
        organization_id=org_id,
        metadata=purged,
    )
    await db.commit()
