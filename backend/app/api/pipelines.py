"""Pipeline CRUD — Phase 1 (foundation; not yet wired into Lead/Deal).

Surface:
  * GET    /api/pipelines?kind=lead|deal       list (auto-seeds default on first call)
  * POST   /api/pipelines                      create empty pipeline (admin/manager)
  * GET    /api/pipelines/{id}                 detail with stages
  * PATCH  /api/pipelines/{id}                 rename + reconcile stages (admin/manager)
  * DELETE /api/pipelines/{id}                 soft-delete (admin/manager); blocked if default

Stage reconciliation in PATCH (see `_reconcile_stages`):
  * stages with `id` matching an existing row → UPDATE in place
  * stages with `id=null` → INSERT
  * existing rows whose id is absent from the payload → soft-delete
This avoids three separate endpoints for the SPA's drag-to-reorder
+ inline rename + delete-stage flow.
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import record_audit
from app.database import get_db
from app.deps import PRIVILEGED_ROLES, get_current_org_id, get_current_user, require_roles
from app.models import Pipeline, PipelineKind, PipelineStage, User
from app.pipelines import KIND_LOOKUP, get_or_seed_default_pipeline
from app.schemas import (
    PipelineCreate,
    PipelineOut,
    PipelineStageOut,
    PipelineStageWrite,
    PipelineUpdate,
)

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(s: str) -> str:
    out = s.lower().strip().replace(" ", "-")
    out = _SLUG_RE.sub("-", out)
    out = re.sub(r"-+", "-", out).strip("-")
    return out or "pipeline"


def _serialize(p: Pipeline) -> PipelineOut:
    return PipelineOut(
        id=p.id,
        kind=p.kind.value,
        name=p.name,
        slug=p.slug,
        is_default=p.is_default,
        created_at=p.created_at,
        updated_at=p.updated_at,
        stages=[
            PipelineStageOut(
                id=s.id,
                name=s.name,
                slug=s.slug,
                position=s.position,
                probability=s.probability,
                is_won=s.is_won,
                is_lost=s.is_lost,
            )
            # `p.stages` is order_by=position via the relationship,
            # but the soft-delete filter event excludes deleted
            # stages so the visible list is what callers expect.
            for s in p.stages
        ],
    )


async def _get_pipeline_or_404(
    db: AsyncSession, pipeline_id: uuid.UUID, org_id: uuid.UUID
) -> Pipeline:
    # `selectinload(stages)` is one extra query but avoids the
    # per-row lazy-load N+1 when we serialise. The soft-delete
    # filter applies to the eager load too via
    # `with_loader_criteria(SoftDeleteMixin, …, include_aliases=True)`.
    result = await db.execute(
        select(Pipeline)
        .options(selectinload(Pipeline.stages))
        .where(Pipeline.id == pipeline_id, Pipeline.organization_id == org_id)
    )
    p = result.scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return p


@router.get("", response_model=list[PipelineOut])
async def list_pipelines(
    kind: str | None = Query(default=None, pattern=r"^(lead|deal)$"),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[PipelineOut]:
    """List pipelines, optionally filtered by kind. On first call
    per (org, kind) auto-seeds the default pipeline so the admin
    UI is never empty."""
    # Auto-seed both kinds if either is missing — cheap and means
    # admins don't have to flip between kinds to discover the
    # "seed happens automatically" behavior. When `?kind=` is given
    # we only seed that one; when omitted we seed both.
    seeded_kinds: set[PipelineKind] = (
        {KIND_LOOKUP[kind]} if kind else set(PipelineKind)
    )
    for k in seeded_kinds:
        await get_or_seed_default_pipeline(db, org_id, k)
    await db.commit()

    stmt = (
        select(Pipeline)
        .options(selectinload(Pipeline.stages))
        .where(Pipeline.organization_id == org_id)
        .order_by(Pipeline.kind, Pipeline.is_default.desc(), Pipeline.name)
    )
    if kind:
        stmt = stmt.where(Pipeline.kind == KIND_LOOKUP[kind])
    result = await db.execute(stmt)
    return [_serialize(p) for p in result.scalars().all()]


@router.get("/{pipeline_id}", response_model=PipelineOut)
async def get_pipeline(
    pipeline_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> PipelineOut:
    p = await _get_pipeline_or_404(db, pipeline_id, org_id)
    return _serialize(p)


@router.post("", response_model=PipelineOut, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    payload: PipelineCreate,
    user: User = Depends(require_roles(*PRIVILEGED_ROLES)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> PipelineOut:
    kind = KIND_LOOKUP[payload.kind]
    slug = (payload.slug or _slugify(payload.name)).strip()
    # Pre-flight slug-clash check (the partial unique index would
    # raise an IntegrityError otherwise; this gives a friendlier 409).
    clash = (
        await db.execute(
            select(Pipeline.id).where(
                Pipeline.organization_id == org_id,
                Pipeline.kind == kind,
                Pipeline.slug == slug,
            )
        )
    ).scalar_one_or_none()
    if clash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Pipeline slug '{slug}' already used for {kind.value} pipelines.",
        )
    p = Pipeline(
        organization_id=org_id,
        kind=kind,
        name=payload.name.strip(),
        slug=slug,
        is_default=False,
    )
    db.add(p)
    await db.flush()
    await record_audit(
        db, actor=user, action="pipeline.create",
        entity_type="pipeline", entity_id=p.id, organization_id=org_id,
        metadata={"kind": kind.value, "name": p.name},
    )
    await db.commit()
    # Re-fetch with stages eager-loaded for the response shape.
    p = await _get_pipeline_or_404(db, p.id, org_id)
    return _serialize(p)


async def _reconcile_stages(
    db: AsyncSession,
    pipeline: Pipeline,
    incoming: list[PipelineStageWrite],
) -> None:
    """In-place reconcile the pipeline's stage list against the
    incoming payload. ids in incoming that match existing → update;
    ids absent → soft-delete; null ids → insert."""
    existing_by_id = {s.id: s for s in pipeline.stages}
    incoming_ids = {st.id for st in incoming if st.id is not None}

    # Soft-delete stages that the client dropped from the list.
    now = datetime.now(UTC)
    for sid, stage in existing_by_id.items():
        if sid not in incoming_ids:
            stage.deleted_at = now

    for st in incoming:
        if st.id is not None and st.id in existing_by_id:
            target = existing_by_id[st.id]
            target.name = st.name.strip()
            if st.slug:
                target.slug = _slugify(st.slug)
            target.position = st.position
            target.probability = st.probability
            target.is_won = st.is_won
            target.is_lost = st.is_lost
        else:
            db.add(
                PipelineStage(
                    pipeline_id=pipeline.id,
                    name=st.name.strip(),
                    slug=_slugify(st.slug or st.name),
                    position=st.position,
                    probability=st.probability,
                    is_won=st.is_won,
                    is_lost=st.is_lost,
                )
            )


@router.patch("/{pipeline_id}", response_model=PipelineOut)
async def update_pipeline(
    pipeline_id: uuid.UUID,
    payload: PipelineUpdate,
    user: User = Depends(require_roles(*PRIVILEGED_ROLES)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> PipelineOut:
    p = await _get_pipeline_or_404(db, pipeline_id, org_id)
    changes = payload.model_dump(exclude_unset=True)

    if "name" in changes and changes["name"]:
        p.name = changes["name"].strip()
    if "slug" in changes and changes["slug"]:
        new_slug = _slugify(changes["slug"])
        if new_slug != p.slug:
            clash = (
                await db.execute(
                    select(Pipeline.id).where(
                        Pipeline.organization_id == org_id,
                        Pipeline.kind == p.kind,
                        Pipeline.slug == new_slug,
                        Pipeline.id != p.id,
                    )
                )
            ).scalar_one_or_none()
            if clash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Pipeline slug '{new_slug}' is already in use.",
                )
            p.slug = new_slug
    if "is_default" in changes and changes["is_default"] is True and not p.is_default:
        # Demote the previous default of this kind so we keep the
        # invariant "exactly one default per (org, kind)".
        await db.execute(
            update(Pipeline)
            .where(
                Pipeline.organization_id == org_id,
                Pipeline.kind == p.kind,
                Pipeline.is_default.is_(True),
                Pipeline.id != p.id,
            )
            .values(is_default=False)
        )
        p.is_default = True
    if payload.stages is not None:
        await _reconcile_stages(db, p, payload.stages)

    await record_audit(
        db, actor=user, action="pipeline.update",
        entity_type="pipeline", entity_id=p.id, organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    p = await _get_pipeline_or_404(db, p.id, org_id)
    return _serialize(p)


# Skip `-> None` annotation on the 204 — combined with
# `from __future__ import annotations` FastAPI's introspection trips
# the "204 must not have a body" assert (see notes.delete_note for
# the full diagnosis).
@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    pipeline_id: uuid.UUID,
    user: User = Depends(require_roles(*PRIVILEGED_ROLES)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_pipeline_or_404(db, pipeline_id, org_id)
    if p.is_default:
        # Refuse to delete the default pipeline — the auto-seed
        # would just re-create it on the next /pipelines GET, which
        # would be a confusing UX. Admin should set another
        # pipeline as default first.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set another pipeline as default before deleting this one.",
        )
    p.deleted_at = datetime.now(UTC)
    # Stages are cascade-deleted via the relationship's
    # `cascade="all, delete-orphan"` on hard delete, but we're soft-
    # deleting the pipeline — propagate deleted_at to stages too so
    # the global filter hides them.
    for stage in p.stages:
        stage.deleted_at = p.deleted_at
    await record_audit(
        db, actor=user, action="pipeline.delete",
        entity_type="pipeline", entity_id=p.id, organization_id=org_id,
    )
    await db.commit()
