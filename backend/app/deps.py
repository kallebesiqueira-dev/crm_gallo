import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cookies import ACCESS_TOKEN_COOKIE
from app.database import get_db
from app.models import Organization, OrgMembership, User, UserRole
from app.security import decode_token

# `auto_error=False` so a missing Authorization header doesn't 401
# before we get a chance to check the cookie. The cookie path is the
# primary credential in the new model; the Bearer header is kept as a
# transitional fallback for non-browser clients (e.g. curl smoke tests,
# integration scripts) and will be deprecated once everything is on
# cookies.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

PRIVILEGED_ROLES = {UserRole.admin, UserRole.manager}


async def get_current_user(
    request: Request,
    bearer_token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Prefer cookie (browser path); fall back to Bearer header for
    # tooling. Either way the JWT is decoded the same.
    token = request.cookies.get(ACCESS_TOKEN_COOKIE) or bearer_token
    if not token:
        raise credentials_exc
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exc
        # MFA challenge tokens are issued only to authorise /mfa/verify
        # — they must never grant access to data endpoints. Without
        # this guard, a leaked challenge token (5-min TTL) would act
        # as a full session for those 5 minutes.
        if payload.get("purpose") == "mfa_challenge":
            raise credentials_exc
    except ValueError as e:
        raise credentials_exc from e

    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, TypeError) as e:
        raise credentials_exc from e

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise credentials_exc
    return user


def require_roles(*allowed: UserRole):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker


def is_privileged(user: User) -> bool:
    """Admin/manager bypasses owner checks."""
    return user.role in PRIVILEGED_ROLES


def can_mutate(user: User, owner_id: uuid.UUID | None) -> bool:
    """Permissive ownership: any authenticated user reads;
    only owner or admin/manager mutates. Orphan records (owner_id is None)
    are mutable by privileged users only."""
    if is_privileged(user):
        return True
    if owner_id is None:
        return False
    return owner_id == user.id


def ensure_can_mutate(user: User, owner_id: uuid.UUID | None) -> None:
    if not can_mutate(user, owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't own this record",
        )


async def get_current_org_id(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Resolve the current tenant for the authenticated user.

    Strategy:
      1. Prefer `user.last_active_org_id` — what the user picked the last
         time they were active. This survives logouts and page reloads.
      2. If that's NULL (membership was deleted, or this is the first
         login after a fresh install), fall back to the user's earliest
         membership. This keeps things working without forcing the user
         to "select an org" on every fresh session.
      3. If there are zero memberships, the user is in a broken state —
         403 with a clear message. (Phase 4's invite flow + the signup
         flow that creates an org-on-register both guarantee at least
         one membership exists by the time we reach here.)

    Never trust an `org_id` coming from request body / query string —
    that would let a logged-in attacker enumerate other tenants by
    swapping the id. This dep is the single source of truth.
    """
    if user.last_active_org_id is not None:
        org_id = user.last_active_org_id
    else:
        result = await db.execute(
            select(OrgMembership.organization_id)
            .where(OrgMembership.user_id == user.id)
            .order_by(OrgMembership.created_at.asc())
            .limit(1)
        )
        org_id = result.scalar_one_or_none()
        if org_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no organization membership",
            )

        # Pin the chosen org so subsequent requests don't repeat the lookup.
        user.last_active_org_id = org_id
        await db.commit()
        await db.refresh(user)

    # Phase 6 RLS: set the GUC the policies read. We use the
    # session-persistent form (`set_config(..., false)`, i.e. SET not
    # SET LOCAL) because routes commit mid-request — SET LOCAL would
    # be wiped on the next txn and subsequent queries (e.g.
    # `db.refresh()` after `db.commit()`) would return zero rows.
    # `get_db` clears this GUC on session close so the value can't
    # leak across pooled connections to a later request.
    await db.execute(
        text("SELECT set_config('app.current_org_id', :v, false)"),
        {"v": str(org_id)},
    )
    return org_id


async def get_current_org(
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Loads the current Organization object — useful for billing endpoints
    that need plan / seat_limit / stripe_* fields without a second query.
    """
    org = await db.get(Organization, org_id)
    if org is None:
        # Membership existed but the org was wiped — very degenerate state.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org


async def get_current_membership(
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> OrgMembership:
    """Membership row for the (user, current_org) pair — carries the role.

    The legacy `User.role` will be deprecated; in the meantime endpoints
    can read either. Org-scoped role checks (admin of org X but
    sales_agent in org Y) should use this dep, not user.role.
    """
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.organization_id == org_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        # Defensive: get_current_org_id already validated that a membership
        # exists, so reaching here means a race (membership deleted between
        # the two queries). Treat as 403, not 500.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No membership in the active organization",
        )
    return membership
