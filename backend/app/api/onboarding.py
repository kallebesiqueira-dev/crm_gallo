"""Onboarding in < 30 minutes (plan.md §3) — backend half.

Two pieces a fresh org needs on day one:

  GET  /api/onboarding/templates
      Sector pipeline templates (Agency, SaaS, Consulting,
      Construction, Real estate, WhatsApp sales, simple B2B). Static
      catalog — stage names ship in English as the canonical copy;
      the SPA wizard localizes the *display* by slug, and applied
      stages stay fully editable in the existing pipeline editor.

  POST /api/onboarding/templates/{slug}/apply
      Materializes the template as a deal Pipeline + stages for this
      org (admin/manager). Re-applying the same template 409s — the
      pipeline editor is the place to iterate after that.

  GET  /api/onboarding/checklist
      The 5-step first-session checklist, computed from REAL data —
      no state table, nothing to migrate, can never drift from what
      the org actually did:
        1. pipeline_ready    — created/applied/edited a pipeline
        2. first_lead        — at least one lead exists
        3. next_action_set   — some deal carries next_action_at
        4. teammate_invited  — >1 member or a pending invite
        5. proposal_sent     — a quote left draft

Self-contained module (local schemas, the trash.py pattern).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import PRIVILEGED_ROLES, get_current_org_id, get_current_user, require_roles
from app.models import (
    AuditLog,
    Lead,
    OrgInvite,
    OrgMembership,
    Pipeline,
    PipelineKind,
    PipelineStage,
    Quote,
    QuoteStatus,
    User,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(s: str) -> str:
    out = _SLUG_RE.sub("-", s.lower().strip().replace(" ", "-"))
    return re.sub(r"-+", "-", out).strip("-") or "pipeline"


# ---------- Sector template catalog ----------
# Stage tuples are (name, probability, is_won, is_lost) — positions are
# implicit. Probabilities feed the weighted-pipeline widgets out of the box.

SECTOR_TEMPLATES: dict[str, dict[str, Any]] = {
    "agency": {
        "name": "Agency",
        "stages": [
            ("Briefing", 10, False, False),
            ("Proposal sent", 35, False, False),
            ("Negotiation", 60, False, False),
            ("Won", 100, True, False),
            ("Lost", 0, False, True),
        ],
    },
    "saas": {
        "name": "SaaS / Software",
        "stages": [
            ("Demo scheduled", 15, False, False),
            ("Demo done", 35, False, False),
            ("Trial", 55, False, False),
            ("Negotiation", 75, False, False),
            ("Won", 100, True, False),
            ("Lost", 0, False, True),
        ],
    },
    "consulting": {
        "name": "Consulting",
        "stages": [
            ("Discovery", 15, False, False),
            ("Proposal sent", 40, False, False),
            ("Negotiation", 65, False, False),
            ("Won", 100, True, False),
            ("Lost", 0, False, True),
        ],
    },
    "construction": {
        "name": "Construction",
        "stages": [
            ("Site visit", 15, False, False),
            ("Estimate sent", 40, False, False),
            ("Negotiation", 60, False, False),
            ("Contract", 85, False, False),
            ("Won", 100, True, False),
            ("Lost", 0, False, True),
        ],
    },
    "real-estate": {
        "name": "Real estate",
        "stages": [
            ("Visit scheduled", 15, False, False),
            ("Visit done", 35, False, False),
            ("Proposal", 60, False, False),
            ("Paperwork", 85, False, False),
            ("Won", 100, True, False),
            ("Lost", 0, False, True),
        ],
    },
    "whatsapp-sales": {
        "name": "WhatsApp sales",
        "stages": [
            ("New conversation", 10, False, False),
            ("Qualified", 30, False, False),
            ("Offer sent", 55, False, False),
            ("Payment pending", 80, False, False),
            ("Won", 100, True, False),
            ("Lost", 0, False, True),
        ],
    },
    "b2b-simple": {
        "name": "Simple B2B",
        "stages": [
            ("Contact", 10, False, False),
            ("Qualified", 35, False, False),
            ("Proposal", 60, False, False),
            ("Won", 100, True, False),
            ("Lost", 0, False, True),
        ],
    },
}


class TemplateStageOut(BaseModel):
    name: str
    slug: str
    position: int
    probability: int
    is_won: bool
    is_lost: bool


class TemplateOut(BaseModel):
    slug: str
    name: str
    kind: str = "deal"
    stages: list[TemplateStageOut]


class ApplyTemplateIn(BaseModel):
    """Optional knobs; the wizard usually sends an empty body."""

    name: str | None = None  # pipeline display name override
    set_default: bool = False


class ChecklistStepOut(BaseModel):
    key: str
    done: bool


class ChecklistOut(BaseModel):
    steps: list[ChecklistStepOut]
    completed: int
    total: int
    done: bool


def _template_out(slug: str) -> TemplateOut:
    tpl = SECTOR_TEMPLATES[slug]
    return TemplateOut(
        slug=slug,
        name=tpl["name"],
        stages=[
            TemplateStageOut(
                name=name,
                slug=_slugify(name),
                position=i,
                probability=prob,
                is_won=is_won,
                is_lost=is_lost,
            )
            for i, (name, prob, is_won, is_lost) in enumerate(tpl["stages"])
        ],
    )


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(_: User = Depends(get_current_user)) -> list[TemplateOut]:
    return [_template_out(slug) for slug in SECTOR_TEMPLATES]


@router.post(
    "/templates/{slug}/apply",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def apply_template(
    slug: str,
    payload: ApplyTemplateIn | None = None,
    user: User = Depends(require_roles(*PRIVILEGED_ROLES)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tpl = SECTOR_TEMPLATES.get(slug)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    overrides = payload or ApplyTemplateIn()

    pipeline_slug = _slugify(slug)
    clash = (
        await db.execute(
            select(Pipeline.id).where(
                Pipeline.organization_id == org_id,
                Pipeline.kind == PipelineKind.deal,
                Pipeline.slug == pipeline_slug,
            )
        )
    ).scalar_one_or_none()
    if clash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template '{slug}' was already applied — edit that pipeline instead.",
        )

    pipeline = Pipeline(
        organization_id=org_id,
        kind=PipelineKind.deal,
        name=(overrides.name or tpl["name"]).strip(),
        slug=pipeline_slug,
        is_default=False,
    )
    db.add(pipeline)
    await db.flush()
    for i, (name, prob, is_won, is_lost) in enumerate(tpl["stages"]):
        db.add(
            PipelineStage(
                pipeline_id=pipeline.id,
                name=name,
                slug=_slugify(name),
                position=i,
                probability=prob,
                is_won=is_won,
                is_lost=is_lost,
            )
        )
    if overrides.set_default:
        # Demote the previous default — same invariant as PATCH /pipelines.
        from sqlalchemy import update as sa_update

        await db.execute(
            sa_update(Pipeline)
            .where(
                Pipeline.organization_id == org_id,
                Pipeline.kind == PipelineKind.deal,
                Pipeline.is_default.is_(True),
                Pipeline.id != pipeline.id,
            )
            .values(is_default=False)
        )
        pipeline.is_default = True

    await record_audit(
        db,
        actor=user,
        action="onboarding.apply_template",
        entity_type="pipeline",
        entity_id=pipeline.id,
        organization_id=org_id,
        metadata={"template": slug},
    )
    await db.commit()
    return {"pipeline_id": str(pipeline.id), "template": slug}


# ---------- Checklist ----------


async def _exists(db: AsyncSession, stmt) -> bool:
    return (await db.execute(stmt.limit(1))).first() is not None


@router.get("/checklist", response_model=ChecklistOut)
async def checklist(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> ChecklistOut:
    # 1. Touched their pipeline setup in any way (created, edited, or
    #    applied a template). The audit ledger is the cheapest truth.
    pipeline_ready = await _exists(
        db,
        select(AuditLog.id).where(
            AuditLog.organization_id == org_id,
            AuditLog.action.in_(
                ("pipeline.create", "pipeline.update", "onboarding.apply_template")
            ),
        ),
    )
    # 2. At least one lead (live).
    first_lead = await _exists(db, select(Lead.id).where(Lead.organization_id == org_id))
    # 3. Some active deal carries a next action. Raw SQL on purpose —
    #    the column ships with the in-flight Deal next-action lane
    #    (migration 9c0d1e2f3a4b) and this stays immune to ORM churn.
    next_action_set = (
        await db.execute(
            text(
                "SELECT 1 FROM deals WHERE organization_id = :org"
                " AND next_action_at IS NOT NULL AND deleted_at IS NULL LIMIT 1"
            ),
            {"org": str(org_id)},
        )
    ).first() is not None
    # 4. Brought a colleague in (second member or a standing invite).
    member_count = (
        await db.execute(
            select(func.count())
            .select_from(OrgMembership)
            .where(OrgMembership.organization_id == org_id)
        )
    ).scalar_one()
    teammate_invited = member_count > 1 or await _exists(
        db, select(OrgInvite.id).where(OrgInvite.organization_id == org_id)
    )
    # 5. A quote that left draft (sent/accepted/declined/expired).
    proposal_sent = await _exists(
        db,
        select(Quote.id).where(Quote.organization_id == org_id, Quote.status != QuoteStatus.draft),
    )

    steps = [
        ChecklistStepOut(key="pipeline_ready", done=pipeline_ready),
        ChecklistStepOut(key="first_lead", done=first_lead),
        ChecklistStepOut(key="next_action_set", done=next_action_set),
        ChecklistStepOut(key="teammate_invited", done=teammate_invited),
        ChecklistStepOut(key="proposal_sent", done=proposal_sent),
    ]
    completed = sum(1 for s in steps if s.done)
    return ChecklistOut(
        steps=steps, completed=completed, total=len(steps), done=completed == len(steps)
    )
