"""Public send API. Handlers call `send(...)`; it enqueues an arq
`send_email` job so a slow provider never blocks the request path.

The job (in `app/worker/jobs.py`) renders + delivers and retries on
failure. We enqueue the raw (template, locale, ctx) — rendering lives
in exactly one place (the worker) and the Redis payload stays small
and JSON-serializable.
"""

from __future__ import annotations

from typing import Any

from app.logging_setup import get_logger

log = get_logger(__name__)


async def send(
    *,
    to: str,
    template: str,
    locale: str | None,
    ctx: dict[str, Any],
    dedupe_key: str | None = None,
) -> None:
    """Enqueue a transactional email.

    Best-effort by contract: callers (invite create, password reset)
    wrap this so a Redis/enqueue hiccup never 500s a user action — the
    URL is also logged at the call site as a recovery fallback. The
    worker owns delivery retries once the job is on the queue.
    """
    # Deferred import: `app.worker.queue` pulls in the worker settings
    # → jobs → back into this package. Importing it lazily here keeps
    # `app.email` import-safe from inside the worker.
    from app.worker.queue import enqueue

    await enqueue(
        "send_email",
        to,
        template,
        locale,
        ctx,
        dedupe_key=dedupe_key,
    )
    log.info("email.enqueued", to=to, template=template, locale=locale)
