import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.custom_fields import ENTITY_TYPES
from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.models import SavedSegment, User
from app.schemas import SegmentCreate, SegmentOut, SegmentUpdate

router = APIRouter(prefix="/api/segments", tags=["segments"])


def _validate_entity_type(entity_type: str) -> None:
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="Unknown entity_type")


async def _get_or_404(db: AsyncSession, segment_id: uuid.UUID, org_id: uuid.UUID) -> SavedSegment:
    result = await db.execute(
        select(SavedSegment).where(
            SavedSegment.id == segment_id,
            SavedSegment.organization_id == org_id,
        )
    )
    seg = result.scalar_one_or_none()
    if not seg or seg.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Segment not found")
    return seg


@router.get("", response_model=list[SegmentOut])
async def list_segments(
    entity_type: str | None = Query(default=None),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[SavedSegment]:
    stmt = select(SavedSegment).where(SavedSegment.organization_id == org_id)
    if entity_type is not None:
        _validate_entity_type(entity_type)
        stmt = stmt.where(SavedSegment.entity_type == entity_type)
    stmt = stmt.order_by(SavedSegment.entity_type.asc(), SavedSegment.name.asc())
    return list((await db.execute(stmt)).scalars().all())


@router.post("", response_model=SegmentOut, status_code=status.HTTP_201_CREATED)
async def create_segment(
    payload: SegmentCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> SavedSegment:
    seg = SavedSegment(
        **payload.model_dump(),
        organization_id=org_id,
        created_by_id=user.id,
    )
    db.add(seg)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="segment.create",
        entity_type="saved_segment",
        entity_id=seg.id,
        organization_id=org_id,
        metadata={"entity_type": seg.entity_type, "name": seg.name},
    )
    await db.commit()
    await db.refresh(seg)
    return seg


@router.patch("/{segment_id}", response_model=SegmentOut)
async def update_segment(
    segment_id: uuid.UUID,
    payload: SegmentUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> SavedSegment:
    seg = await _get_or_404(db, segment_id, org_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(seg, field, value)
    await record_audit(
        db,
        actor=user,
        action="segment.update",
        entity_type="saved_segment",
        entity_id=seg.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await db.refresh(seg)
    return seg


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segment(
    segment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    seg = await _get_or_404(db, segment_id, org_id)
    seg.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="segment.soft_delete",
        entity_type="saved_segment",
        entity_id=seg.id,
        organization_id=org_id,
    )
    await db.commit()
