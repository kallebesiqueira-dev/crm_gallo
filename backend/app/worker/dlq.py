"""Dead-letter queue helpers for arq jobs.

When a job exhausts its retry budget (job_try >= max_tries), the
`dlq_wrap` decorator calls `push_to_dlq` before re-raising so the
failure is preserved in Redis for operator inspection.

Redis key: ``arq:dead``  (LPUSH — newest first, capped at _DLQ_MAX_LEN)
Admin UI:  GET /api/admin/dlq
"""

from __future__ import annotations

import functools
import json
import traceback
from datetime import UTC, datetime
from typing import Any

import structlog

from app.redis_client import get_redis

log = structlog.get_logger(__name__)

DLQ_KEY = "arq:dead"
_DLQ_MAX_LEN = 500
_DEFAULT_MAX_TRIES = 5  # mirrors WorkerSettings.max_tries


async def _push(
    ctx: dict,
    function_name: str,
    exc: Exception,
) -> None:
    entry = {
        "job_id": ctx.get("job_id", "unknown"),
        "function": function_name,
        "job_try": ctx.get("job_try", 0),
        "failed_at": datetime.now(UTC).isoformat(),
        "exception_type": type(exc).__name__,
        "exception_msg": str(exc)[:2000],
        "traceback": traceback.format_exc()[:4000],
    }
    log.error(
        "job.dead",
        job_id=entry["job_id"],
        function=function_name,
        job_try=entry["job_try"],
        exception=entry["exception_type"],
    )
    try:
        r = get_redis()
        await r.lpush(DLQ_KEY, json.dumps(entry))
        await r.ltrim(DLQ_KEY, 0, _DLQ_MAX_LEN - 1)
    except Exception:
        log.warning("dlq.push_failed", exc_info=True)


def dlq_wrap(fn: Any, max_tries: int = _DEFAULT_MAX_TRIES) -> Any:
    """Wrap an arq job function to persist terminal failures to DLQ.

    Transparent to arq's retry scheduler: always re-raises the
    exception. Only calls `_push` on the final attempt
    (job_try >= max_tries) so transient failures don't pollute the DLQ.
    """

    @functools.wraps(fn)
    async def wrapper(ctx: dict, *args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(ctx, *args, **kwargs)
        except Exception as exc:
            if ctx.get("job_try", 1) >= max_tries:
                await _push(ctx, fn.__name__, exc)
            raise

    return wrapper
