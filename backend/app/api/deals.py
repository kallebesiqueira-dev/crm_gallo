import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities import ENTITY_DEAL, ActivityType, record_activity
from app.api._concurrency import check_if_match
from app.api.dashboard import invalidate_dashboard_cache
from app.audit import record_audit
from app.custom_fields import validate_custom_fields
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.events import EventType, record_event
from app.logging_setup import get_logger
from app.models import Deal, DealStage, User
from app.schemas import DealCreate, DealOut, DealStageMove, DealUpdate

router = APIRouter(prefix="/api/deals", tags=["deals"])
log = get_logger(__name__)


def _check_if_match(deal: Deal, if_match: str | None) -> None:
    check_if_match(
        entity="deal",
        entity_id=deal.id,
        current_version=deal.version,
        if_match=if_match,
    )


async def _get_deal_or_404(db: AsyncSession, deal_id: uuid.UUID, org_id: uuid.UUID) -> Deal:
    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.organization_id == org_id)
    )
    deal = result.scalar_one_or_none()
    if not deal or deal.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.post("/{deal_id}/pdf", status_code=status.HTTP_202_ACCEPTED)
async def generate_deal_pdf_endpoint(
    deal_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Enqueue a deal-summary PDF (ADR-016) and return 202.

    The worker renders the document and attaches it to the deal, so the
    result shows up in `GET /api/attachments?entity_type=deal&...` and
    downloads via the existing presigned-URL endpoint. Idempotent within
    a 5-minute window — a double-click returns `{queued: false}`.
    """
    deal = await _get_deal_or_404(db, deal_id, org_id)
    ensure_can_mutate(user, deal.owner_id)

    from app.worker.queue import enqueue

    job = await enqueue(
        "generate_deal_pdf",
        str(deal.id),
        str(org_id),
        dedupe_key=f"deal_pdf:{deal.id}",
        dedupe_ttl_seconds=300,
    )
    if job is None:
        return {"queued": False, "dedupe": True}
    return {"queued": True, "job_id": job.job_id}


@router.get("", response_model=list[DealOut])
async def list_deals(
    stage: DealStage | None = None,
    team_id: uuid.UUID | None = Query(default=None, description="filter by team_id"),
    limit: int = Query(default=200, ge=1, le=500),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[Deal]:
    stmt = (
        select(Deal)
        .where(Deal.organization_id == org_id)
        .order_by(Deal.stage, Deal.sort_index, Deal.created_at.desc(), Deal.id.desc())
        .limit(limit)
    )
    if stage:
        stmt = stmt.where(Deal.stage == stage)
    if team_id is not None:
        stmt = stmt.where(Deal.team_id == team_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=DealOut, status_code=status.HTTP_201_CREATED)
async def create_deal(
    payload: DealCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Deal:
    data = payload.model_dump()
    data["owner_id"] = data.get("owner_id") or user.id
    data["custom_fields"] = await validate_custom_fields(
        db, org_id, "deal", data.get("custom_fields"), partial=False
    )

    # Sort index is org-scoped: a new deal lands at the bottom of its
    # column inside THIS org. Without the org filter we'd peek at every
    # tenant's pipeline order.
    max_index = (
        await db.execute(
            select(Deal.sort_index)
            .where(
                Deal.organization_id == org_id,
                Deal.stage == data["stage"],
            )
            .order_by(Deal.sort_index.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    data["sort_index"] = (max_index or 0) + 1

    deal = Deal(**data, organization_id=org_id)
    db.add(deal)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="deal.create",
        entity_type="deal",
        entity_id=deal.id,
        organization_id=org_id,
        metadata={"stage": deal.stage.value, "value": deal.value},
    )
    await record_activity(
        db,
        entity_type=ENTITY_DEAL,
        entity_id=deal.id,
        activity_type=ActivityType.created,
        organization_id=org_id,
        actor=user,
        metadata={"stage": deal.stage.value},
    )
    await record_event(
        db,
        event_type=EventType.deal_created,
        organization_id=org_id,
        payload={
            "deal_id": deal.id,
            "owner_id": deal.owner_id,
            "stage": deal.stage.value,
            "value": deal.value,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    await invalidate_dashboard_cache(org_id)
    await db.refresh(deal)
    return deal


@router.get("/{deal_id}", response_model=DealOut)
async def get_deal(
    deal_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Deal:
    return await _get_deal_or_404(db, deal_id, org_id)


@router.patch("/{deal_id}", response_model=DealOut)
async def update_deal(
    deal_id: uuid.UUID,
    payload: DealUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> Deal:
    deal = await _get_deal_or_404(db, deal_id, org_id)
    ensure_can_mutate(user, deal.owner_id)
    _check_if_match(deal, if_match)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("organization_id", None)
    if "custom_fields" in changes:
        changes["custom_fields"] = await validate_custom_fields(
            db,
            org_id,
            "deal",
            changes["custom_fields"],
            existing=deal.custom_fields,
            partial=True,
        )
    for field, value in changes.items():
        setattr(deal, field, value)
    deal.version = deal.version + 1
    await record_audit(
        db,
        actor=user,
        action="deal.update",
        entity_type="deal",
        entity_id=deal.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await record_activity(
        db,
        entity_type=ENTITY_DEAL,
        entity_id=deal.id,
        activity_type=ActivityType.updated,
        organization_id=org_id,
        actor=user,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await invalidate_dashboard_cache(org_id)
    await db.refresh(deal)
    return deal


@router.post("/{deal_id}/move", response_model=DealOut)
async def move_deal(
    deal_id: uuid.UUID,
    payload: DealStageMove,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> Deal:
    deal = await _get_deal_or_404(db, deal_id, org_id)
    ensure_can_mutate(user, deal.owner_id)
    _check_if_match(deal, if_match)
    prev_stage = deal.stage
    deal.stage = payload.stage
    deal.sort_index = payload.sort_index
    deal.version = deal.version + 1
    await record_audit(
        db,
        actor=user,
        action="deal.move",
        entity_type="deal",
        entity_id=deal.id,
        organization_id=org_id,
        metadata={"from": prev_stage.value, "to": deal.stage.value, "sort_index": deal.sort_index},
    )
    # Outbox fan-out for every stage move + specific events on won/lost.
    # Subscribers can filter on `deal.stage_changed` for the generic
    # case OR react narrowly to `deal.won` / `deal.lost` without
    # parsing the payload (cleaner automation surface).
    if deal.stage != prev_stage:
        await record_activity(
            db,
            entity_type=ENTITY_DEAL,
            entity_id=deal.id,
            activity_type=ActivityType.stage_change,
            organization_id=org_id,
            actor=user,
            metadata={"from": prev_stage.value, "to": deal.stage.value},
        )
        event_payload = {
            "deal_id": deal.id,
            "from": prev_stage.value,
            "to": deal.stage.value,
            "value": deal.value,
            "owner_id": deal.owner_id,
            "actor_user_id": user.id,
        }
        await record_event(
            db,
            event_type=EventType.deal_stage_changed,
            organization_id=org_id,
            payload=event_payload,
        )
        if deal.stage == DealStage.won:
            await record_event(
                db,
                event_type=EventType.deal_won,
                organization_id=org_id,
                payload=event_payload,
            )
        elif deal.stage == DealStage.lost:
            await record_event(
                db,
                event_type=EventType.deal_lost,
                organization_id=org_id,
                payload=event_payload,
            )
    await db.commit()
    await invalidate_dashboard_cache(org_id)
    await db.refresh(deal)
    return deal


@router.delete("/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(
    deal_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    deal = await _get_deal_or_404(db, deal_id, org_id)
    ensure_can_mutate(user, deal.owner_id)
    deal.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="deal.soft_delete",
        entity_type="deal",
        entity_id=deal.id,
        organization_id=org_id,
    )
    await db.commit()
    await invalidate_dashboard_cache(org_id)
