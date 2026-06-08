"""Arq `WorkerSettings` — picked up by the CLI entrypoint:
    `arq app.worker.settings.WorkerSettings`

`functions` lists every coroutine arq will dispatch by name. Add new
job modules' callables here when they're imported into `jobs.py`.

`on_startup` / `on_shutdown` keep a long-lived async engine in
`ctx` so jobs don't re-open a connection per call. asyncpg + Arq's
loop are the same loop so the engine is reusable without the
loop-binding gymnastics that the test harness needs.

Retries:
  * `max_tries=5` with exponential backoff — covers transient LLM
    / S3 / SMTP blips.
  * `keep_result_forever=False`: result rows TTL after 1 hour, so
    `arq.JobStatus` lookups by job id work for the typical "did
    the click take?" follow-up without bloating Redis.

DLQ: arq has no built-in dead-letter queue. After max_tries the
exception is logged and the job is dropped. A real DLQ would be
a Redis list `arq:queue:dead` we LPUSH to from a fail callback;
tracked as a P2 follow-up.
"""

from __future__ import annotations

from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import register_org_guc
from app.worker.jobs import (
    deliver_webhook,
    drain_outbox,
    generate_contract_pdf,
    generate_deal_pdf,
    generate_quote_pdf,
    process_import,
    scan_stale_leads,
    score_lead,
    send_email,
)


def _redis_settings_from_url() -> RedisSettings:
    """Arq wants its own RedisSettings shape; derive from our
    `REDIS_URL` env so there's one source of truth. URL parsing
    is intentionally minimal — we only run against the redis://
    scheme in dev and rediss:// in prod, both supported here."""
    url = get_settings().redis_url
    # `redis://[[username]:password@]host[:port][/db]`
    no_scheme = url.replace("rediss://", "").replace("redis://", "")
    ssl = url.startswith("rediss://")
    auth_host, _, db = no_scheme.partition("/")
    password: str | None = None
    if "@" in auth_host:
        auth, _, host_port = auth_host.partition("@")
        # Managed Redis (e.g. Railway) uses `default:<password>`; dev may use
        # `:<password>` or no auth at all. Redis AUTH with the password alone
        # authenticates the default user, so we only need the password here.
        password = (auth.split(":", 1)[1] if ":" in auth else auth) or None
    else:
        host_port = auth_host
    host, _, port = host_port.partition(":")
    return RedisSettings(
        host=host or "redis",
        port=int(port or 6379),
        database=int(db or 0),
        password=password,
        ssl=ssl,
    )


async def _startup(ctx: dict) -> None:
    """Construct the per-worker async engine + session factory. arq
    re-uses one event loop for the worker's lifetime, so this is
    safe (no fresh-pool-per-job overhead)."""
    settings = get_settings()
    engine = create_async_engine(settings.runtime_database_url, echo=False, future=True)
    # Transaction-scoped RLS GUC: jobs call `set_current_org_id(...)` and
    # this re-applies `app.current_org_id` (SET LOCAL) at every txn begin,
    # so a connection-scoped GUC can't linger on a pooled connection and
    # leak one job's tenant into a later job that reuses it.
    register_org_guc(engine)
    ctx["engine"] = engine
    ctx["SessionLocal"] = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def _shutdown(ctx: dict) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    """Arq picks `functions`, `redis_settings`, `on_startup`,
    `on_shutdown`, `max_tries`, etc. off the class directly."""

    functions: ClassVar = [
        score_lead,
        deliver_webhook,
        send_email,
        generate_deal_pdf,
        generate_quote_pdf,
        generate_contract_pdf,
        process_import,
        scan_stale_leads,
    ]
    # Cron set: fires every 5 seconds. Outbox publishers commit
    # synchronously in the request path, so events appear under 1
    # request-latency-budget; the drain just needs to be fast enough
    # to feel real-time without hammering Redis. 5s is the sweet
    # spot — at 1s the worker churns on empty queries; at 30s a
    # webhook subscriber would visibly lag a user clicking the
    # button.
    cron_jobs: ClassVar = [
        cron(
            drain_outbox,
            name="drain_outbox",
            second={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
            run_at_startup=True,
            unique=True,  # never two overlapping drains on the same node
            max_tries=1,  # the drain itself handles per-row retries
        ),
        # Time-based automations (lead_stale). Hourly is plenty — staleness
        # is a days-scale threshold and the per-(lead,day) idempotency key
        # makes a re-run within the day a cheap no-op. unique so two nodes
        # don't double-scan; max_tries=1 because the scan isolates per-rule
        # errors itself (see app.automations._run_rule).
        cron(
            scan_stale_leads,
            name="scan_stale_leads",
            minute={0},
            run_at_startup=False,
            unique=True,
            max_tries=1,
        ),
    ]
    redis_settings = _redis_settings_from_url()
    on_startup = _startup
    on_shutdown = _shutdown
    max_tries = 5
    keep_result = 3600  # seconds — `arq.JobResult` lookup window
    job_timeout = 60  # seconds — kill stuck jobs (LLM cold-start)
