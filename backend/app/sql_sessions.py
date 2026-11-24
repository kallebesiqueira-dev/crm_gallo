"""Refresh-token sessions stored in Postgres.

Used when `REDIS_URL` is not a redis:// URL (the public demo runs
without a Redis service). The redis-backed path in `redis_client`
stays the default for local/dev and the test suite.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.database import engine

_TOMBSTONE_SECONDS = 300


def _sid(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(
    token: str,
    user_id: str,
    ttl_seconds: int,
    user_agent: str = "",
    ip_address: str = "",
) -> str:
    sid = _sid(token)
    expires = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO auth_refresh_sessions
                  (token_hash, user_id, session_id, created_at, last_seen_at,
                   user_agent, ip_address, expires_at)
                VALUES
                  (:token_hash, :user_id, :session_id, now(), now(),
                   :user_agent, :ip_address, :expires_at)
                """
            ),
            {
                "token_hash": _hash(token),
                "user_id": user_id,
                "session_id": sid,
                "user_agent": user_agent or "",
                "ip_address": ip_address or "",
                "expires_at": expires,
            },
        )
    return sid


async def resolve_refresh_token(token: str) -> str | None:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    """
                    SELECT user_id FROM auth_refresh_sessions
                    WHERE token_hash = :token_hash AND expires_at > now()
                    """
                ),
                {"token_hash": _hash(token)},
            )
        ).first()
    return None if row is None else str(row.user_id)


async def touch_session(token: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE auth_refresh_sessions
                SET last_seen_at = now()
                WHERE token_hash = :token_hash AND expires_at > now()
                """
            ),
            {"token_hash": _hash(token)},
        )


async def rotate_refresh_token(
    old_token: str,
    new_token: str,
    user_id: str,
    ttl_seconds: int,
    user_agent: str = "",
    ip_address: str = "",
) -> str:
    new_sid = _sid(new_token)
    expires = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    tombstone_until = datetime.now(UTC) + timedelta(seconds=_TOMBSTONE_SECONDS)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM auth_refresh_sessions WHERE token_hash = :token_hash"),
            {"token_hash": _hash(old_token)},
        )
        await conn.execute(
            text(
                """
                INSERT INTO auth_refresh_tombstones (token_hash, user_id, expires_at)
                VALUES (:token_hash, :user_id, :expires_at)
                ON CONFLICT (token_hash) DO UPDATE
                  SET user_id = EXCLUDED.user_id, expires_at = EXCLUDED.expires_at
                """
            ),
            {
                "token_hash": _hash(old_token),
                "user_id": user_id,
                "expires_at": tombstone_until,
            },
        )
        await conn.execute(
            text(
                """
                INSERT INTO auth_refresh_sessions
                  (token_hash, user_id, session_id, created_at, last_seen_at,
                   user_agent, ip_address, expires_at)
                VALUES
                  (:token_hash, :user_id, :session_id, now(), now(),
                   :user_agent, :ip_address, :expires_at)
                """
            ),
            {
                "token_hash": _hash(new_token),
                "user_id": user_id,
                "session_id": new_sid,
                "user_agent": user_agent or "",
                "ip_address": ip_address or "",
                "expires_at": expires,
            },
        )
    return new_sid


async def check_rotated_token(token: str) -> str | None:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    """
                    SELECT user_id FROM auth_refresh_tombstones
                    WHERE token_hash = :token_hash AND expires_at > now()
                    """
                ),
                {"token_hash": _hash(token)},
            )
        ).first()
    return None if row is None else str(row.user_id)


async def revoke_refresh_token(token: str) -> bool:
    async with engine.begin() as conn:
        result = await conn.execute(
            text("DELETE FROM auth_refresh_sessions WHERE token_hash = :token_hash"),
            {"token_hash": _hash(token)},
        )
    return bool(result.rowcount)


async def list_user_sessions(user_id: str) -> list[dict]:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM auth_refresh_sessions WHERE user_id = :user_id AND expires_at <= now()"
            ),
            {"user_id": user_id},
        )
        rows = (
            await conn.execute(
                text(
                    """
                    SELECT session_id, created_at, last_seen_at, user_agent, ip_address
                    FROM auth_refresh_sessions
                    WHERE user_id = :user_id AND expires_at > now()
                    ORDER BY created_at DESC
                    """
                ),
                {"user_id": user_id},
            )
        ).all()
    return [
        {
            "id": row.session_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
            "user_agent": row.user_agent or "",
            "ip_address": row.ip_address or "",
        }
        for row in rows
    ]


async def revoke_session_by_id(user_id: str, session_id: str) -> bool:
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                DELETE FROM auth_refresh_sessions
                WHERE user_id = :user_id AND session_id = :session_id
                """
            ),
            {"user_id": user_id, "session_id": session_id},
        )
    return bool(result.rowcount)


async def revoke_user_sessions_except(user_id: str, except_session_id: str | None) -> int:
    async with engine.begin() as conn:
        if except_session_id:
            result = await conn.execute(
                text(
                    """
                    DELETE FROM auth_refresh_sessions
                    WHERE user_id = :user_id AND session_id <> :session_id
                    """
                ),
                {"user_id": user_id, "session_id": except_session_id},
            )
        else:
            result = await conn.execute(
                text("DELETE FROM auth_refresh_sessions WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
    return int(result.rowcount or 0)
