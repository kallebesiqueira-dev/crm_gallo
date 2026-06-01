"""Helpers HTTP handlers use to enqueue background work.

Two responsibilities:
  1. Open / cache an `ArqRedis` pool (separate from `app.redis_client`
     because Arq wants its own pool shape).
  2. Wrap `enqueue_job` with idempotency: a `SETNX` on
     `job:dedupe:{key}` with a configurable TTL drops the second
     enqueue if the first hasn't expired yet. Defends against
     double-clicks and React-strict-mode double effects.

Returns the Arq `Job` (with `.job_id`) on success or `None` when
the de-dupe key was already present — caller surfaces "already
queued" to the SPA rather than queueing twice.
"""
from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis
from arq.jobs import Job

from app.redis_client import get_redis
from app.worker.settings import WorkerSettings


_pool: ArqRedis | None = None


async def get_arq() -> ArqRedis:
    """Lazy singleton — Arq's pool is event-loop-bound like asyncpg
    so we open on the first request and reuse."""
    global _pool
    if _pool is None:
        _pool = await create_pool(WorkerSettings.redis_settings)
    return _pool


async def enqueue(
    function_name: str,
    *args: Any,
    dedupe_key: str | None = None,
    dedupe_ttl_seconds: int = 3600,
    **kwargs: Any,
) -> Job | None:
    """Push a job onto the queue.

    `dedupe_key` is optional but recommended for user-triggered
    actions (score this lead, send this email). When set, we
    `SET NX EX` on `job:dedupe:{key}` first — if the key already
    exists, return None and don't enqueue. TTL window should be
    "how long does the job take + buffer"; for a 30s LLM call,
    1 hour is conservative enough that retries within the window
    are intentional re-tries (manual re-click), not noise.
    """
    if dedupe_key is not None:
        r = get_redis()
        # `nx=True` makes SET atomic: returns True if the key was
        # set (no previous value), None if it already existed.
        ok = await r.set(f"job:dedupe:{dedupe_key}", "1", nx=True, ex=dedupe_ttl_seconds)
        if not ok:
            return None
    pool = await get_arq()
    return await pool.enqueue_job(function_name, *args, **kwargs)
