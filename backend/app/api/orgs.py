"""Organization endpoints — list user's memberships, switch active org,
create a brand-new org.

The "switch org" is a server-side write (updates `users.last_active_org_id`)
followed by a client-side reload. We don't reissue the JWT because the
JWT carries only `sub` (user id) and `role` — the org is resolved from
the DB on every request via `get_current_org_id`. Switching is therefore
zero-cost token-wise; the next request just sees the new org.

Creating a new org makes the caller the admin of it. We don't run the
seat enforcement on this (it's a fresh org with 1 seat used, no plan
limit hit). The seat check only kicks in for invite-accept and signup
into an existing org.
"""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.models import Organization, OrgMembership, User, UserRole
from app.schemas import (
    MembershipOut,
    OrgCreate,
    OrgOut,
    SwitchOrgRequest,
    TeamMemberOut,
    UserOut,
)

router = APIRouter(prefix="/api/orgs", tags=["orgs"])


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    """Turn 'Acme Corp & Co.' → 'acme-corp-co'. Not pretty for non-Latin
    scripts — for those the user should supply their own slug. The
    `_SLUG_RE` strips everything that isn't already URL-safe."""
    s = name.lower().strip().replace(" ", "-")
    s = _SLUG_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "workspace"


async def _unique_slug(db: AsyncSession, base: str) -> str:
    """Append -2, -3, … until the slug is free. Matches GitHub-style
    auto-disambiguation. Bounded loop so a pathologically unlucky base
    can't spin forever."""
    candidate = base
    for i in range(2, 200):
        existing = await db.execute(select(Organization.id).where(Organization.slug == candidate))
        if existing.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{i}"
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Could not generate a unique slug; pick a less common name.",
    )


@router.get("/me", response_model=list[MembershipOut])
async def list_my_memberships(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MembershipOut]:
    """All orgs the current user belongs to, with their role in each.
    Drives the org switcher in the UI."""
    result = await db.execute(
        select(OrgMembership, Organization)
        .join(Organization, Organization.id == OrgMembership.organization_id)
        .where(OrgMembership.user_id == user.id)
        .order_by(OrgMembership.created_at.asc())
    )
    return [
        MembershipOut(
            organization=OrgOut.model_validate(org),
            role=m.role,
            created_at=m.created_at,
        )
        for m, org in result.all()
    ]


@router.post("/me/switch", response_model=UserOut)
async def switch_org(
    payload: SwitchOrgRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Switch the user's active org. Verifies membership exists before
    writing — silently dropping into a 'switched but no membership'
    state would break every subsequent tenant-scoped query."""
    membership = (
        await db.execute(
            select(OrgMembership).where(
                OrgMembership.user_id == user.id,
                OrgMembership.organization_id == payload.organization_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        # 404, not 403 — the existence-leak rule applies to org IDs too.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found in your memberships",
        )

    user.last_active_org_id = payload.organization_id
    await record_audit(
        db,
        actor=user,
        action="user.switch_org",
        entity_type="user",
        entity_id=user.id,
        organization_id=payload.organization_id,
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/current/members", response_model=list[TeamMemberOut])
async def list_org_members(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[TeamMemberOut]:
    """Every user in the current org — feeds team-member pickers. Any member
    can read; team mutation stays on the teams router."""
    rows = (
        await db.execute(
            select(User, OrgMembership.role)
            .join(OrgMembership, OrgMembership.user_id == User.id)
            .where(OrgMembership.organization_id == org_id)
            .order_by(User.full_name)
        )
    ).all()
    return [
        TeamMemberOut(user_id=u.id, full_name=u.full_name, email=u.email, role=role)
        for u, role in rows
    ]


@router.post("", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
async def create_org(
    payload: OrgCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Create a fresh org. The caller becomes admin of it and is
    auto-switched to it (their next request hits the new tenant)."""
    base_slug = _slugify(payload.slug or payload.name)
    if not base_slug or len(base_slug) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization name is too short.",
        )
    slug = await _unique_slug(db, base_slug)

    org = Organization(name=payload.name.strip(), slug=slug)
    db.add(org)
    await db.flush()

    membership = OrgMembership(user_id=user.id, organization_id=org.id, role=UserRole.admin)
    db.add(membership)

    # Auto-switch — the user almost always wants to land in the org they
    # just created.
    user.last_active_org_id = org.id

    await record_audit(
        db,
        actor=user,
        action="org.create",
        entity_type="organization",
        entity_id=org.id,
        organization_id=org.id,
        metadata={"name": org.name, "slug": org.slug},
    )
    await db.commit()
    await db.refresh(org)
    return org
