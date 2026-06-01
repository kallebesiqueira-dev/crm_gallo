"""Invite endpoints — admins generate single-use tokens, invitees accept
to land in the inviting org as a new member.

Token model:
  - Generated via `secrets.token_urlsafe(32)` → ~43 url-safe chars.
  - Stored exact (NO hashing) — tokens are short-lived and single-use; a
    hashed token would prevent lookup-by-token, which is the entire point
    of the public preview/accept endpoints.
  - One-shot: `accepted_at` is set atomically with the membership insert
    in the accept handler. Subsequent uses of the same token return 410.
  - 7-day expiry by default — long enough for "I'll forward this to Marco
    tomorrow", short enough that stale tokens get pruned naturally.

Security:
  - Create / list / revoke require **admin role in the target org** (not
    the legacy `User.role` — we check `OrgMembership.role` so a user
    who is admin in org A but sales_agent in org B can't invite people
    to org B).
  - Accept is unauthenticated. The token IS the authentication — same
    trust model as a password-reset link.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.billing import can_accept_new_user
from app.audit import record_audit
from app.config import get_settings
from app.cookies import issue_csrf_token, set_auth_cookies
from app.database import get_db
from app.deps import get_current_membership, get_current_org_id, get_current_user
from app.logging_setup import get_logger
from app.models import Organization, OrgInvite, OrgMembership, User, UserRole
from app.rate_limit import limiter
from app.redis_client import create_session
from app.schemas import (
    AuthResponse,
    InviteAcceptRequest,
    InviteCreate,
    InviteOut,
    InvitePreview,
    Token,
    UserOut,
)
from app.security import create_access_token, hash_password

log = get_logger(__name__)
settings = get_settings()

# Invite endpoints live under TWO routers because the auth surface
# differs. Admin endpoints below /api/orgs/current/invites are protected;
# the public preview + accept live under /api/invites and /api/auth.
admin_router = APIRouter(prefix="/api/orgs/current/invites", tags=["invites"])
public_router = APIRouter(prefix="/api/invites", tags=["invites"])
accept_router = APIRouter(prefix="/api/auth", tags=["auth"])


INVITE_TTL_DAYS = 7


def _new_token() -> str:
    """URL-safe random token. 32 bytes → ~43 chars after base64-url. Plenty
    of entropy for a 7-day single-use credential.
    """
    return secrets.token_urlsafe(32)


def _invite_url(token: str) -> str:
    """Where the invitee lands. Tied to the frontend success URL host so
    the link Just Works in dev (localhost:3030) and matches the env var
    operators already configure for Stripe.
    """
    base = settings.stripe_success_url.rsplit("/", 2)[0]  # strip /en/billing?…
    # Fall back to a sensible default if the Stripe URL is unconfigured.
    if not base:
        base = "http://localhost:3030"
    return f"{base}/invite/{token}"


def _ensure_admin(membership: OrgMembership) -> None:
    """Only admins of the CURRENT org can issue or revoke invites."""
    if membership.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only org admins can manage invites",
        )


# ──────────────────────────── Admin endpoints ────────────────────────────


@admin_router.post("", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def create_invite(
    payload: InviteCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    membership: OrgMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> InviteOut:
    _ensure_admin(membership)

    email = payload.email.lower().strip()

    # Refuse if the email already belongs to a member of this org. Issuing
    # an invite for an existing member would be a no-op confusion.
    existing_member = (
        await db.execute(
            select(OrgMembership)
            .join(User, User.id == OrgMembership.user_id)
            .where(
                OrgMembership.organization_id == org_id,
                User.email == email,
            )
        )
    ).scalar_one_or_none()
    if existing_member is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already a member of the organization",
        )

    # Soft dedupe: if there's a still-pending, still-valid invite for
    # the same email in this org, return it instead of issuing a new
    # one. Keeps the admin from generating duplicates by re-clicking.
    pending = (
        await db.execute(
            select(OrgInvite).where(
                OrgInvite.organization_id == org_id,
                OrgInvite.email == email,
                OrgInvite.accepted_at.is_(None),
                OrgInvite.expires_at > datetime.now(UTC),
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        out = InviteOut.model_validate(pending)
        out.invite_url = _invite_url(pending.token)
        return out

    invite = OrgInvite(
        organization_id=org_id,
        email=email,
        role=payload.role,
        token=_new_token(),
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_TTL_DAYS),
        created_by_user_id=user.id,
    )
    db.add(invite)
    await db.flush()

    await record_audit(
        db,
        actor=user,
        action="invite.create",
        entity_type="invite",
        entity_id=invite.id,
        organization_id=org_id,
        metadata={"email": email, "role": invite.role.value},
    )
    await db.commit()
    await db.refresh(invite)

    # Real SMTP belongs to P1 auth hardening. Until then the invite URL
    # is returned in the create response AND logged so an operator can
    # tail the backend log to find it.
    url = _invite_url(invite.token)
    log.info(
        "invite.dispatched",
        email=email,
        organization_id=str(org_id),
        invite_url=url,
    )

    out = InviteOut.model_validate(invite)
    out.invite_url = url
    return out


@admin_router.get("", response_model=list[InviteOut])
async def list_invites(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    membership: OrgMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[InviteOut]:
    _ensure_admin(membership)

    # Pending = not yet accepted AND not yet expired. Accepted/expired
    # invites stay in the table for audit but don't surface in the UI.
    now = datetime.now(UTC)
    result = await db.execute(
        select(OrgInvite)
        .where(
            OrgInvite.organization_id == org_id,
            OrgInvite.accepted_at.is_(None),
            OrgInvite.expires_at > now,
        )
        .order_by(OrgInvite.created_at.desc())
    )
    return [InviteOut.model_validate(i) for i in result.scalars().all()]


@admin_router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    invite_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    membership: OrgMembership = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> None:
    _ensure_admin(membership)

    result = await db.execute(
        select(OrgInvite).where(
            OrgInvite.id == invite_id,
            OrgInvite.organization_id == org_id,
        )
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        # 404, not 403 — same existence-leak rule as the rest of the
        # tenant surface.
        raise HTTPException(status_code=404, detail="Invite not found")

    await record_audit(
        db,
        actor=user,
        action="invite.revoke",
        entity_type="invite",
        entity_id=invite.id,
        organization_id=org_id,
        metadata={"email": invite.email},
    )
    await db.delete(invite)
    await db.commit()


# ──────────────────────────── Public endpoints ───────────────────────────


@public_router.get("/{token}", response_model=InvitePreview)
async def preview_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> InvitePreview:
    """No auth — anyone with the token can preview. The token itself is
    the credential. We DO check expiry / already-accepted here so the
    UI can render a clear "this invite has been used" / "expired" page
    instead of showing a register form that's going to fail."""
    result = await db.execute(select(OrgInvite).where(OrgInvite.token == token))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=410, detail="Invite already used")
    if invite.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Invite expired")

    org = await db.get(Organization, invite.organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization no longer exists")

    return InvitePreview(
        organization_id=org.id,
        organization_name=org.name,
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
    )


@accept_router.post(
    "/register-with-invite",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.rate_limit_login_per_minute}/minute")
async def register_with_invite(
    request: Request,
    response: Response,
    payload: InviteAcceptRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Create a new user account AND attach it to the inviting org in
    one atomic transaction. Same rate limit as /login to deter brute-
    forcing tokens via this endpoint.

    Scope for now: this endpoint is for NEW email addresses only. Adding
    an existing logged-in user to a new org via invite is a separate
    Phase 4b feature (would need an authenticated "accept" endpoint).
    """
    invite_result = await db.execute(select(OrgInvite).where(OrgInvite.token == payload.token))
    invite = invite_result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=410, detail="Invite already used")
    if invite.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Invite expired")

    # Refuse if a user with this email exists. They should log in then
    # follow a future "accept invite while logged in" flow.
    existing = (
        await db.execute(select(User).where(User.email == invite.email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "An account with this email already exists. "
                "Log in first and accept the invite from your dashboard."
            ),
        )

    # Seat check on the TARGET org — Free plan still caps at 2 even if
    # the admin generated unlimited invites. Token isn't burned yet
    # because the accept didn't go through.
    ok, reason = await can_accept_new_user(db, invite.organization_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=reason or "Organization seat limit reached.",
        )

    org = await db.get(Organization, invite.organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization no longer exists")

    user = User(
        email=invite.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=invite.role,  # legacy column — kept in sync with membership.role
        locale=payload.locale,
        last_active_org_id=org.id,
    )
    db.add(user)
    await db.flush()

    membership = OrgMembership(user_id=user.id, organization_id=org.id, role=invite.role)
    db.add(membership)

    # Burn the invite atomically with the user/membership insert.
    invite.accepted_at = datetime.now(UTC)

    await record_audit(
        db,
        actor=user,
        action="invite.accept",
        entity_type="invite",
        entity_id=invite.id,
        organization_id=org.id,
        metadata={"role": invite.role.value, "user_id": str(user.id)},
    )
    await db.commit()
    await db.refresh(user)

    token = Token(access_token=create_access_token(subject=str(user.id), role=user.role.value))
    # Mint + persist a refresh token alongside, matching the login /
    # register flow. Browsers pick up cookies; non-browser callers can
    # still grab the access JWT from the response body. UA/IP captured
    # for the /sessions UI.
    refresh = secrets.token_urlsafe(32)
    ua = (request.headers.get("user-agent") or "")[:200]
    ip = request.client.host if request.client else ""
    await create_session(
        token=refresh,
        user_id=str(user.id),
        ttl_seconds=settings.refresh_token_expire_days * 86400,
        user_agent=ua,
        ip_address=ip,
    )
    set_auth_cookies(
        response,
        access_token=token.access_token,
        csrf_token=issue_csrf_token(),
        refresh_token=refresh,
    )
    return AuthResponse(user=UserOut.model_validate(user), token=token)
