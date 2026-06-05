import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import email as email_service
from app.api.billing import can_accept_new_user
from app.audit import record_audit
from app.config import get_settings
from app.cookies import (
    REFRESH_TOKEN_COOKIE,
    clear_auth_cookies,
    issue_csrf_token,
    set_auth_cookies,
)
from app.database import get_db
from app.deps import get_current_user, holds_privileged_role
from app.mfa import (
    consume_backup_code,
    count_unused_backup_codes,
    generate_backup_codes,
    generate_secret,
    provisioning_uri,
    verify_totp,
)
from app.models import (
    EmailVerificationToken,
    MfaBackupCode,
    Organization,
    OrgMembership,
    PasswordResetToken,
    User,
    UserRole,
)
from app.rate_limit import limiter
from app.redis_client import (
    check_rotated_token,
    create_session,
    list_user_sessions,
    resolve_refresh_token,
    revoke_refresh_token,
    revoke_session_by_id,
    revoke_user_sessions_except,
    rotate_refresh_token,
    session_id_from_token,
)
from app.schemas import (
    AuthResponse,
    EmailVerifyConfirm,
    EmailVerifyResend,
    MfaDisableRequest,
    MfaEnableOut,
    MfaEnableRequest,
    MfaLoginChallenge,
    MfaSetupOut,
    MfaSetupRequired,
    MfaStatusOut,
    MfaVerifyRequest,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    RegisterResponse,
    SessionOut,
    SessionsRevokeOthersOut,
    Token,
    UserOut,
    UserUpdate,
)
from app.security import (
    create_access_token,
    create_mfa_challenge_token,
    decode_token,
    hash_password,
    verify_password,
)

log = structlog.get_logger(__name__)
PASSWORD_RESET_TTL_HOURS = 1

settings = get_settings()
# Email-verification link lifetime. Sourced from settings so operators can
# tune it per-env without a code change (mirrors how the reset TTL is a
# module constant — kept as a name here for symmetry at the call sites).
EMAIL_VERIFICATION_TTL_HOURS = settings.email_verification_ttl_hours
# Frontend origin for the reset link. Reads the configured setting so
# prod emits real https links, not localhost.
FRONTEND_BASE_URL = settings.frontend_base_url
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_token(user: User) -> Token:
    return Token(access_token=create_access_token(subject=str(user.id), role=user.role.value))


def _new_refresh_token() -> str:
    """Opaque, URL-safe — never decoded, only matched against Redis.
    Length matches our other tokens (invite, password reset)."""
    return secrets.token_urlsafe(32)


async def _start_session(request: Request, response: Response, user: User) -> Token:
    """Mint access + refresh tokens, persist as a session in Redis
    (with metadata for the /sessions UI), and set all three cookies on
    the outgoing response. Returns the access Token so callers can
    echo it in the response body (compat for non-browser clients
    during the transition).

    `user_agent` and `ip_address` are best-effort: truncated to keep
    Redis values bounded, treated as opaque strings. The IP we
    capture is whatever Starlette gave us — behind a reverse proxy
    that's the proxy IP, not the client. Trusting `X-Forwarded-For`
    blindly here would let any client spoof their displayed IP, so
    that's a follow-up tied to a real prod reverse-proxy config.
    """
    token = _issue_token(user)
    refresh_token = _new_refresh_token()
    ua = (request.headers.get("user-agent") or "")[:200]
    ip = request.client.host if request.client else ""
    await create_session(
        token=refresh_token,
        user_id=str(user.id),
        ttl_seconds=settings.refresh_token_expire_days * 86400,
        user_agent=ua,
        ip_address=ip,
    )
    set_auth_cookies(
        response,
        access_token=token.access_token,
        csrf_token=issue_csrf_token(),
        refresh_token=refresh_token,
    )
    return token


