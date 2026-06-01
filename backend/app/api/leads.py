import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities import ENTITY_LEAD, ActivityType, record_activity
from app.audit import record_audit
from app.events import EventType, record_event
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.models import Lead, LeadStage, User
from app.notifications import NotificationType, notify
from app.schemas import LeadCreate, LeadOut, LeadScoreOut, LeadUpdate
from app.services.ai_scoring import score_lead

router = APIRouter(prefix="/api/leads", tags=["leads"])


# All endpoints here are tenant-scoped via `get_current_org_id`. Every
# SELECT carries `Lead.organization_id == org_id` so cross-org reads are
# physically impossible (returning 404 instead of 403 avoids leaking
# which lead IDs exist in other tenants). Phase 6 will add Postgres RLS
# as a second line of defence; until then the app-layer filter is the
# only enforcement, so it must never be skipped.


async def _get_lead_or_404(db: AsyncSession, lead_id: uuid.UUID, org_id: uuid.UUID) -> Lead:
    """Fetch a lead scoped to the current org, or raise 404."""
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.organization_id == org_id)
    )
    lead = result.scalar_one_or_none()
    if not lead or lead.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.get("", response_model=list[LeadOut])
async def list_leads(
    stage: LeadStage | None = None,
    team_id: uuid.UUID | None = Query(
        default=None, description="filter by team_id"
    ),
    q: str | None = Query(default=None, description="search by name/email/company"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[Lead]:
    stmt = (
        select(Lead)
        .where(Lead.organization_id == org_id)
        .order_by(Lead.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if stage:
        stmt = stmt.where(Lead.stage == stage)
    if team_id is not None:
        stmt = stmt.where(Lead.team_id == team_id)
    if q:
        # Postgres FTS via the stored `search_vector` generated column
        # (migration 062fbc7b628d) + GIN index. Replaces the previous
        # `LOWER() LIKE '%q%'` full-table scan. `websearch_to_tsquery`
        # parses Google-style input: `acme corp`, `"exact phrase"`,
        # `acme -spam`. `simple` config matches the index — locale-
        # agnostic since the data is multilingual.
        stmt = stmt.where(
            sa.text("search_vector @@ websearch_to_tsquery('simple', :q)")
            .bindparams(q=q)
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Lead:
    data = payload.model_dump()
    # `organization_id` is NEVER read from payload — that would let a
    # logged-in user plant rows into any tenant. Pull from the server-
    # side dep.
    data["owner_id"] = data.get("owner_id") or user.id
    lead = Lead(**data, organization_id=org_id)
    db.add(lead)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="lead.create",
        entity_type="lead",
        entity_id=lead.id,
        organization_id=org_id,
        metadata={"stage": lead.stage.value},
    )
    await record_activity(
        db,
        entity_type=ENTITY_LEAD,
        entity_id=lead.id,
        activity_type=ActivityType.created,
        organization_id=org_id,
        actor=user,
        metadata={"stage": lead.stage.value},
    )
    await record_event(
        db,
        event_type=EventType.lead_created,
        organization_id=org_id,
        payload={
            "lead_id": lead.id,
            "owner_id": lead.owner_id,
            "stage": lead.stage.value,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    await db.refresh(lead)
    return lead


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(
    lead_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Lead:
    return await _get_lead_or_404(db, lead_id, org_id)


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Lead:
    lead = await _get_lead_or_404(db, lead_id, org_id)
    ensure_can_mutate(user, lead.owner_id)
    changes = payload.model_dump(exclude_unset=True)
    # Even if a (buggy) caller smuggles organization_id into the patch
    # body, refuse to let it move tenants.
    changes.pop("organization_id", None)
    # Snapshot the old stage BEFORE setattr so a stage transition
    # gets recorded as a separate `stage_change` activity (with from/to
    # in metadata) — the timeline UI shows it as a distinct row from
    # the generic `updated` activity.
    prev_stage = lead.stage
    for field, value in changes.items():
        setattr(lead, field, value)
    await record_audit(
        db,
        actor=user,
        action="lead.update",
        entity_type="lead",
        entity_id=lead.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    if "stage" in changes and changes["stage"] != prev_stage:
        await record_activity(
            db,
            entity_type=ENTITY_LEAD,
            entity_id=lead.id,
            activity_type=ActivityType.stage_change,
            organization_id=org_id,
            actor=user,
            metadata={"from": prev_stage.value, "to": lead.stage.value},
        )
        await record_event(
            db,
            event_type=EventType.lead_stage_changed,
            organization_id=org_id,
            payload={
                "lead_id": lead.id,
                "from": prev_stage.value,
                "to": lead.stage.value,
                "actor_user_id": user.id,
            },
        )
        # Bell the lead's owner when someone ELSE moves the stage —
        # don't notify them about their own actions (spammy).
        if lead.owner_id and lead.owner_id != user.id:
            await notify(
                db,
                user_id=lead.owner_id,
                organization_id=org_id,
                notification_type=NotificationType.lead_stage_changed,
                title=f"{user.full_name} moved a lead to {lead.stage.value}",
                body=f"{lead.first_name} {lead.last_name}",
                link_url=f"/leads/{lead.id}",
                actor=user,
                metadata={
                    "lead_id": str(lead.id),
                    "from": prev_stage.value,
                    "to": lead.stage.value,
                },
            )
    else:
        # Catch-all `updated` activity for non-stage edits so the
        # timeline reflects that something changed (the security audit
        # already records the field list — we keep the activity terse).
        await record_activity(
            db,
            entity_type=ENTITY_LEAD,
            entity_id=lead.id,
            activity_type=ActivityType.updated,
            organization_id=org_id,
            actor=user,
            metadata={"fields": list(changes.keys())},
        )
    await db.commit()
    await db.refresh(lead)
    return lead


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    lead = await _get_lead_or_404(db, lead_id, org_id)
    ensure_can_mutate(user, lead.owner_id)
    lead.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="lead.soft_delete",
        entity_type="lead",
        entity_id=lead.id,
        organization_id=org_id,
    )
    await db.commit()


@router.post("/{lead_id}/score", response_model=LeadOut)
async def score(
    lead_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Lead:
    lead = await _get_lead_or_404(db, lead_id, org_id)
    ensure_can_mutate(user, lead.owner_id)
    result = await score_lead(lead)
    lead.ai_score = result["score"]
    lead.ai_priority = result["priority"]
    lead.ai_next_action = result["next_action"]
    lead.ai_conversion_probability = result["conversion_probability"]
    lead.ai_risk_analysis = result["risk_analysis"]
    lead.ai_scored_at = result.get("scored_at", datetime.now(UTC))
    await record_activity(
        db,
        entity_type=ENTITY_LEAD,
        entity_id=lead.id,
        activity_type=ActivityType.ai_scored,
        organization_id=org_id,
        actor=user,
        metadata={
            "score": lead.ai_score,
            "priority": lead.ai_priority,
            "next_action": lead.ai_next_action,
        },
    )
    await record_audit(
        db,
        actor=user,
        action="lead.score",
        entity_type="lead",
        entity_id=lead.id,
        organization_id=org_id,
        metadata={"score": lead.ai_score, "priority": lead.ai_priority},
    )
    await db.commit()
    await db.refresh(lead)
    return lead


@router.post("/{lead_id}/score-async", status_code=status.HTTP_202_ACCEPTED)
async def score_async(
    lead_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Enqueue an LLM scoring job for this lead and return 202.

    Used by the dashboard's "score all" button + by clients that
    don't want to block the HTTP request on a 30s LLM call.
    Idempotent within a 5-minute window: clicking twice in quick
    succession returns `{queued: false, dedupe: true}` instead of
    enqueueing twice.

    The sync POST `/score` endpoint is still there for clients that
    want the score returned inline.
    """
    # Lead-must-exist + ownership check via the same dep stack the
    # sync endpoint uses — we don't want to enqueue work against a
    # foreign-org lead.
    lead = await _get_lead_or_404(db, lead_id, org_id)
    ensure_can_mutate(user, lead.owner_id)

    from app.worker.queue import enqueue

    job = await enqueue(
        "score_lead",
        str(lead.id),
        str(org_id),
        dedupe_key=f"score_lead:{lead.id}",
        dedupe_ttl_seconds=300,
    )
    if job is None:
        return {"queued": False, "dedupe": True}
    return {"queued": True, "job_id": job.job_id}


# Kept for clients that want the score payload without re-fetching the lead.
@router.get("/{lead_id}/score", response_model=LeadScoreOut)
async def get_score(
    lead_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> LeadScoreOut:
    lead = await _get_lead_or_404(db, lead_id, org_id)
    if lead.ai_score is None:
        raise HTTPException(status_code=404, detail="Score not available")
    return LeadScoreOut(
        score=lead.ai_score,
        priority=lead.ai_priority or "",
        next_action=lead.ai_next_action or "",
        conversion_probability=lead.ai_conversion_probability or 0.0,
        risk_analysis=lead.ai_risk_analysis or "",
    )
