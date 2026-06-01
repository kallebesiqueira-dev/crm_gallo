"""Team CRUD + membership.

Surface:
  * `GET    /api/teams`                      list (any member of org)
  * `POST   /api/teams`                      create (admin/manager)
  * `PATCH  /api/teams/{id}`                 rename/re-slug (admin/manager)
  * `DELETE /api/teams/{id}`                 soft-delete (admin/manager) + unassign members
  * `POST   /api/teams/{id}/members`         assign user (admin/manager)
  * `DELETE /api/teams/{id}/members/{uid}`   unassign (admin/manager)

Org-scoped via `get_current_org_id`. Mutation reserved for
privileged roles; everyone else can read so the UI can render
team chips on records they look at.

Round-robin assignment of new Leads/Deals to team members is a
follow-up — needs a Redis cursor per team to remember "last
assigned". Tracked in skills.md.
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import PRIVILEGED_ROLES, get_current_org_id, get_current_user, require_roles
from app.models import Deal, Lead, Team, User
from app.schemas import (
    TeamCreate,
    TeamMemberAssign,
    TeamMemberOut,
    TeamOut,
    TeamUpdate,
)

router = APIRouter(prefix="/api/teams", tags=["teams"])


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(s: str) -> str:
    """Turn 'Inbound EU & DACH' → 'inbound-eu-dach'. Mirrors the
    helper in `app/api/orgs.py`."""
    out = s.lower().strip().replace(" ", "-")
    out = _SLUG_RE.sub("-", out)
    out = re.sub(r"-+", "-", out).strip("-")
    return out or "team"


async def _get_team_or_404(
    db: AsyncSession, team_id: uuid.UUID, org_id: uuid.UUID
) -> Team:
    result = await db.execute(
        select(Team).where(Team.id == team_id, Team.organization_id == org_id)
    )
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


async def _serialize(db: AsyncSession, team: Team) -> TeamOut:
    """Hydrate one team with its current member list. One JOIN
    against User where `team_id == team.id`; counts come from the
    same rowset."""
    rows = (
        await db.execute(
            select(User.id, User.full_name, User.email, User.role)
            .where(User.team_id == team.id, User.is_active.is_(True))
            .order_by(User.full_name.asc())
        )
    ).all()
    members = [
        TeamMemberOut(user_id=r.id, full_name=r.full_name, email=r.email, role=r.role)
        for r in rows
    ]
    return TeamOut(
        id=team.id,
        name=team.name,
        slug=team.slug,
        created_at=team.created_at,
        updated_at=team.updated_at,
        member_count=len(members),
        members=members,
    )


@router.get("", response_model=list[TeamOut])
async def list_teams(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[TeamOut]:
    """List all (non-deleted) teams in the current org with their
    member rolls. Any org member can read — needed to render team
    chips on records."""
    result = await db.execute(
        select(Team)
        .where(Team.organization_id == org_id)
        .order_by(Team.name.asc())
    )
    teams = list(result.scalars().all())
    return [await _serialize(db, t) for t in teams]


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    user: User = Depends(require_roles(*PRIVILEGED_ROLES)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> TeamOut:
    slug = payload.slug.strip() if payload.slug else _slugify(payload.name)
    # Guard against the partial unique index racing — gives a
    # readable 409 instead of a raw IntegrityError.
    existing = (
        await db.execute(
            select(Team.id).where(
                Team.organization_id == org_id, Team.slug == slug
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team slug '{slug}' is already in use.",
        )
    team = Team(organization_id=org_id, name=payload.name.strip(), slug=slug)
    db.add(team)
    await db.flush()
    await record_audit(
        db, actor=user, action="team.create",
        entity_type="team", entity_id=team.id, organization_id=org_id,
        metadata={"name": team.name, "slug": team.slug},
    )
    await db.commit()
    await db.refresh(team)
    return await _serialize(db, team)


@router.patch("/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: uuid.UUID,
    payload: TeamUpdate,
    user: User = Depends(require_roles(*PRIVILEGED_ROLES)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> TeamOut:
    team = await _get_team_or_404(db, team_id, org_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"]:
        team.name = changes["name"].strip()
    if "slug" in changes and changes["slug"]:
        new_slug = _slugify(changes["slug"])
        if new_slug != team.slug:
            # Same per-org-unique guard as create.
            clash = (
                await db.execute(
                    select(Team.id).where(
                        Team.organization_id == org_id,
                        Team.slug == new_slug,
                        Team.id != team.id,
                    )
                )
            ).scalar_one_or_none()
            if clash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Team slug '{new_slug}' is already in use.",
                )
            team.slug = new_slug
    await record_audit(
        db, actor=user, action="team.update",
        entity_type="team", entity_id=team.id, organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await db.refresh(team)
    return await _serialize(db, team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: uuid.UUID,
    user: User = Depends(require_roles(*PRIVILEGED_ROLES)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    from datetime import UTC, datetime

    team = await _get_team_or_404(db, team_id, org_id)
    # Soft-delete on the team. We also explicitly clear `team_id` on
    # User/Lead/Deal NOW — the FK is SET NULL on hard delete only;
    # soft-delete needs the app to do the housekeeping so the
    # records don't keep pointing at an invisible team.
    team.deleted_at = datetime.now(UTC)
    await db.execute(
        update(User).where(User.team_id == team.id).values(team_id=None)
    )
    # Clear team_id on Lead/Deal too — the FK is SET NULL only on
    # HARD delete; soft-delete needs the app to do the housekeeping
    # so records don't keep pointing at an invisible team. RLS still
    # gates these to the current org via the GUC set by
    # `get_current_org_id`.
    await db.execute(
        update(Lead).where(Lead.team_id == team.id).values(team_id=None)
    )
    await db.execute(
        update(Deal).where(Deal.team_id == team.id).values(team_id=None)
    )
    await record_audit(
        db, actor=user, action="team.delete",
        entity_type="team", entity_id=team.id, organization_id=org_id,
    )
    await db.commit()


# ---------- Membership ----------

@router.post("/{team_id}/members", response_model=TeamOut)
async def add_member(
    team_id: uuid.UUID,
    payload: TeamMemberAssign,
    user: User = Depends(require_roles(*PRIVILEGED_ROLES)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> TeamOut:
    team = await _get_team_or_404(db, team_id, org_id)
    # The target user must be a member of THIS org (membership check
    # would be cleaner once we accept that User.last_active_org_id is
    # not authoritative — for now we use it as a fast filter and rely
    # on the existing per-route org_id check).
    target = await db.get(User, payload.user_id)
    if target is None or target.last_active_org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this organization",
        )
    target.team_id = team.id
    await record_audit(
        db, actor=user, action="team.member_added",
        entity_type="team", entity_id=team.id, organization_id=org_id,
        metadata={"user_id": str(target.id)},
    )
    await db.commit()
    await db.refresh(team)
    return await _serialize(db, team)


@router.delete(
    "/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    actor: User = Depends(require_roles(*PRIVILEGED_ROLES)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    team = await _get_team_or_404(db, team_id, org_id)
    target = await db.get(User, user_id)
    if target is None or target.team_id != team.id:
        raise HTTPException(status_code=404, detail="Member not found in team")
    target.team_id = None
    await record_audit(
        db, actor=actor, action="team.member_removed",
        entity_type="team", entity_id=team.id, organization_id=org_id,
        metadata={"user_id": str(user_id)},
    )
    await db.commit()


