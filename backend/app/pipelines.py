"""Pipeline auto-seed + helpers.

The first time an org reads its pipelines we materialise a
"default" pipeline matching the existing enum stages — so the
admin opens /settings → Pipelines and sees the familiar 7-column
lead funnel + 6-column deal funnel ready to edit, instead of an
empty list that needs a tutorial.

Phase 2 (next session) will:
  * Add `pipeline_stage_id` (nullable FK) on Lead/Deal
  * Backfill: for each row, set it to the stage in the default
    pipeline whose `slug` matches the enum value
  * Migrate filters / kanban to read from pipeline_stage_id
  * Eventually drop the enum columns once nothing references them
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LeadStage, Pipeline, PipelineKind, PipelineStage

# Seed templates: (slug, name, probability, is_won, is_lost). These
# mirror the legacy enum so the per-row backfill in Phase 2 is a
# slug join. Localised display names live in the frontend `pipelines.*`
# namespace; the `name` column here is the English default and the
# admin can rename freely.
_LEAD_DEFAULT_STAGES: list[tuple[str, str, int, bool, bool]] = [
    ("new", "New", 5, False, False),
    ("contacted", "Contacted", 15, False, False),
    ("qualified", "Qualified", 40, False, False),
    ("proposal_sent", "Proposal sent", 60, False, False),
    ("negotiation", "Negotiation", 80, False, False),
    ("won", "Won", 100, True, False),
    ("lost", "Lost", 0, False, True),
]

_DEAL_DEFAULT_STAGES: list[tuple[str, str, int, bool, bool]] = [
    ("new", "New", 10, False, False),
    ("qualified", "Qualified", 30, False, False),
    ("proposal_sent", "Proposal sent", 50, False, False),
    ("negotiation", "Negotiation", 75, False, False),
    ("won", "Won", 100, True, False),
    ("lost", "Lost", 0, False, True),
]


async def get_or_seed_default_pipeline(
    db: AsyncSession, organization_id: uuid.UUID, kind: PipelineKind
) -> Pipeline:
    """Return this org's default pipeline for `kind`, materialising
    it (+ its stages) the first time. Subsequent calls return the
    same row without writing.

    Caller is responsible for the commit. We `flush()` so the
    returned `Pipeline.stages` is populated for the response.
    """
    existing = (
        await db.execute(
            select(Pipeline).where(
                Pipeline.organization_id == organization_id,
                Pipeline.kind == kind,
                Pipeline.is_default.is_(True),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    template = _LEAD_DEFAULT_STAGES if kind == PipelineKind.lead else _DEAL_DEFAULT_STAGES
    name = "Default lead funnel" if kind == PipelineKind.lead else "Default sales funnel"
    pipeline = Pipeline(
        organization_id=organization_id,
        kind=kind,
        name=name,
        slug="default",
        is_default=True,
    )
    db.add(pipeline)
    await db.flush()
    for i, (slug, sname, prob, is_won, is_lost) in enumerate(template):
        db.add(
            PipelineStage(
                pipeline_id=pipeline.id,
                name=sname,
                slug=slug,
                position=i,
                probability=prob,
                is_won=is_won,
                is_lost=is_lost,
            )
        )
    await db.flush()
    # Re-fetch to populate `pipeline.stages` via the relationship.
    await db.refresh(pipeline)
    return pipeline


# Re-export a small map the API layer uses to convert the URL-style
# "kind" query param into the enum without leaking the enum across
# modules.
KIND_LOOKUP: dict[str, PipelineKind] = {
    "lead": PipelineKind.lead,
    "deal": PipelineKind.deal,
}


# Silence ruff: LeadStage import kept for future Phase 2 backfill
# helper that lives here. Remove this when the helper lands.
_ = LeadStage