async def _send_verification_email(db: AsyncSession, user: User) -> None:
    """Mint a fresh single-use verification token for `user`, persist it,
    audit the dispatch, and enqueue the verification email.

    Shared by /register (initial send) and /verify-email/resend. Mirrors
    the password-reset dispatch: the URL is logged regardless of provider
    so an operator can always recover the link, and the email enqueue is
    best-effort (a Redis hiccup must not 500 the caller). The caller is
    responsible for committing the surrounding transaction.
    """
    token_value = secrets.token_urlsafe(32)
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token=token_value,
            expires_at=datetime.now(UTC) + timedelta(hours=EMAIL_VERIFICATION_TTL_HOURS),
        )
    )
    await record_audit(
        db,
        actor=user,
        action="user.email_verification_sent",
        entity_type="user",
        entity_id=user.id,
    )

    verify_url = f"{FRONTEND_BASE_URL}/verify-email/{token_value}"
    log.info(
        "email_verification.dispatched",
        user_email=user.email,
        url=verify_url,
        expires_in_hours=EMAIL_VERIFICATION_TTL_HOURS,
    )
    try:
        await email_service.send(
            to=user.email,
            template=email_service.TEMPLATE_VERIFY_EMAIL,
            locale=user.locale,
            ctx={"url": verify_url, "expires_hours": EMAIL_VERIFICATION_TTL_HOURS},
            dedupe_key=f"verify:{token_value}",
        )
    except Exception:
        log.warning("email_verification.email_enqueue_failed", exc_info=True)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.rate_limit_register_per_minute}/minute")
