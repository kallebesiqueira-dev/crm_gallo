"""Async Redis client + session / refresh-token storage.

Single shared connection pool (one per worker process). We use Redis
for the session store; future uses (idempotency keys, rate-limit
state, background-job queues) will share this pool.

Schema:
  * `refresh:{token}`           → user_id (string)
        Fast lookup for token-validation on /refresh.
  * `session:{session_id}`      → hash {user_id, token, created_at,
                                        last_seen_at, user_agent,
                                        ip_address}
        Metadata for the "active sessions" UI. `session_id` is
        deterministically derived as `sha256(token)[:32]` so we never
        need a reverse index — given a token we know its session_id,
        and the session_id alone is safe to expose (one-way from the
        secret, so showing it in the SPA cannot be used to forge
        the cookie).
  * `user_sessions:{user_id}`   → SET of session_ids
        Enables "list my sessions" and "log out other devices"
        without scanning the keyspace.

All three keys share the same TTL = refresh_token_expire_days. Redis
purges them automatically; no sweeper job needed. A session SET that
loses its hash before its SET entry (e.g. clock skew at edge of TTL)
gets cleaned up lazily by `list_user_sessions`.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import redis.asyncio as redis

from app.config import get_settings

_REFRESH_KEY_PREFIX = "refresh:"
_SESSION_KEY_PREFIX = "session:"
_USER_SESSIONS_PREFIX = "user_sessions:"
# Short-lived tombstone for tokens that were just rotated. A /refresh
# call landing on a tombstoned token is the steal-detection signal:
# the legitimate client moved on to the successor token; whoever is
# now presenting the old one is replaying. TTL = 5 min covers
# in-flight two-tab races without leaving the tombstone forever.
_USED_REFRESH_PREFIX = "refresh_used:"
_USED_REFRESH_TTL = 300

_pool: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Lazy singleton — first call constructs the connection pool,
    subsequent calls reuse it. Pool size defaults are fine for a single
    uvicorn worker; revisit when we add Gunicorn + multi-worker."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _pool


def session_id_from_token(token: str) -> str:
    """Derive a stable, opaque session identifier from a refresh token.

    SHA-256 truncated to 32 hex chars (128 bits) is plenty for
    collision-resistance across a single user's session set. Safe to
    expose to the SPA: there's no preimage that would let an attacker
    forge a refresh cookie from a leaked session_id.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


# ---------- Session lifecycle ----------


async def create_session(
    token: str,
    user_id: str,
    ttl_seconds: int,
    user_agent: str = "",
    ip_address: str = "",
) -> str:
    """Register a new refresh token + session metadata atomically.

    Returns the session_id (derived from the token) so the caller can
    log it / surface it in audit. All three Redis writes happen in one
    transactional pipeline so a crash between them can't leave a token
    valid but missing from the user's session list.
    """
    sid = session_id_from_token(token)
    now = datetime.now(UTC).isoformat()
    r = get_redis()
    async with r.pipeline(transaction=True) as p:
        p.set(_REFRESH_KEY_PREFIX + token, user_id, ex=ttl_seconds)
        p.hset(
            _SESSION_KEY_PREFIX + sid,
            mapping={
                "user_id": user_id,
                "token": token,
                "created_at": now,
                "last_seen_at": now,
                # `redis-py` rejects None — coerce explicitly to ""
                # since these are optional per the function signature.
                "user_agent": user_agent or "",
                "ip_address": ip_address or "",
            },
        )
        p.expire(_SESSION_KEY_PREFIX + sid, ttl_seconds)
        p.sadd(_USER_SESSIONS_PREFIX + user_id, sid)
        # Bump the user-set TTL on every new session so the set stays
        # alive as long as ANY session is alive (max of any session's
        # remaining TTL). Stale entries are also cleaned in list_*.
        p.expire(_USER_SESSIONS_PREFIX + user_id, ttl_seconds)
        await p.execute()
    return sid


async def resolve_refresh_token(token: str) -> str | None:
    """Return the user_id this token belongs to, or None if the token
    is unknown / expired / revoked."""
    r = get_redis()
    return await r.get(_REFRESH_KEY_PREFIX + token)


async def touch_session(token: str) -> None:
    """Bump `last_seen_at` for the session backing this token. Called
    from /refresh so the "active sessions" UI reflects recent use.
    Silent no-op if the session metadata is missing (shouldn't happen,
    but treat as best-effort)."""
    sid = session_id_from_token(token)
    r = get_redis()
    # HSET only if the key exists — avoids resurrecting a key that
    # was just revoked in a race. `expire` keyword on HSET isn't
    # available in our redis-py version; do it via two ops.
    if await r.exists(_SESSION_KEY_PREFIX + sid):
        await r.hset(
            _SESSION_KEY_PREFIX + sid,
            "last_seen_at",
            datetime.now(UTC).isoformat(),
        )


