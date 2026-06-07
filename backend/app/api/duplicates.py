import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import get_current_org_id, get_current_user, require_roles
from app.models import User, UserRole
from app.schemas import DuplicateGroupsOut, MergeRequest, MergeResult
from app.services.duplicates import (
    DUPLICATE_ENTITY_TYPES,
    detect_duplicates,
    merge_records,
)

router = APIRouter(prefix="/api/duplicates", tags=["duplicates"])

# Merging soft-deletes records and re-homes their history, so it is a
# privileged op (same bar as deleting a tag). Detection is read-only and
# open to any member.
manage = require_roles(UserRole.admin, UserRole.manager)


def _validate_entity_type(entity_type: str) -> None:
    if entity_type not in DUPLICATE_ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="Unknown entity_type")


@router.get("", response_model=DuplicateGroupsOut)
async def list_duplicates(
    entity_type: str = Query(...),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> DuplicateGroupsOut:
    _validate_entity_type(entity_type)
    groups = await detect_duplicates(db, org_id, entity_type)
    return DuplicateGroupsOut(entity_type=entity_type, groups=groups)


@router.post("/merge", response_model=MergeResult)
async def merge_duplicates(
    payload: MergeRequest,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> MergeResult:
    try:
        result = await merge_records(
            db,
            org_id,
            payload.entity_type,
            payload.survivor_id,
            payload.loser_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="No records to merge") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=f"{exc} not found") from exc

    await record_audit(
        db,
        actor=user,
        action="duplicate.merge",
        entity_type=payload.entity_type,
        entity_id=result.survivor_id,
        organization_id=org_id,
        metadata={
            "losers": [str(i) for i in payload.loser_ids],
            "merged_count": result.merged_count,
            "reparented": result.reparented,
        },
    )
    await db.commit()
    return result