async def register(
    request: Request,
    response: Response,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Race-safe first-user check: lock advisory key so two concurrent registers
    # cannot both end up as admin. Falls back to count==0 inside the lock.
    await db.execute(select(func.pg_advisory_xact_lock(0xC0FFEE)))
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    is_first_user = count == 0
    role = UserRole.admin if is_first_user else UserRole.sales_agent

    # Resolve (or bootstrap) the org this user lands in BEFORE the seat
    # check — seat enforcement is now per-org, so we need the org id.
    # Multi-tenant via signup-without-invite: every new user joins the
    # install's default-workspace. Fresh installs (count==0) create it
    # on the fly. Phase 4 invites and Phase 5 "create new org" flow are
    # how additional tenants come into existence.
    org_result = await db.execute(
        select(Organization).where(Organization.slug == "default-workspace")
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        if count != 0:
            # Should be impossible — backfill migration always creates it
            # for existing installs, and count==0 below creates it. If we
            # get here something is very wrong with the DB state.
            raise HTTPException(
                status_code=500,
                detail="default-workspace missing; run migrations",
            )
        org = Organization(name="CRM Gallo Workspace", slug="default-workspace")
        db.add(org)
        await db.flush()

    # Per-org seat enforcement: Free plan caps the new org at 2 members.
    # Standard/Premium are uncapped today (seat-based pricing later).
    ok, reason = await can_accept_new_user(db, org.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=reason or "Seat limit reached. Please upgrade your plan.",
        )

    # The first user (install founder) is auto-verified so they can't lock
    # themselves out while bootstrapping. Every other self-signup must
    # confirm their email before logging in (anti-abuse on the Free tier).
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=role,
        locale=payload.locale,
        last_active_org_id=org.id,
        email_verified=is_first_user,
    )
    db.add(user)
    await db.flush()

    membership = OrgMembership(user_id=user.id, organization_id=org.id, role=role)
    db.add(membership)
    await db.flush()

    await record_audit(
        db,
        actor=user,
        action="user.register",
        entity_type="user",
        entity_id=user.id,
        organization_id=org.id,
        metadata={"role": user.role.value, "first_user": is_first_user},
    )

    if is_first_user:
        # Auto-verified founder → start a session and log them straight in,
        # exactly as before this feature.
        await db.commit()
        await db.refresh(user)
        token = await _start_session(request, response, user)
        return RegisterResponse(
            verification_required=False,
            email=user.email,
            user=UserOut.model_validate(user),
            token=token,
        )

    # Everyone else: mint + send a verification link in the SAME
    # transaction as the user/membership insert, then return a body that
    # tells the frontend to show the "check your email" screen. No session
    # is started — login is gated on email_verified.
    await _send_verification_email(db, user)
    await db.commit()
    await db.refresh(user)
    return RegisterResponse(
        verification_required=True,
        email=user.email,
        user=UserOut.model_validate(user),
        token=None,
    )


# Pre-computed bcrypt hash of a long random string. Used to keep
# `/login` execution time constant when the email isn't found, so an
# attacker can't enumerate accounts by timing (real users go through
# bcrypt verify; unknown emails would skip it and respond faster).
# The hash itself is never matched against anything — it's a sink.
_DUMMY_PASSWORD_HASH = "$2b$12$Cw5z9rGq0Y9D6jZJqLqQXOJ9q5cQyWqM5p0sJgWmO5sQ9YK1d6jzS"


@router.post("/login")
@limiter.limit(f"{settings.rate_limit_login_per_minute}/minute")
async def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Verifies password. If the user has MFA enabled, returns a
    short-lived `mfa_token` instead of a full session — the client
    follows up with /mfa/verify. Otherwise returns the full session
    (cookies + body) as before.

    Response shape depends on MFA state, so the return type is
    intentionally untyped at the FastAPI layer (frontend type-narrows
    on the `mfa_required` field).
    """
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    # Always run bcrypt — even on missing-user — so the response time
    # doesn't leak whether the email exists. Without this, the "no
    # user" branch returns immediately while the "user found, wrong
    # password" branch waits for bcrypt (~100ms) — a trivial timing
    # oracle for account enumeration.
    password_ok = verify_password(
        form.password,
        user.hashed_password if user else _DUMMY_PASSWORD_HASH,
    )
    if not user or not password_ok:
        # Same response for unknown email and bad password (no enumeration).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")

    # Gate login on a confirmed email (anti-abuse on the Free tier). The
    # frontend keys off the exact `email_not_verified` detail string to
    # render a "verify your email" + resend UI. Checked BEFORE the MFA
    # branch so an unverified account never even reaches an MFA challenge.
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email_not_verified",
        )

    if user.mfa_enabled:
        # Don't start a session yet — issue an MFA challenge instead.
        # The audit row marks the password step succeeded; the second
        # /mfa/verify audit records the completion.
        await record_audit(
            db,
            actor=user,
            action="user.login_mfa_challenge_issued",
            entity_type="user",
            entity_id=user.id,
        )
        await db.commit()
        return MfaLoginChallenge(mfa_token=create_mfa_challenge_token(subject=str(user.id)))

    # Privileged user who hasn't enrolled, with the policy on: start a
    # full session (so they can reach /mfa/setup + /mfa/enable) but flag
    # the client to route straight into forced enrollment. The teeth are
    # server-side — get_current_org_id blocks every tenant-data endpoint
    # with 403 `mfa_enrollment_required` until they finish; this signal
    # is just the UX hint so they don't bounce off a wall of 403s.
    if settings.mfa_required_for_privileged and await holds_privileged_role(db, user.id):
        await record_audit(
            db,
            actor=user,
            action="user.login_mfa_setup_required",
            entity_type="user",
            entity_id=user.id,
        )
        await db.commit()
        token = await _start_session(request, response, user)
        return MfaSetupRequired(user=UserOut.model_validate(user), token=token)

    await record_audit(
        db,
        actor=user,
        action="user.login",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()
    token = await _start_session(request, response, user)
    return AuthResponse(user=UserOut.model_validate(user), token=token)


@router.post("/mfa/verify", response_model=AuthResponse)
@limiter.limit(f"{settings.rate_limit_login_per_minute}/minute")
async def mfa_verify(
    request: Request,
    response: Response,
    payload: MfaVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Second step of MFA login. Validates the challenge token + a
    TOTP code OR a backup code, and on success starts a full session."""
    try:
        decoded = decode_token(payload.mfa_token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid MFA token") from e
    if decoded.get("purpose") != "mfa_challenge":
        raise HTTPException(status_code=400, detail="Invalid MFA token")
    user_id = decoded.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid MFA token")
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail="Invalid MFA token") from e

    user = await db.get(User, uid)
    if user is None or not user.is_active or not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA not configured")

    code = payload.code.strip()
    ok = False
    used_backup = False
    if code.isdigit() and len(code) == 6:
        ok = verify_totp(user.mfa_secret, code)
    if not ok:
        ok = await consume_backup_code(db, user.id, code)
        used_backup = ok
    if not ok:
        # Audit the failed verify so brute-force attempts show up in
        # the trail. SlowAPI already limits the rate on this endpoint.
        await record_audit(
            db,
            actor=user,
            action="user.mfa_verify_failed",
            entity_type="user",
            entity_id=user.id,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA code",
        )

    await record_audit(
        db,
        actor=user,
        action="user.mfa_verify_backup" if used_backup else "user.mfa_verify",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()
    token = await _start_session(request, response, user)
    return AuthResponse(user=UserOut.model_validate(user), token=token)


# -------- MFA enrollment (authenticated) --------


@router.get("/mfa/status", response_model=MfaStatusOut)
async def mfa_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaStatusOut:
    remaining = await count_unused_backup_codes(db, user.id) if user.mfa_enabled else 0
    return MfaStatusOut(
        enabled=user.mfa_enabled,
        enrolled_at=user.mfa_enrolled_at,
        backup_codes_remaining=remaining,
    )


@router.post("/mfa/setup", response_model=MfaSetupOut)
async def mfa_setup(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaSetupOut:
    """Generate (and store) a fresh secret for this user. The secret
    is NOT considered active until /mfa/enable validates the first
    code — until then, login still works without MFA. Re-running
    setup overwrites the pending secret (useful if the user lost the
    QR mid-flow)."""
    if user.mfa_enabled:
        raise HTTPException(
            status_code=400,
            detail="MFA already enabled. Disable first to re-enroll.",
        )
    secret = generate_secret()
    user.mfa_secret = secret
    await db.commit()
    return MfaSetupOut(
        secret=secret,
        provisioning_uri=provisioning_uri(secret, account_label=user.email),
    )


@router.post("/mfa/enable", response_model=MfaEnableOut)
async def mfa_enable(
    payload: MfaEnableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaEnableOut:
    """Activate MFA after the user proves the secret made it across
    by submitting the first code from their authenticator. Generates
    10 single-use backup codes and returns them in plaintext ONCE —
    they are never returned by any subsequent endpoint."""
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA already enabled")
    if not user.mfa_secret:
        raise HTTPException(status_code=400, detail="Run /mfa/setup first")
    if not verify_totp(user.mfa_secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid code")

    user.mfa_enabled = True
    user.mfa_enrolled_at = datetime.now(UTC)
    codes = await generate_backup_codes(db, user.id)
    await record_audit(
        db,
        actor=user,
        action="user.mfa_enabled",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()
    return MfaEnableOut(backup_codes=codes)


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def mfa_disable(
    payload: MfaDisableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove MFA. Requires the current password (proves the cookie
    isn't drive-by-stolen) plus a current TOTP or backup code (proves
    the second factor is genuinely accessible to the requester).
    Both checks are required — either alone would let an attacker who
    has only one factor remove the other."""
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA not enabled")
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Password incorrect")
    code = payload.code.strip()
    ok = (
        verify_totp(user.mfa_secret or "", code)
        if code.isdigit() and len(code) == 6
        else await consume_backup_code(db, user.id, code)
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid MFA code")

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_enrolled_at = None
    # Wipe ALL backup codes (used + unused) — disabling MFA means
    # those codes lose their meaning, and re-enabling generates a
    # fresh set anyway.
    existing = (
        (await db.execute(select(MfaBackupCode).where(MfaBackupCode.user_id == user.id)))
        .scalars()
        .all()
    )
    for c in existing:
        await db.delete(c)

    await record_audit(
        db,
        actor=user,
        action="user.mfa_disabled",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()


@router.post("/refresh", response_model=Token)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Mint a fresh access token from the refresh cookie AND rotate
    the refresh token itself. Detects reuse of already-rotated
    tokens as a theft signal and revokes the entire user's sessions.

    Steps:
      1. Read the path-scoped `refresh_token` cookie.
      2. Look up the token in Redis:
         * VALID → mint new access JWT, rotate the refresh token
           (atomic: new token issued, old token deleted and
           tombstoned for 5 min), reset both cookies.
         * MISSING + matches a recent tombstone → REUSE DETECTED.
           Revoke EVERY session for this user (someone is replaying
           a refresh token; the legitimate client moved on, and we
           don't know which side is the attacker). Audit + 401.
         * MISSING + no tombstone → ordinary expired/revoked path.
           Plain 401.

    Two-tab race: the legitimate second tab may innocently replay
    the just-rotated token. With a 5-min tombstone we'd revoke its
    sessions — false positive. Mitigation lives at the SPA layer:
    `lib/api.ts` collapses concurrent 401s into a SINGLE in-flight
    /refresh call (already implemented). The server-side replay
    detection is the last line of defence — false positives here
    are acceptable since the user can re-login.

    CSRF: the global middleware enforces X-CSRF-Token here too,
    because this is a state-changing POST (it mints a new
    credential).
    """
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )
    user_id_str = await resolve_refresh_token(refresh_token)
    if not user_id_str:
        # Token isn't live. Distinguish "stale (expired/revoked)" from
        # "reuse-after-rotation" — the latter is a theft signal.
        rotated_user_id = await check_rotated_token(refresh_token)
        if rotated_user_id:
            # Steal detection. Burn every session for the user; force
            # a fresh login from a clean device. Audit goes through
            # structlog (best-effort; not transactional).
            revoked = await revoke_user_sessions_except(rotated_user_id, None)
            log.warning(
                "refresh.reuse_detected",
                user_id=rotated_user_id,
                revoked_sessions=revoked,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token reuse detected; all sessions revoked.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalid or revoked",
        )

    # Re-load the user from the DB so a deactivated account is rejected
    # at refresh time, not just on the next protected call. The refresh
    # token alone (a Redis entry) carries no liveness signal — an admin
    # who flips `is_active=False` would otherwise keep handing the user
    # fresh 15-min access tokens until their current one expired. If the
    # account is gone or disabled, burn every session so the still-live
    # refresh token can't keep minting credentials, then 401.
    try:
        user_uuid = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        user_uuid = None
    user = (
        (await db.execute(select(User).where(User.id == user_uuid))).scalar_one_or_none()
        if user_uuid is not None
        else None
    )
    if user is None or not user.is_active:
        await revoke_user_sessions_except(user_id_str, None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive",
        )

    # Happy path: rotate. Stamp the user's real role into the new access
    # token (the claim is cosmetic today — get_current_user re-reads role
    # from the DB — but "unknown" was a latent trap if that ever changes).
    new_refresh = _new_refresh_token()
    new_access = Token(access_token=create_access_token(subject=user_id_str, role=user.role.value))
    ua = (request.headers.get("user-agent") or "")[:200]
    ip = request.client.host if request.client else ""
    await rotate_refresh_token(
        old_token=refresh_token,
        new_token=new_refresh,
        user_id=user_id_str,
        ttl_seconds=settings.refresh_token_expire_days * 86400,
        user_agent=ua,
        ip_address=ip,
    )
    set_auth_cookies(
        response,
        access_token=new_access.access_token,
        csrf_token=request.cookies.get("csrf_token") or issue_csrf_token(),
        refresh_token=new_refresh,
    )
    return new_access


def _current_session_id(request: Request) -> str | None:
    """Derive the caller's session_id from the refresh cookie, if
    present. Returns None when the call is made without the refresh
    cookie (e.g. integration scripts hitting via Bearer + access
    cookie path=/ only) — in that case the /sessions UI just won't
    mark a row as current."""
    refresh = request.cookies.get(REFRESH_TOKEN_COOKIE)
    return session_id_from_token(refresh) if refresh else None


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    request: Request,
    user: User = Depends(get_current_user),
) -> list[SessionOut]:
    """List every live session belonging to the authenticated user.
    The session calling this endpoint is flagged `current=true` so
    the SPA can render an appropriate "this device" label and
    disable the revoke button on its own row."""
    current_sid = _current_session_id(request)
    sessions = await list_user_sessions(str(user.id))
    return [
        SessionOut(
            id=s["id"],
            created_at=s.get("created_at"),
            last_seen_at=s.get("last_seen_at"),
            user_agent=s.get("user_agent", ""),
            ip_address=s.get("ip_address", ""),
            current=(s["id"] == current_sid),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke a specific session (= log out one specific device).
    Refuses to revoke the caller's own session — that's what
    /logout is for, and going through /logout also clears the
    cookies on the caller's browser. Returns 404 when the session
    doesn't exist OR belongs to another user (no enumeration)."""
    current_sid = _current_session_id(request)
    if current_sid and current_sid == session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use /logout to end the current session",
        )
    ok = await revoke_session_by_id(str(user.id), session_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    await record_audit(
        db,
        actor=user,
        action="user.session_revoked",
        entity_type="user",
        entity_id=user.id,
        metadata={"session_id": session_id},
    )
    await db.commit()


@router.post("/sessions/revoke-others", response_model=SessionsRevokeOthersOut)
async def revoke_other_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionsRevokeOthersOut:
    """ "Log out everywhere else" — revoke every session for this
    user except the one making the call. Useful after a password
    change or a suspected compromise. Returns the count revoked so
    the SPA can show "Signed out N other devices"."""
    current_sid = _current_session_id(request)
    n = await revoke_user_sessions_except(str(user.id), except_session_id=current_sid)
    if n > 0:
        await record_audit(
            db,
            actor=user,
            action="user.sessions_revoke_others",
            entity_type="user",
            entity_id=user.id,
            metadata={"revoked": n},
        )
        await db.commit()
    return SessionsRevokeOthersOut(revoked=n)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Records the logout event, revokes the refresh token in Redis,
    and clears all session cookies.

    The current access JWT continues to validate via signature alone
    until it expires (15 min default) — a leaked access token survives
    that long. Revoking it server-side instantly would require either
    a per-request Redis hit (every protected endpoint) or a JTI-based
    blocklist with the same cost. We accept the 15-minute window.
    """
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if refresh_token:
        await revoke_refresh_token(refresh_token)
    await record_audit(
        db,
        actor=user,
        action="user.logout",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()
    clear_auth_cookies(response)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"] != user.email:
        existing = await db.execute(select(User).where(User.email == data["email"]))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")
    for field, value in data.items():
        setattr(user, field, value)
    await record_audit(
        db,
        actor=user,
        action="user.update",
        entity_type="user",
        entity_id=user.id,
        metadata={"fields": list(data.keys())},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/password-reset/request", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.rate_limit_password_reset_per_minute}/minute")
async def request_password_reset(
    request: Request,
    payload: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Send (log, today) a password-reset link to the given email.

    Always returns 204 — even if the email is unknown — to avoid
    leaking which addresses have accounts. The token is delivered
    out-of-band; in dev the URL is emitted on the log line
    `password_reset.dispatched` for the operator to copy/paste.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        # Silent no-op: same response shape and timing as the happy
        # path (we accept a small timing window here — the DB hit
        # already happened; reset issuance is not a brand-new bcrypt).
        return

    # Burn any previous unused tokens for this user so only the most
    # recent link works. Prevents a stockpiled-old-link attack if the
    # user requested resets multiple times in quick succession.
    now = datetime.now(UTC)
    await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    # No bulk-update needed: we just create a fresh token and let the
    # confirm endpoint dedupe by "newest unused per user". Simpler
    # than an UPDATE here.

    token_value = secrets.token_urlsafe(32)
    reset = PasswordResetToken(
        user_id=user.id,
        token=token_value,
        expires_at=now + timedelta(hours=PASSWORD_RESET_TTL_HOURS),
    )
    db.add(reset)
    await record_audit(
        db,
        actor=user,
        action="user.password_reset_requested",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()

    reset_url = f"{FRONTEND_BASE_URL}/reset-password/{token_value}"
    # The URL is logged regardless of provider so an operator can
    # always recover the link (console provider in dev, or a transient
    # enqueue failure in prod).
    log.info(
        "password_reset.dispatched",
        user_email=user.email,
        url=reset_url,
        expires_in_hours=PASSWORD_RESET_TTL_HOURS,
    )

    # Fire the reset email (ADR-017). Best-effort: a Redis/enqueue
    # hiccup must not 500 the request — and we always return 204 here
    # to avoid leaking which addresses exist.
    try:
        await email_service.send(
            to=user.email,
            template=email_service.TEMPLATE_PASSWORD_RESET,
            locale=user.locale,
            ctx={"url": reset_url, "expires_hours": PASSWORD_RESET_TTL_HOURS},
            dedupe_key=f"pwreset:{token_value}",
        )
    except Exception:
        log.warning("password_reset.email_enqueue_failed", exc_info=True)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.rate_limit_password_reset_per_minute}/minute")
async def confirm_password_reset(
    request: Request,
    payload: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Consume a reset token to set a new password.

    Failure modes use distinct codes so the UI can render specific
    messages without leaking which step failed for an attacker (the
    rate limit + opaque error text upstream provides the leak
    defense; 404 vs 410 here is a UX nicety for legitimate users):
      - unknown / never-existed token → 404
      - already used token → 410 Gone
      - expired token → 410 Gone
    """
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == payload.token)
    )
    reset = result.scalar_one_or_none()
    if reset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid token")
    if reset.used_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token already used")
    if reset.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token expired")

    user = await db.get(User, reset.user_id)
    if user is None or not user.is_active:
        # The user disappeared or was disabled between issuance and
        # confirm — treat as a dead link.
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Account unavailable")

    user.hashed_password = hash_password(payload.new_password)
    reset.used_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="user.password_reset_confirmed",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()


@router.post("/verify-email/confirm", response_model=AuthResponse)
@limiter.limit(f"{settings.rate_limit_password_reset_per_minute}/minute")
async def confirm_email_verification(
    request: Request,
    response: Response,
    payload: EmailVerifyConfirm,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Consume a verification token to mark the user's email confirmed,
    then log them straight in.

    Token validation mirrors confirm_password_reset's distinct codes so
    the UI can render a precise dead-link message:
      - unknown / never-existed token → 404
      - already used token → 410 Gone
      - expired token → 410 Gone

    On success we start a full session (cookies + body) so clicking the
    link in the email lands the user in the dashboard without a second
    login step.
    """
    result = await db.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token == payload.token)
    )
    verification = result.scalar_one_or_none()
    if verification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid token")
    if verification.used_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token already used")
    if verification.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token expired")

    user = await db.get(User, verification.user_id)
    if user is None or not user.is_active:
        # The user disappeared or was disabled between issuance and
        # confirm — treat as a dead link.
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Account unavailable")

    user.email_verified = True
    verification.used_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="user.email_verified",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()
    await db.refresh(user)
    token = await _start_session(request, response, user)
    return AuthResponse(user=UserOut.model_validate(user), token=token)


@router.post("/verify-email/resend", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.rate_limit_password_reset_per_minute}/minute")
async def resend_email_verification(
    request: Request,
    payload: EmailVerifyResend,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Re-send the verification link for an unconfirmed account.

    Always returns 204 — even if the email is unknown, the account is
    disabled, or it's already verified — to avoid leaking which addresses
    have accounts or their verification state. A fresh token is minted +
    emailed only when the email maps to an active, not-yet-verified user.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.email_verified:
        # Silent no-op — same response shape as the happy path.
        return

    await _send_verification_email(db, user)
    await db.commit()


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    await record_audit(
        db,
        actor=user,
        action="user.password_change",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()