async def rotate_refresh_token(
    old_token: str,
    new_token: str,
    user_id: str,
    ttl_seconds: int,
    user_agent: str = "",
    ip_address: str = "",
) -> str:
    """Atomic refresh-token rotation. Deletes the old refresh key +
    its session metadata, registers the new token + new session, and
    tombstones the old token for `_USED_REFRESH_TTL` seconds so a
    replay can be detected. Returns the new session_id.

    The tombstone window MUST be short — a long one means a stolen
    token gives the attacker that much time to use it. But it must
    be long enough to absorb in-flight requests from a legitimate
    second tab racing the rotation. 5 minutes is a reasonable
    floor; tune via `_USED_REFRESH_TTL` if telemetry suggests
    otherwise.
    """
    new_sid = session_id_from_token(new_token)
    old_sid = session_id_from_token(old_token)
    now = datetime.now(UTC).isoformat()
    r = get_redis()
    async with r.pipeline(transaction=True) as p:
        # New token + new session
        p.set(_REFRESH_KEY_PREFIX + new_token, user_id, ex=ttl_seconds)
        p.hset(
            _SESSION_KEY_PREFIX + new_sid,
            mapping={
                "user_id": user_id,
                "token": new_token,
                "created_at": now,
                "last_seen_at": now,
                "user_agent": user_agent or "",
                "ip_address": ip_address or "",
            },
        )
        p.expire(_SESSION_KEY_PREFIX + new_sid, ttl_seconds)
        p.sadd(_USER_SESSIONS_PREFIX + user_id, new_sid)
        p.expire(_USER_SESSIONS_PREFIX + user_id, ttl_seconds)
        # Retire the old token
        p.delete(_REFRESH_KEY_PREFIX + old_token)
        p.delete(_SESSION_KEY_PREFIX + old_sid)
        p.srem(_USER_SESSIONS_PREFIX + user_id, old_sid)
        # Tombstone — pairs the old token with the user_id so the
        # steal-detection path can revoke the rest of the family.
        p.set(
            _USED_REFRESH_PREFIX + old_token,
            user_id,
            ex=_USED_REFRESH_TTL,
        )
        await p.execute()
    return new_sid


async def check_rotated_token(token: str) -> str | None:
    """Return the user_id this (now-tombstoned) token belonged to,
    or None if the token is not in the tombstone. Used by /refresh
    to detect replays after rotation."""
    r = get_redis()
    return await r.get(_USED_REFRESH_PREFIX + token)


async def revoke_refresh_token(token: str) -> bool:
    """Revoke a single session by its refresh token. Deletes the
    refresh→user_id key, the session hash, and removes the session_id
    from the user's set — all in one transactional pipeline so partial
    cleanup can't strand orphan entries. Returns True if anything was
    deleted (i.e. the token was a real live session)."""
    r = get_redis()
    sid = session_id_from_token(token)
    user_id = await r.get(_REFRESH_KEY_PREFIX + token)
    async with r.pipeline(transaction=True) as p:
        p.delete(_REFRESH_KEY_PREFIX + token)
        p.delete(_SESSION_KEY_PREFIX + sid)
        if user_id:
            p.srem(_USER_SESSIONS_PREFIX + user_id, sid)
        results = await p.execute()
    # results[0] is the count of refresh keys deleted (0 or 1).
    return bool(results[0])


# ---------- Sessions listing / multi-session revoke ----------


async def list_user_sessions(user_id: str) -> list[dict]:
    """Return all live sessions for a user — each as a dict with
    `id`, `created_at`, `last_seen_at`, `user_agent`, `ip_address`.
    Drops and self-heals SET entries whose session hash has already
    expired (TTL drift)."""
    r = get_redis()
    sids = await r.smembers(_USER_SESSIONS_PREFIX + user_id)
    sessions: list[dict] = []
    stale: list[str] = []
    for sid in sids:
        data = await r.hgetall(_SESSION_KEY_PREFIX + sid)
        if not data:
            stale.append(sid)
            continue
        sessions.append(
            {
                "id": sid,
                "created_at": data.get("created_at"),
                "last_seen_at": data.get("last_seen_at"),
                "user_agent": data.get("user_agent", ""),
                "ip_address": data.get("ip_address", ""),
            }
        )
    if stale:
        await r.srem(_USER_SESSIONS_PREFIX + user_id, *stale)
    # Newest first so the UI puts the user's current device near the top.
    sessions.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return sessions


async def revoke_session_by_id(user_id: str, session_id: str) -> bool:
    """Revoke a specific session, checking it belongs to this user
    (so /sessions/{id} cannot be used to enumerate or revoke other
    users' sessions). Returns True if a session was found and revoked."""
    r = get_redis()
    data = await r.hgetall(_SESSION_KEY_PREFIX + session_id)
    if not data or data.get("user_id") != user_id:
        return False
    token = data.get("token")
    if token:
        return await revoke_refresh_token(token)
    # Orphan: hash exists but lost its token field (shouldn't happen
    # in normal use). Clean up the dangling references anyway.
    async with r.pipeline(transaction=True) as p:
        p.delete(_SESSION_KEY_PREFIX + session_id)
        p.srem(_USER_SESSIONS_PREFIX + user_id, session_id)
        await p.execute()
    return True


async def revoke_user_sessions_except(user_id: str, except_session_id: str | None) -> int:
    """Revoke every session for this user except the one identified
    by `except_session_id` (typically the caller's own session, so
    "log out other devices" doesn't log YOU out). Returns the count
    of sessions revoked. Pass None to revoke all sessions."""
    r = get_redis()
    sids = await r.smembers(_USER_SESSIONS_PREFIX + user_id)
    count = 0
    for sid in sids:
        if except_session_id and sid == except_session_id:
            continue
        if await revoke_session_by_id(user_id, sid):
            count += 1
    return count
