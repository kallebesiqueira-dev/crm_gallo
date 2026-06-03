"""Bearer-token auth for the Public API (/api/v1) — ADR-016.

This is a SECOND, distinct credential path from the browser model
(`app.deps.get_current_user`, cookie + CSRF). A server-to-server
integrator has no browser to hold a cookie and no origin to scope CSRF
to, so it presents an API key as ``Authorization: Bearer crmk_…``.

The flow, in order:
  1. Pull + shape-check the bearer token.
  2. Recover the org from the token (`crmk_{org_hex}_…`) and set the
     RLS GUC — so the key lookup runs UNDER row-level security. A token
     whose embedded org doesn't match the key's org returns zero rows
     (RLS) → 401, so the embedded org can't be used to reach another
     tenant's key.
  3. Look the key up by ``sha256(token)`` (single indexed seek), reject
     if revoked / expired.
  4. Resolve the key's creator user — the key is only valid while that
     user exists and is active (deactivating a user kills their keys;
     no orphaned credential outlives its human owner). That user is the
     audit actor for everything the key does.
  5. Scope check: GET→`read`, mutating verb→`write`.
  6. Per-key rate limit (Redis fixed-window).

Returns an `ApiPrincipal`, which the /api/v1 handlers unwrap into the
``(user, org_id)`` pair the existing CRUD logic already expects.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_keys import (
    decode_scopes,
    hash_token,
    parse_org_id,
    required_scope_for_method,
)
from app.config import get_settings
from app.database import get_db, set_current_org_id
from app.models import ApiKey, ApiKeyScope, User
from app.redis_client import get_redis

settings = get_settings()

_BEARER_PREFIX = "bearer "
_RL_PREFIX = "apikey_rl:"


@dataclass
class ApiPrincipal:
    """The resolved caller behind a valid API key."""

    api_key: ApiKey
    org_id: uuid.UUID
    # The key's creator — the audit actor + default `owner_id` for rows
    # the key creates. Always present (a key with no active creator is
    # rejected upstream).
    user: User
    scopes: set[ApiKeyScope]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith(_BEARER_PREFIX):
        raise _unauthorized("Missing or malformed Authorization: Bearer header")
    token = header[len(_BEARER_PREFIX) :].strip()
    if not token:
        raise _unauthorized("Empty bearer token")
    return token


async def _enforce_rate_limit(api_key_id: uuid.UUID) -> None:
    """Fixed-window-per-minute token budget, counted in Redis so the
    limit is global across replicas. Fail-open if Redis is down — a
    rate limiter must never become a hard dependency that takes the
    whole API offline (mirrors the in-memory fallback the SlowAPI
    limiter uses)."""
    limit = settings.api_key_rate_limit_per_minute
    window = int(time.time()) // 60
    redis_key = f"{_RL_PREFIX}{api_key_id}:{window}"
    try:
        r = get_redis()
        count = await r.incr(redis_key)
        if count == 1:
            # First hit in this window — set the TTL so the counter
            # self-expires. A hair over 60s absorbs clock skew.
            await r.expire(redis_key, 70)
    except Exception:
        return
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="API key rate limit exceeded",
            headers={"Retry-After": "60"},
        )


async def _touch_last_used(db: AsyncSession, api_key: ApiKey) -> None:
    """Refresh `last_used_at`, but at most once per throttle window so a
    GET doesn't become a write on every call. Committed in its own short
    transaction; the RLS GUC is re-applied by the begin event on the
    handler's next transaction."""
    now = datetime.now(UTC)
    throttle = settings.api_key_last_used_throttle_seconds
    if api_key.last_used_at is not None:
        age = (now - api_key.last_used_at).total_seconds()
        if age < throttle:
            return
    api_key.last_used_at = now
    await db.commit()


async def require_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiPrincipal:
    token = _extract_bearer(request)

    org_id = parse_org_id(token)
    if org_id is None:
        raise _unauthorized("Invalid API key")

    # Set the tenant GUC BEFORE the first query so the lookup runs under
    # RLS. No transaction is open on this session yet, so the begin event
    # will apply the GUC on the autobegin the SELECT triggers.
    set_current_org_id(org_id)

    result = await db.execute(select(ApiKey).where(ApiKey.hashed_key == hash_token(token)))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise _unauthorized("Invalid API key")

    if api_key.revoked_at is not None:
        raise _unauthorized("API key has been revoked")
    if api_key.expires_at is not None and api_key.expires_at <= datetime.now(UTC):
        raise _unauthorized("API key has expired")

    # The key acts on behalf of its creator. No creator (SET NULL after a
    # user delete) or an inactive creator → the key is dead.
    if api_key.created_by_user_id is None:
        raise _unauthorized("API key has no owning user")
    creator = await db.get(User, api_key.created_by_user_id)
    if creator is None or not creator.is_active:
        raise _unauthorized("API key's owning user is inactive")

    scopes = decode_scopes(api_key.scopes)
    needed = required_scope_for_method(request.method)
    if needed not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key lacks required scope: {needed.value}",
        )

    await _enforce_rate_limit(api_key.id)
    await _touch_last_used(db, api_key)

    return ApiPrincipal(api_key=api_key, org_id=org_id, user=creator, scopes=scopes)
