"""Job coroutines. Imported by `WorkerSettings.functions` so arq
dispatches by name.

Each job function:
  * Takes `ctx` first (arq convention) — `ctx['SessionLocal']` is
    the async session factory injected by `_startup`.
  * Sets the RLS GUC (`app.current_org_id`) inside its own session
    so the policies don't filter the row out — the worker runs as
    `crm_app` (NOSUPERUSER NOBYPASSRLS) same as the API, so this
    is mandatory.
  * Touches the DB inside a single transaction and `commit()`s
    explicitly. Errors propagate so arq's retry kicks in.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import structlog
from arq import Retry
from sqlalchemy import delete, select, text

from app.activities import ENTITY_LEAD, ActivityType, record_activity
from app.audit import record_audit
from app.database import set_current_org_id
from app.events import OUTBOX_MAX_ATTEMPTS
from app.events_dispatcher import EventContext, dispatch_event
from app.models import (
    Contract,
    Conversation,
    Customer,
    Deal,
    ImportEntityType,
    ImportJob,
    ImportMode,
    ImportStatus,
    Lead,
    Message,
    MessageStatus,
    Organization,
    OrgInvite,
    Quote,
    User,
    WebhookDelivery,
    WebhookEndpoint,
    WhatsAppAccount,
    WhatsAppAccountStatus,
)
from app.services.ai_scoring import score_lead as score_lead_via_llm
from app.webhook_sign import SIGNATURE_HEADER, sign_payload

log = structlog.get_logger(__name__)

# Per-sweep claim limit. Bigger = more throughput per cron tick;
# smaller = lower lock contention if we ever scale to N workers.
# 100 covers the steady-state burst from a typical lead-import or
# pipeline-shuffle without holding row locks for more than a second.
_OUTBOX_BATCH_SIZE = 100


# Webhook delivery config. Tunables, not contract — adjust as we
# learn what receivers actually do.
_WEBHOOK_HTTP_TIMEOUT_S = 10.0
_WEBHOOK_MAX_TRIES = 8  # 1 + 7 retries; ~17min wall time at the cap
_WEBHOOK_AUTO_PAUSE_THRESHOLD = 10
# Truncate received bodies so a misbehaving receiver returning a
# 1 MB HTML error page doesn't bloat the deliveries table.
_WEBHOOK_RESPONSE_EXCERPT_BYTES = 2048

# Cap on per-row errors persisted to `ImportJob.error_report`. A 50k-row
# file that's malformed on every line would otherwise write a multi-MB
# JSONB blob; 1000 sampled errors is plenty for a user to see the shape
# of what's wrong and fix the source file. `error_count` still reflects
# the TRUE total — only the detailed report is sampled.
_IMPORT_ERROR_REPORT_CAP = 1000

# Which ORM model each importable entity writes to.
_IMPORT_MODELS = {
    ImportEntityType.lead: Lead,
    ImportEntityType.customer: Customer,
}


async def score_lead(ctx: dict, lead_id: str, organization_id: str) -> dict:
    """Re-score one lead in the background.

    Mirrors the sync `POST /api/leads/{id}/score` endpoint but with
    no HTTP user attached — activity / audit get `actor=None`
    (system event). Returns a small status dict that arq stores in
    Redis (queryable via `JobResult` for "did my click land?"
    polling).

    Idempotency note: arq retries this job on exception (max_tries=5);
    so the LLM call MUST be safe to repeat. `score_lead_via_llm`
    is read-only against the lead; the only mutation here is the
    final UPDATE on the lead row. Repeated runs just overwrite the
    same fields with a fresh score — acceptable.
    """
    SessionLocal = ctx["SessionLocal"]
    lead_uuid = uuid.UUID(lead_id)
    org_uuid = uuid.UUID(organization_id)

    async with SessionLocal() as db:
        # RLS GUC — the runtime engine doesn't bypass RLS, so a bare
        # SELECT against tenant tables returns nothing without a tenant
        # set. Stash it on the task ContextVar; the worker engine's begin
        # event applies it (SET LOCAL) to each transaction, so it can't
        # linger on a pooled connection and leak into the next job.
        set_current_org_id(org_uuid)
        result = await db.execute(
            select(Lead).where(Lead.id == lead_uuid, Lead.organization_id == org_uuid)
        )
        lead = result.scalar_one_or_none()
        if lead is None or lead.deleted_at is not None:
            # Lead disappeared between enqueue and dispatch (deleted,
            # cross-org leak attempt, or the org_id is wrong). Don't
            # retry — there's nothing to score.
            log.warning("score_lead.lead_missing", lead_id=lead_id, organization_id=organization_id)
            return {"status": "missing"}

        scoring = await score_lead_via_llm(lead)
        lead.ai_score = scoring["score"]
        lead.ai_priority = scoring["priority"]
        lead.ai_next_action = scoring["next_action"]
        lead.ai_conversion_probability = scoring["conversion_probability"]
        lead.ai_risk_analysis = scoring["risk_analysis"]
        lead.ai_scored_at = scoring.get("scored_at", datetime.now(UTC))

        await record_activity(
            db,
            entity_type=ENTITY_LEAD,
            entity_id=lead.id,
            activity_type=ActivityType.ai_scored,
            organization_id=org_uuid,
            actor=None,  # system event
            metadata={
                "score": lead.ai_score,
                "priority": lead.ai_priority,
                "via": "worker",
            },
        )
        await record_audit(
            db,
            actor=None,
            action="lead.score",
            entity_type="lead",
            entity_id=lead.id,
            organization_id=org_uuid,
            metadata={"score": lead.ai_score, "via": "worker"},
        )
        await db.commit()

    log.info(
        "score_lead.done",
        lead_id=lead_id,
        organization_id=organization_id,
        score=scoring["score"],
    )
    return {"status": "scored", "score": scoring["score"]}


async def drain_outbox(ctx: dict) -> dict:
    """Periodic outbox sweep — claims a batch of unprocessed events
    with `FOR UPDATE SKIP LOCKED`, dispatches each through the
    in-process subscriber registry, and marks success/failure.

    Why `FOR UPDATE SKIP LOCKED`: two workers (or a worker + an
    accidentally-triggered one-shot) racing on the same outbox row
    would otherwise either deadlock (FOR UPDATE) or double-fire
    subscribers (no lock). SKIP LOCKED makes each row dispatch
    by exactly one worker per sweep.

    Backoff: after a failure, the row's `occurred_at` is NOT
    rewritten, but the dispatcher only claims rows where
    `occurred_at + (2^attempt_count seconds) <= now()`. So attempt 1
    waits 2s, attempt 5 waits 32s, attempt 10 waits ~17min.

    DLQ: rows with `attempt_count >= OUTBOX_MAX_ATTEMPTS` are
    excluded from future claims (they stay `processed_at IS NULL`
    with `last_error` populated). Ops surface via the admin
    `/api/outbox?status=failed` endpoint.

    Outbox is NOT RLS'd, so no GUC needed. Worker drains across
    every org in one pass.
    """
    SessionLocal = ctx["SessionLocal"]
    claimed = 0
    succeeded = 0
    failed = 0

    async with SessionLocal() as db:
        # Single SQL claim: SKIP LOCKED + LIMIT for back-pressure +
        # exponential backoff via `occurred_at + interval`. The
        # POW expression caps attempts at OUTBOX_MAX_ATTEMPTS so
        # the LEAST() clause never returns NULL.
        claim_sql = text(
            """
            SELECT id, event_type, organization_id, payload, occurred_at, attempt_count
              FROM outbox_events
             WHERE processed_at IS NULL
               AND attempt_count < :max_attempts
               AND occurred_at + (POW(2, attempt_count) * INTERVAL '1 second') <= now()
             ORDER BY occurred_at
             LIMIT :batch
             FOR UPDATE SKIP LOCKED
            """
        )
        result = await db.execute(
            claim_sql,
            {"max_attempts": OUTBOX_MAX_ATTEMPTS, "batch": _OUTBOX_BATCH_SIZE},
        )
        rows = result.mappings().all()
        claimed = len(rows)

        for row in rows:
            event_id = row["id"]
            try:
                payload_obj = json.loads(row["payload"]) if row["payload"] else None
            except json.JSONDecodeError as e:
                # Bad JSON in the payload — flag this row as failed
                # so it doesn't loop, and move on.
                await db.execute(
                    text(
                        "UPDATE outbox_events SET attempt_count = :ac, "
                        "last_error = :err WHERE id = :id"
                    ),
                    {
                        "id": event_id,
                        "ac": OUTBOX_MAX_ATTEMPTS,
                        "err": f"invalid payload JSON: {e}",
                    },
                )
                failed += 1
                continue

            event_ctx = EventContext(
                event_id=event_id,
                event_type=row["event_type"],
                organization_id=row["organization_id"],
                payload=payload_obj,
                occurred_at=row["occurred_at"],
            )
            try:
                await dispatch_event(event_ctx)
            except Exception as e:
                await db.execute(
                    text(
                        "UPDATE outbox_events SET attempt_count = attempt_count + 1, "
                        "last_error = :err WHERE id = :id"
                    ),
                    {"id": event_id, "err": str(e)[:2000]},
                )
                log.warning(
                    "outbox.dispatch_failed",
                    event_id=str(event_id),
                    event_type=row["event_type"],
                    attempt=row["attempt_count"] + 1,
                    error=str(e),
                )
                failed += 1
                continue

            await db.execute(
                text(
                    "UPDATE outbox_events SET processed_at = now(), "
                    "last_error = NULL WHERE id = :id"
                ),
                {"id": event_id},
            )
            succeeded += 1

        await db.commit()

    if claimed:
        log.info(
            "outbox.drained",
            claimed=claimed,
            succeeded=succeeded,
            failed=failed,
        )
    return {"claimed": claimed, "succeeded": succeeded, "failed": failed}


async def deliver_webhook(
    ctx: dict,
    endpoint_id: str,
    event_id: str,
    event_type: str,
    payload: dict | None,
    organization_id: str | None,
) -> dict:
    """Deliver one event to one webhook endpoint. Re-enqueued by the
    fanout subscriber once per (endpoint, event) pair so a slow
    receiver only delays its own deliveries, not the outbox drain
    or other endpoints.

    Retry model (arq):
      * `_WEBHOOK_MAX_TRIES` total attempts (1 initial + 7 retries).
      * Backoff via `arq.Retry(defer_seconds=2^attempt)` — 2s, 4s,
        8s, 16s, 32s, 64s, 128s, 256s wait between tries.
      * Each attempt writes a `WebhookDelivery` row tracking the
        outcome — admin can see "attempt 3 returned 502 after 8s".

    Endpoint health:
      * `consecutive_failures` is bumped on every non-2xx + reset on
        success. When it reaches `_WEBHOOK_AUTO_PAUSE_THRESHOLD`,
        `paused_at = now()` and no further fanouts target this
        endpoint until an admin unpauses (which also zeros the
        counter — see `PATCH /api/webhooks/{id}`).

    Idempotency: receivers MUST dedupe by `event_id` from the body.
    Two arq retries of the same job carry the SAME event_id, so a
    receiver that successfully processed attempt 1 and crashed
    before ACK'ing should not double-handle on attempt 2.
    """
    SessionLocal = ctx["SessionLocal"]
    ep_uuid = uuid.UUID(endpoint_id)
    ev_uuid = uuid.UUID(event_id)
    attempt = ctx.get("job_try", 1)

    async with SessionLocal() as db:
        result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == ep_uuid))
        ep = result.scalar_one_or_none()
        if ep is None or ep.paused_at is not None:
            # Endpoint deleted or paused between enqueue and dispatch —
            # drop silently. No retry, no row (there's nothing to
            # tell ops about an action they intentionally took).
            return {"status": "skipped"}

        body = json.dumps(
            {
                "event_id": event_id,
                "event_type": event_type,
                "organization_id": organization_id,
                "payload": payload or {},
            },
            sort_keys=True,  # stable bytes for signature recomputation
        ).encode("utf-8")
        signature = sign_payload(ep.secret, body)

        delivery = WebhookDelivery(
            endpoint_id=ep.id,
            event_id=ev_uuid,
            event_type=event_type,
            attempt=attempt,
        )
        db.add(delivery)
        await db.flush()

        started = time.perf_counter()
        response_code: int | None = None
        excerpt: str | None = None
        err: str | None = None
        succeeded = False
        try:
            async with httpx.AsyncClient(timeout=_WEBHOOK_HTTP_TIMEOUT_S) as client:
                r = await client.post(
                    ep.url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "CRM-Gallo-Webhook/1.0",
                        SIGNATURE_HEADER: signature,
                        # Receivers can dedupe by event_id alone, but
                        # this header makes the relationship explicit
                        # and survives JSON re-encoding.
                        "X-CRM-Event-Id": event_id,
                        "X-CRM-Event-Type": event_type,
                    },
                )
            response_code = r.status_code
            excerpt = r.text[:_WEBHOOK_RESPONSE_EXCERPT_BYTES] or None
            # 2xx = success. Receivers signal "got it, will dedupe" via
            # any 2xx — we don't require a specific body shape.
            succeeded = 200 <= r.status_code < 300
            if not succeeded:
                err = f"HTTP {r.status_code}"
        except httpx.HTTPError as e:
            err = f"{type(e).__name__}: {e}"

        latency_ms = int((time.perf_counter() - started) * 1000)
        delivery.latency_ms = latency_ms
        delivery.response_code = response_code
        delivery.response_body_excerpt = excerpt
        delivery.error = err
        delivery.finished_at = datetime.now(UTC)

        if succeeded:
            delivery.status = "success"
            ep.consecutive_failures = 0
            ep.last_success_at = delivery.finished_at
            await db.commit()
            log.info(
                "webhook.delivered",
                endpoint_id=endpoint_id,
                event_id=event_id,
                event_type=event_type,
                attempt=attempt,
                latency_ms=latency_ms,
                response_code=response_code,
            )
            return {"status": "success", "latency_ms": latency_ms}

        # Failure path
        delivery.status = "failed"
        ep.consecutive_failures = ep.consecutive_failures + 1
        ep.last_failure_at = delivery.finished_at
        auto_pause = ep.consecutive_failures >= _WEBHOOK_AUTO_PAUSE_THRESHOLD
        if auto_pause:
            ep.paused_at = delivery.finished_at
        await db.commit()

        log.warning(
            "webhook.failed",
            endpoint_id=endpoint_id,
            event_id=event_id,
            event_type=event_type,
            attempt=attempt,
            response_code=response_code,
            error=err,
            consecutive_failures=ep.consecutive_failures,
            auto_paused=auto_pause,
        )

        if auto_pause:
            # Don't burn the remaining retry budget on an endpoint we
            # just auto-paused; let arq drop the job here.
            return {"status": "paused"}

        if attempt < _WEBHOOK_MAX_TRIES:
            # Exponential backoff. `Retry` is arq's signal to re-queue
            # this job with `defer_seconds` wait. Caps at ~4 minutes
            # so a 7-retry sequence finishes in <17min.
            defer = min(2**attempt, 240)
            raise Retry(defer=defer)

        # Out of retries — leave the delivery row as the audit trail
        # and let arq drop the job.
        return {"status": "exhausted"}


async def send_email(
    ctx: dict,
    to: str,
    template: str,
    locale: str | None,
    email_ctx: dict,
) -> dict:
    """Render + deliver one transactional email (ADR-017).

    Enqueued by `app.email.send()`. Rendering happens here (one place)
    from the small JSON payload pushed onto Redis. Delivery goes
    through the configured provider (console / resend / smtp); a hard
    failure raises so arq retries with backoff (`max_tries=5`).

    No DB session is touched — this job is pure render + network. It
    therefore needs no RLS GUC.
    """
    # Imported here (not module top) so the jobs module stays cheap to
    # import and there's no email↔worker import cycle at load time.
    from app.email import get_provider, render

    rendered = render(template, locale, email_ctx)
    provider = get_provider()
    await provider.send(to=to, message=rendered)

    log.info(
        "email.sent",
        to=to,
        template=template,
        locale=locale,
        provider=provider.name,
        subject=rendered.subject,
    )
    return {"status": "sent", "provider": provider.name}


async def generate_deal_pdf(ctx: dict, deal_id: str, organization_id: str) -> dict:
    """Render a deal-summary PDF and attach it to the deal (ADR-016).

    Enqueued by `POST /api/deals/{id}/pdf`. Reads the deal (+ customer,
    owner, org names), renders the `deal_summary` template to PDF via
    WeasyPrint, and stores it as a `FileAttachment` — so it surfaces in
    the deal's existing attachment list and downloads through the same
    presigned-URL path as uploads.

    RLS: the worker runs as `crm_app` (NOBYPASSRLS), so the GUC must be
    set before reading `deals` (an RLS'd tenant table) or the SELECT
    returns nothing. `file_attachments` is not yet RLS'd (TD-42) so the
    INSERT itself doesn't depend on the GUC, but we set it anyway.

    Idempotency: arq retries on exception (`max_tries=5`). A retry
    re-renders + re-uploads, producing a NEW attachment row (fresh
    UUID/key). Acceptable for v1 — a regenerate is user-meaningful and
    the dedupe window on the enqueue side collapses accidental
    double-clicks. The lazy WeasyPrint import lives in `app.pdf.render`.
    """
    from app.pdf import TEMPLATE_DEAL_SUMMARY, render_pdf, store_pdf_attachment

    SessionLocal = ctx["SessionLocal"]
    deal_uuid = uuid.UUID(deal_id)
    org_uuid = uuid.UUID(organization_id)

    # RLS tenant scope via the task ContextVar; the worker engine's begin
    # event applies it (SET LOCAL) to every transaction this job opens.
    # See app.database.register_org_guc.
    set_current_org_id(org_uuid)

    # Phase 1 — read into a plain context dict, then RELEASE the connection
    # before the render (TD-43: don't pin a pooled connection across the
    # ~tens-of-seconds WeasyPrint call).
    async with SessionLocal() as db:
        deal = (
            await db.execute(
                select(Deal).where(Deal.id == deal_uuid, Deal.organization_id == org_uuid)
            )
        ).scalar_one_or_none()
        if deal is None or deal.deleted_at is not None:
            # Deal vanished between enqueue and dispatch — nothing to
            # render. Don't retry.
            log.warning(
                "generate_deal_pdf.deal_missing",
                deal_id=deal_id,
                organization_id=organization_id,
            )
            return {"status": "missing"}

        org_name = (
            await db.execute(select(Organization.name).where(Organization.id == org_uuid))
        ).scalar_one_or_none() or "CRM Gallo"

        customer_name = None
        if deal.customer_id is not None:
            cust = (
                await db.execute(
                    select(Customer.first_name, Customer.last_name, Customer.company).where(
                        Customer.id == deal.customer_id
                    )
                )
            ).first()
            if cust is not None:
                full = f"{cust.first_name} {cust.last_name}".strip()
                customer_name = f"{full} ({cust.company})" if cust.company else full

        owner_name = None
        if deal.owner_id is not None:
            owner_name = (
                await db.execute(select(User.full_name).where(User.id == deal.owner_id))
            ).scalar_one_or_none()

        deal_pk = deal.id
        filename = f"deal-{deal.title[:40].strip()}.pdf".replace("/", "-")
        context = {
            "org_name": org_name,
            "deal_title": deal.title,
            "value": deal.value,
            "currency": deal.currency.value,
            "stage": deal.stage.value,
            "customer_name": customer_name,
            "owner_name": owner_name,
            "expected_close_date": (
                deal.expected_close_date.isoformat() if deal.expected_close_date else None
            ),
            "created_at": deal.created_at.strftime("%Y-%m-%d"),
            "description": deal.notes,
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        }

    # Phase 2 — render with NO DB connection held. WeasyPrint's write_pdf()
    # is synchronous and CPU-bound (~seconds, tens of seconds on a cold
    # font cache); running it inline blocks arq's event loop — which
    # starves the Redis heartbeat and the drain_outbox cron, and can
    # surface as spurious CancelledError on the Redis connection
    # mid-render. Offload to a thread.
    pdf_bytes = await asyncio.to_thread(render_pdf, TEMPLATE_DEAL_SUMMARY, context)

    # Phase 3 — store + audit in a fresh short transaction (GUC re-applied
    # by the begin event from the still-set ContextVar).
    async with SessionLocal() as db:
        att = await store_pdf_attachment(
            db,
            organization_id=org_uuid,
            entity_type="deal",
            entity_id=deal_pk,
            filename=filename,
            pdf_bytes=pdf_bytes,
        )
        await record_audit(
            db,
            actor=None,
            action="deal.pdf_generated",
            entity_type="deal",
            entity_id=deal_pk,
            organization_id=org_uuid,
            metadata={"attachment_id": str(att.id), "size_bytes": att.size_bytes, "via": "worker"},
        )
        await db.commit()
        att_id = str(att.id)
        att_size = att.size_bytes

    log.info(
        "generate_deal_pdf.done",
        deal_id=deal_id,
        organization_id=organization_id,
        attachment_id=att_id,
        size_bytes=att_size,
    )
    return {"status": "generated", "attachment_id": att_id, "size_bytes": att_size}


async def generate_quote_pdf(ctx: dict, quote_id: str, organization_id: str) -> dict:
    """Render a quote PDF and attach it to the quote (ADR-016).

    Enqueued by `POST /api/quotes/{id}/pdf`. Mirrors `generate_deal_pdf`:
    set the RLS GUC (worker is `crm_app`, NOBYPASSRLS), read the quote +
    its line items + the org/customer/owner names, render the `quote`
    template via WeasyPrint off the event loop, and store the bytes as a
    `FileAttachment` (entity_type="quote") so it surfaces in the quote's
    attachment list and downloads via the existing presigned-URL path.

    The line items are eager-loaded (`selectinload`) because the render
    happens after the session work — a lazy load there would fail under
    async. Same retry/idempotency note as the deal job applies.
    """
    from sqlalchemy.orm import selectinload

    from app.pdf import TEMPLATE_QUOTE, render_pdf, store_pdf_attachment

    SessionLocal = ctx["SessionLocal"]
    quote_uuid = uuid.UUID(quote_id)
    org_uuid = uuid.UUID(organization_id)

    # RLS tenant scope via the task ContextVar; the worker engine's begin
    # event applies it (SET LOCAL) to EVERY transaction this job opens —
    # both the read below and the write after the render. See
    # app.database.register_org_guc.
    set_current_org_id(org_uuid)

    # Phase 1 — read everything into a plain context dict, then RELEASE the
    # connection. The render (Phase 2) is ~tens of seconds; holding a
    # pooled connection across it would starve the small worker pool and
    # block drain_outbox / other jobs (TD-43).
    async with SessionLocal() as db:
        quote = (
            await db.execute(
                select(Quote)
                .where(Quote.id == quote_uuid, Quote.organization_id == org_uuid)
                .options(selectinload(Quote.line_items))
            )
        ).scalar_one_or_none()
        if quote is None or quote.deleted_at is not None:
            log.warning(
                "generate_quote_pdf.quote_missing",
                quote_id=quote_id,
                organization_id=organization_id,
            )
            return {"status": "missing"}

        org_name = (
            await db.execute(select(Organization.name).where(Organization.id == org_uuid))
        ).scalar_one_or_none() or "CRM Gallo"

        customer_name = None
        if quote.customer_id is not None:
            cust = (
                await db.execute(
                    select(Customer.first_name, Customer.last_name, Customer.company).where(
                        Customer.id == quote.customer_id
                    )
                )
            ).first()
            if cust is not None:
                full = f"{cust.first_name} {cust.last_name}".strip()
                customer_name = f"{full} ({cust.company})" if cust.company else full

        owner_name = None
        if quote.owner_id is not None:
            owner_name = (
                await db.execute(select(User.full_name).where(User.id == quote.owner_id))
            ).scalar_one_or_none()

        quote_pk = quote.id
        filename = f"quote-{quote.number}-v{quote.version}.pdf".replace("/", "-")
        context = {
            "org_name": org_name,
            "number": quote.number,
            "version": quote.version,
            "status": quote.status.value,
            "title": quote.title,
            "currency": quote.currency.value,
            "customer_name": customer_name,
            "owner_name": owner_name,
            "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
            "created_at": quote.created_at.strftime("%Y-%m-%d"),
            "notes": quote.notes,
            "subtotal": quote.subtotal,
            "tax_rate": quote.tax_rate,
            "tax_amount": quote.tax_amount,
            "total": quote.total,
            "line_items": [
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "line_total": item.line_total,
                }
                for item in quote.line_items
            ],
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        }

    # Phase 2 — render with NO DB connection held. Synchronous CPU-bound
    # WeasyPrint call is offloaded so it doesn't block arq's event loop
    # (see generate_deal_pdf for the full rationale).
    pdf_bytes = await asyncio.to_thread(render_pdf, TEMPLATE_QUOTE, context)

    # Phase 3 — store + audit in a fresh short transaction (GUC re-applied
    # by the begin event from the still-set ContextVar).
    async with SessionLocal() as db:
        att = await store_pdf_attachment(
            db,
            organization_id=org_uuid,
            entity_type="quote",
            entity_id=quote_pk,
            filename=filename,
            pdf_bytes=pdf_bytes,
        )
        await record_audit(
            db,
            actor=None,
            action="quote.pdf_generated",
            entity_type="quote",
            entity_id=quote_pk,
            organization_id=org_uuid,
            metadata={"attachment_id": str(att.id), "size_bytes": att.size_bytes, "via": "worker"},
        )
        await db.commit()
        att_id = str(att.id)
        att_size = att.size_bytes

    log.info(
        "generate_quote_pdf.done",
        quote_id=quote_id,
        organization_id=organization_id,
        attachment_id=att_id,
        size_bytes=att_size,
    )
    return {"status": "generated", "attachment_id": att_id, "size_bytes": att_size}


async def generate_contract_pdf(ctx: dict, contract_id: str, organization_id: str) -> dict:
    """Render a contract PDF and attach it to the contract (ADR-016).

    Enqueued by `POST /api/contracts/{id}/pdf`. Mirrors
    `generate_quote_pdf` but the contract has no line items — it renders a
    single agreed `value` plus the term / renewal / free-text body. Set
    the RLS GUC (worker is `crm_app`, NOBYPASSRLS), read the contract +
    org/customer/owner names, render the `contract` template via
    WeasyPrint off the event loop, and store the bytes as a
    `FileAttachment` (entity_type="contract") so it surfaces in the
    contract's attachment list and downloads via the existing
    presigned-URL path. Same retry/idempotency note as the quote job.
    """
    from app.pdf import TEMPLATE_CONTRACT, render_pdf, store_pdf_attachment

    SessionLocal = ctx["SessionLocal"]
    contract_uuid = uuid.UUID(contract_id)
    org_uuid = uuid.UUID(organization_id)

    set_current_org_id(org_uuid)

    # Phase 1 — read into a plain context dict, then RELEASE the connection
    # before the ~tens-of-seconds WeasyPrint render (TD-43).
    async with SessionLocal() as db:
        contract = (
            await db.execute(
                select(Contract).where(
                    Contract.id == contract_uuid, Contract.organization_id == org_uuid
                )
            )
        ).scalar_one_or_none()
        if contract is None or contract.deleted_at is not None:
            log.warning(
                "generate_contract_pdf.contract_missing",
                contract_id=contract_id,
                organization_id=organization_id,
            )
            return {"status": "missing"}

        org_name = (
            await db.execute(select(Organization.name).where(Organization.id == org_uuid))
        ).scalar_one_or_none() or "CRM Gallo"

        customer_name = None
        if contract.customer_id is not None:
            cust = (
                await db.execute(
                    select(Customer.first_name, Customer.last_name, Customer.company).where(
                        Customer.id == contract.customer_id
                    )
                )
            ).first()
            if cust is not None:
                full = f"{cust.first_name} {cust.last_name}".strip()
                customer_name = f"{full} ({cust.company})" if cust.company else full

        owner_name = None
        if contract.owner_id is not None:
            owner_name = (
                await db.execute(select(User.full_name).where(User.id == contract.owner_id))
            ).scalar_one_or_none()

        contract_pk = contract.id
        filename = f"contract-{contract.number}-v{contract.version}.pdf".replace("/", "-")
        context = {
            "org_name": org_name,
            "number": contract.number,
            "version": contract.version,
            "status": contract.status.value,
            "title": contract.title,
            "currency": contract.currency.value,
            "customer_name": customer_name,
            "owner_name": owner_name,
            "value": contract.value,
            "effective_date": (
                contract.effective_date.isoformat() if contract.effective_date else None
            ),
            "end_date": contract.end_date.isoformat() if contract.end_date else None,
            "auto_renew": contract.auto_renew,
            "renewal_term_months": contract.renewal_term_months,
            "created_at": contract.created_at.strftime("%Y-%m-%d"),
            "body": contract.body,
            "notes": contract.notes,
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        }

    # Phase 2 — render with NO DB connection held (see generate_deal_pdf).
    pdf_bytes = await asyncio.to_thread(render_pdf, TEMPLATE_CONTRACT, context)

    # Phase 3 — store + audit in a fresh short transaction.
    async with SessionLocal() as db:
        att = await store_pdf_attachment(
            db,
            organization_id=org_uuid,
            entity_type="contract",
            entity_id=contract_pk,
            filename=filename,
            pdf_bytes=pdf_bytes,
        )
        await record_audit(
            db,
            actor=None,
            action="contract.pdf_generated",
            entity_type="contract",
            entity_id=contract_pk,
            organization_id=org_uuid,
            metadata={"attachment_id": str(att.id), "size_bytes": att.size_bytes, "via": "worker"},
        )
        await db.commit()
        att_id = str(att.id)
        att_size = att.size_bytes

    log.info(
        "generate_contract_pdf.done",
        contract_id=contract_id,
        organization_id=organization_id,
        attachment_id=att_id,
        size_bytes=att_size,
    )
    return {"status": "generated", "attachment_id": att_id, "size_bytes": att_size}


async def scan_stale_leads(ctx: dict) -> dict:
    """Periodic evaluation of time-based `lead_stale` automation rules.

    Event-driven rules ride the outbox; the stale trigger has no event,
    so this cron sweeps for leads idle past each rule's `stale_days` and
    fires the rule's action (one run per lead per day, deduped by the
    `automation_runs.idempotency_key`).

    `automation_rules` and `leads` are RLS'd, so the scan must run per-org
    with the tenant GUC set. `organizations` is NOT RLS'd, so we enumerate
    org ids first (no GUC), then open a fresh per-org session with the GUC
    applied. Orgs without a stale rule short-circuit cheaply.

    Idempotent + self-isolating: `app.automations._run_rule` swallows and
    logs per-rule errors, so a single bad rule can't fail the whole sweep.
    """
    from app.automations import scan_org_stale_leads

    SessionLocal = ctx["SessionLocal"]

    async with SessionLocal() as db:
        org_ids = (await db.execute(select(Organization.id))).scalars().all()

    scanned_orgs = 0
    attempted = 0
    for org_id in org_ids:
        set_current_org_id(org_id)
        async with SessionLocal() as db:
            n = await scan_org_stale_leads(db, org_id)
        if n:
            scanned_orgs += 1
            attempted += n

    if attempted:
        log.info("automation.stale_scan", orgs=scanned_orgs, attempted=attempted)
    return {"orgs": scanned_orgs, "attempted": attempted}


async def send_whatsapp_message(
    ctx: dict,
    message_id: str,
    organization_id: str,
    template: dict | None = None,
    media: dict | None = None,
    interactive: dict | None = None,
    reaction: dict | None = None,
) -> dict:
    """Deliver one outbound WhatsApp message via the Graph API.

    Enqueued by `POST /api/whatsapp/conversations/{id}/messages` (free-form
    text), `.../template` (a pre-approved template), `.../media` (image/
    document/video/audio), or `.../interactive` (reply buttons / list menu). All
    have already persisted a `pending` outbound Message. This job loads that row
    + its conversation + the connected (non-RLS) `whatsapp_accounts` token, calls
    the matching transport function, and stamps the returned `wamid` while
    advancing the status to `sent`. A delivery/read status later rides the
    inbound webhook (`apply_status`).

    `template`, when present, is ``{"name", "language", "params"}`` and routes
    the send through `send_template`. `media`, when present, is
    ``{"media_type", "link", "media_id", "caption", "filename"}`` and routes
    through `send_media`. `interactive`, when present, is ``{"interactive_type",
    "body_text", "buttons"|"button_text"+"sections", "header_text",
    "footer_text"}`` and routes through `send_interactive`. `reaction`, when
    present, is ``{"message_id", "emoji"}`` (empty emoji = remove) and routes
    through `send_reaction`. At most one is set; otherwise plain `send_text` runs.
    The persisted `Message.body` is then a human-readable preview, not the wire
    payload.

    Worker is `crm_app` (NOBYPASSRLS), so the RLS GUC must be set before
    touching the tenant `messages`/`conversations` rows. `whatsapp_accounts` is
    the non-RLS routing root, so its SELECT doesn't depend on the GUC.

    Failure model:
      * Message gone / not pending / no active account → terminal no-op (a
        retry can't fix it), status stamped `failed` where a row exists.
      * Graph API send failure → `WhatsAppSendError`. A 4xx (Meta rejected the
        message: outside the 24h window, bad number, template required) is
        terminal — stamp `failed` + the error, don't retry. A transport/5xx is
        transient — stamp the error but raise so arq retries with backoff.

    Idempotency: a `wa_send:{id}` enqueue-dedupe key collapses double-clicks.
    On retry, the guard `status is not pending` short-circuits a row we already
    sent, so Meta never receives the same text twice from one click.
    """
    from app.whatsapp import (
        WhatsAppSendError,
        send_interactive,
        send_media,
        send_reaction,
        send_template,
        send_text,
    )

    SessionLocal = ctx["SessionLocal"]
    msg_uuid = uuid.UUID(message_id)
    org_uuid = uuid.UUID(organization_id)

    set_current_org_id(org_uuid)

    async with SessionLocal() as db:
        msg = (
            await db.execute(
                select(Message).where(Message.id == msg_uuid, Message.organization_id == org_uuid)
            )
        ).scalar_one_or_none()
        if msg is None:
            log.warning("send_whatsapp_message.missing", message_id=message_id)
            return {"status": "missing"}
        if msg.status is not MessageStatus.pending:
            # Already sent (retry after success) or already failed — no-op.
            return {"status": "already_processed", "current": msg.status.value}

        conv = (
            await db.execute(select(Conversation).where(Conversation.id == msg.conversation_id))
        ).scalar_one_or_none()
        if conv is None:
            msg.status = MessageStatus.failed
            msg.error = "conversation no longer exists"
            await db.commit()
            return {"status": "failed", "reason": "conversation_missing"}

        # Routing root — NOT RLS'd, so this lookup doesn't depend on the GUC.
        account = (
            await db.execute(select(WhatsAppAccount).where(WhatsAppAccount.id == conv.account_id))
        ).scalar_one_or_none()
        if account is None or account.status is not WhatsAppAccountStatus.active:
            msg.status = MessageStatus.failed
            msg.error = "WhatsApp number is not connected/active"
            await db.commit()
            return {"status": "failed", "reason": "account_inactive"}

        phone_number_id = account.phone_number_id
        access_token = account.access_token  # EncryptedSecret → decrypted here
        to = conv.contact_wa_id
        body = msg.body or ""
        context_wamid = msg.context_wa_message_id  # set for a quoted reply

    # Network send OUTSIDE the session — don't pin a pooled connection across
    # the Graph API round-trip.
    try:
        if template is not None:
            wamid = await send_template(
                phone_number_id=phone_number_id,
                access_token=access_token,
                to=to,
                template_name=template["name"],
                language_code=template["language"],
                body_params=template.get("params") or [],
            )
        elif media is not None:
            wamid = await send_media(
                phone_number_id=phone_number_id,
                access_token=access_token,
                to=to,
                media_type=media["media_type"],
                link=media.get("link"),
                media_id=media.get("media_id"),
                caption=media.get("caption"),
                filename=media.get("filename"),
                context_message_id=context_wamid,
            )
        elif interactive is not None:
            wamid = await send_interactive(
                phone_number_id=phone_number_id,
                access_token=access_token,
                to=to,
                interactive_type=interactive["interactive_type"],
                body_text=interactive["body_text"],
                buttons=interactive.get("buttons"),
                button_text=interactive.get("button_text"),
                sections=interactive.get("sections"),
                header_text=interactive.get("header_text"),
                footer_text=interactive.get("footer_text"),
                context_message_id=context_wamid,
            )
        elif reaction is not None:
            wamid = await send_reaction(
                phone_number_id=phone_number_id,
                access_token=access_token,
                to=to,
                message_id=reaction["message_id"],
                emoji=reaction.get("emoji") or "",
            )
        else:
            wamid = await send_text(
                phone_number_id=phone_number_id,
                access_token=access_token,
                to=to,
                body=body,
                context_message_id=context_wamid,
            )
    except WhatsAppSendError as exc:
        # 4xx = Meta rejected it (terminal); anything else = transient → retry.
        terminal = exc.status_code is not None and 400 <= exc.status_code < 500
        async with SessionLocal() as db:
            failed = (
                await db.execute(select(Message).where(Message.id == msg_uuid))
            ).scalar_one_or_none()
            if failed is not None and failed.status is MessageStatus.pending and terminal:
                failed.status = MessageStatus.failed
                failed.error = str(exc)[:2000]
            await db.commit()
        log.warning(
            "send_whatsapp_message.send_failed",
            message_id=message_id,
            organization_id=organization_id,
            status_code=exc.status_code,
            terminal=terminal,
            error=str(exc),
        )
        if terminal:
            return {"status": "failed", "reason": str(exc)}
        raise  # arq retries transient failures with backoff

    async with SessionLocal() as db:
        sent = (
            await db.execute(select(Message).where(Message.id == msg_uuid))
        ).scalar_one_or_none()
        if sent is not None and sent.status is MessageStatus.pending:
            sent.wa_message_id = wamid
            sent.status = MessageStatus.sent
            await db.commit()

    log.info(
        "send_whatsapp_message.sent",
        message_id=message_id,
        organization_id=organization_id,
        wa_message_id=wamid,
    )
    return {"status": "sent", "wa_message_id": wamid}


async def mirror_whatsapp_media(ctx: dict, wa_message_id: str, organization_id: str) -> dict:
    """Mirror one inbound media message off Meta's CDN into our S3 bucket.

    Enqueued by the webhook handler right after it persists an inbound image/
    document/video/audio/sticker. Looks the row up by `wa_message_id` (unique),
    downloads the bytes from Meta with the connected account's token, uploads
    them to S3, and stamps `Message.media_storage_key`. The agent later fetches
    them via a presigned URL — Meta's own media urls are short-lived and require
    the bearer token, so we keep our own copy.

    Worker is `crm_app` (NOBYPASSRLS), so the RLS GUC is set before any tenant
    read/write. `whatsapp_accounts` is the non-RLS routing root.

    Idempotent: a `wa_media:{wamid}` enqueue-dedupe key collapses webhook
    replays, and the `media_storage_key is not None` guard short-circuits a row
    we already mirrored. A terminal 4xx from Meta (handle expired) is logged and
    dropped; a transient error raises so arq retries with backoff.
    """
    from app.storage import put_object
    from app.whatsapp import WhatsAppSendError, fetch_media

    SessionLocal = ctx["SessionLocal"]
    org_uuid = uuid.UUID(organization_id)
    set_current_org_id(org_uuid)

    async with SessionLocal() as db:
        msg = (
            await db.execute(
                select(Message).where(
                    Message.wa_message_id == wa_message_id,
                    Message.organization_id == org_uuid,
                )
            )
        ).scalar_one_or_none()
        if msg is None:
            return {"status": "missing"}
        if msg.media_storage_key is not None:
            return {"status": "already_mirrored"}
        if not msg.media_id:
            return {"status": "no_media"}

        conv = (
            await db.execute(select(Conversation).where(Conversation.id == msg.conversation_id))
        ).scalar_one_or_none()
        if conv is None:
            return {"status": "conversation_missing"}

        # Routing root — NOT RLS'd, so this lookup doesn't depend on the GUC.
        account = (
            await db.execute(select(WhatsAppAccount).where(WhatsAppAccount.id == conv.account_id))
        ).scalar_one_or_none()
        if account is None:
            return {"status": "account_missing"}

        media_id = msg.media_id
        access_token = account.access_token  # EncryptedSecret → decrypted here
        msg_uuid = msg.id
        conv_id = conv.id

    # Network + S3 I/O OUTSIDE the session — don't pin a pooled connection.
    try:
        data, content_type = await fetch_media(media_id, access_token)
    except WhatsAppSendError as exc:
        terminal = exc.status_code is not None and 400 <= exc.status_code < 500
        log.warning(
            "mirror_whatsapp_media.fetch_failed",
            wa_message_id=wa_message_id,
            organization_id=organization_id,
            status_code=exc.status_code,
            terminal=terminal,
            error=str(exc),
        )
        if terminal:
            return {"status": "failed", "reason": str(exc)}
        raise  # transient → arq retries

    key = f"org-{organization_id}/whatsapp-media/{conv_id}/{msg_uuid}"
    await put_object(key, data, content_type)

    async with SessionLocal() as db:
        row = (await db.execute(select(Message).where(Message.id == msg_uuid))).scalar_one_or_none()
        if row is not None and row.media_storage_key is None:
            row.media_storage_key = key
            await db.commit()

    log.info(
        "mirror_whatsapp_media.mirrored",
        wa_message_id=wa_message_id,
        organization_id=organization_id,
        bytes=len(data),
    )
    return {"status": "mirrored", "key": key, "bytes": len(data)}


async def mark_whatsapp_read(ctx: dict, wa_message_id: str, organization_id: str) -> dict:
    """Send a read receipt (blue ticks) to Meta for one inbound message.

    Enqueued when the agent opens a conversation (`POST /conversations/{id}/read`)
    — we mark the most recent inbound wamid as read so the contact sees the blue
    ticks. Best-effort: Meta returns {"success": true}, there's nothing to persist.

    Worker is `crm_app` (NOBYPASSRLS); the GUC is set before the tenant read.
    `whatsapp_accounts` is the non-RLS routing root. A `wa_read:{wamid}` enqueue-
    dedupe key collapses repeat opens. Terminal 4xx is logged + dropped; a
    transient error raises so arq retries.
    """
    from app.whatsapp import WhatsAppSendError, mark_read

    SessionLocal = ctx["SessionLocal"]
    org_uuid = uuid.UUID(organization_id)
    set_current_org_id(org_uuid)

    async with SessionLocal() as db:
        msg = (
            await db.execute(
                select(Message).where(
                    Message.wa_message_id == wa_message_id,
                    Message.organization_id == org_uuid,
                )
            )
        ).scalar_one_or_none()
        if msg is None:
            return {"status": "missing"}

        conv = (
            await db.execute(select(Conversation).where(Conversation.id == msg.conversation_id))
        ).scalar_one_or_none()
        if conv is None:
            return {"status": "conversation_missing"}

        # Routing root — NOT RLS'd, so this lookup doesn't depend on the GUC.
        account = (
            await db.execute(select(WhatsAppAccount).where(WhatsAppAccount.id == conv.account_id))
        ).scalar_one_or_none()
        if account is None:
            return {"status": "account_missing"}

        phone_number_id = account.phone_number_id
        access_token = account.access_token  # EncryptedSecret → decrypted here

    # Network I/O OUTSIDE the session — don't pin a pooled connection.
    try:
        await mark_read(
            phone_number_id=phone_number_id,
            access_token=access_token,
            message_id=wa_message_id,
        )
    except WhatsAppSendError as exc:
        terminal = exc.status_code is not None and 400 <= exc.status_code < 500
        log.warning(
            "mark_whatsapp_read.failed",
            wa_message_id=wa_message_id,
            organization_id=organization_id,
            status_code=exc.status_code,
            terminal=terminal,
            error=str(exc),
        )
        if terminal:
            return {"status": "failed", "reason": str(exc)}
        raise  # transient → arq retries

    log.info(
        "mark_whatsapp_read.marked",
        wa_message_id=wa_message_id,
        organization_id=organization_id,
    )
    return {"status": "marked"}


def _dedupe_keys(clean: dict) -> tuple[str | None, str | None]:
    """The two match keys for one validated row: `lower(email)` and the
    digits-normalised phone. Either may be None (the column was blank)."""
    from app.imports import normalize_phone

    email = clean.get("email")
    email_key = email.strip().lower() if email else None
    phone_key = normalize_phone(clean.get("phone"))
    return email_key, phone_key


async def process_import(ctx: dict, import_job_id: str, organization_id: str) -> dict:
    """Run one bulk import: download → parse → validate → dedupe → write.

    Enqueued by `POST /api/imports` after the file is uploaded to S3 and
    the `ImportJob` row created (`pending`). The worker is `crm_app`
    (NOBYPASSRLS), so the RLS GUC must be set before any tenant-table
    access — including reading the job row itself.

    Failure model:
      * A whole-file failure (unreadable, empty, missing required header)
        sets `status=failed` + `error_message`; nothing is imported.
      * A per-row validation/dedupe outcome is counted
        (created/updated/skipped/error) and, for errors, sampled into
        `error_report` (capped). The job still ends `completed`.

    Atomicity & idempotency: all data writes happen in ONE transaction
    that also stamps the final counters/status, so a crash mid-write
    rolls back cleanly and arq's retry redoes the whole file from
    scratch (existing rows then match as dupes — create skips them,
    upsert re-applies the same values). The only non-idempotent effect
    of a retry is re-counting, which is fine because counters are
    overwritten, not incremented across runs. A job already `completed`
    is never reprocessed.
    """
    from app.imports import (
        ImportParseError,
        get_spec,
        normalize_phone,
        parse_table,
        resolve_headers,
        validate_row,
    )
    from app.storage import get_object

    SessionLocal = ctx["SessionLocal"]
    job_uuid = uuid.UUID(import_job_id)
    org_uuid = uuid.UUID(organization_id)

    set_current_org_id(org_uuid)

    # Phase 1 — claim the job (pending/processing → processing) and read the
    # fields we need, then release the connection before the S3 download +
    # CPU-bound parse/validate. A completed job is a no-op (double-dispatch
    # or a retry after success).
    async with SessionLocal() as db:
        job = (
            await db.execute(
                select(ImportJob).where(
                    ImportJob.id == job_uuid, ImportJob.organization_id == org_uuid
                )
            )
        ).scalar_one_or_none()
        if job is None:
            log.warning("process_import.job_missing", import_job_id=import_job_id)
            return {"status": "missing"}
        if job.status == ImportStatus.completed:
            return {"status": "already_completed"}
        job.status = ImportStatus.processing
        entity_type = job.entity_type
        mode = job.mode
        storage_key = job.storage_key
        content_type = job.content_type
        filename = job.filename
        created_by = job.created_by_user_id
        await db.commit()

    spec = get_spec(entity_type.value)
    model = _IMPORT_MODELS[entity_type]

    # Phase 2 — download + parse + validate with NO DB connection held.
    # parse_table caps at MAX_ROWS and raises ImportParseError on a
    # whole-file problem; resolve_headers reports missing required columns.
    try:
        content = await get_object(storage_key)
        headers, raw_rows = await asyncio.to_thread(parse_table, content, content_type, filename)
        header_to_field, missing = resolve_headers(spec, headers)
        if missing:
            raise ImportParseError("Missing required column(s): " + ", ".join(missing))
    except ImportParseError as exc:
        async with SessionLocal() as db:
            job = (
                await db.execute(select(ImportJob).where(ImportJob.id == job_uuid))
            ).scalar_one_or_none()
            if job is not None:
                job.status = ImportStatus.failed
                job.error_message = str(exc)
                job.finished_at = datetime.now(UTC)
                await record_audit(
                    db,
                    actor=None,
                    action="import.failed",
                    entity_type="import_job",
                    entity_id=job_uuid,
                    organization_id=org_uuid,
                    metadata={"reason": str(exc), "via": "worker"},
                )
                await db.commit()
        log.warning(
            "process_import.failed",
            import_job_id=import_job_id,
            organization_id=organization_id,
            reason=str(exc),
        )
        return {"status": "failed", "reason": str(exc)}

    # Phase 3 — one transaction: build the dedupe index from existing rows,
    # then create/upsert/skip each validated row, then stamp counters +
    # status. Atomic, so a mid-write crash rolls back the whole import.
    created = updated = skipped = errors = 0
    error_report: list[dict] = []

    async with SessionLocal() as db:
        # Existing-record dedupe index: key → row id. Built once from a
        # narrow projection (id/email/phone) so we don't load full ORM
        # objects for the whole org just to test membership. `setdefault`
        # keeps the FIRST match deterministic if the org already holds
        # duplicate keys.
        email_to_id: dict[str, uuid.UUID] = {}
        phone_to_id: dict[str, uuid.UUID] = {}
        existing = await db.execute(
            select(model.id, model.email, model.phone).where(model.organization_id == org_uuid)
        )
        for rid, email, phone in existing:
            if email:
                email_to_id.setdefault(email.strip().lower(), rid)
            pk = normalize_phone(phone)
            if pk:
                phone_to_id.setdefault(pk, rid)

        for offset, raw in enumerate(raw_rows):
            # +2: row 1 is the header, and humans count from 1.
            row_no = offset + 2
            clean, row_errors = validate_row(spec, raw, header_to_field)
            if clean is None:
                errors += 1
                if len(error_report) < _IMPORT_ERROR_REPORT_CAP:
                    for e in row_errors:
                        error_report.append({"row": row_no, **e})
                continue

            email_key, phone_key = _dedupe_keys(clean)
            match_id = (
                (email_key and email_to_id.get(email_key))
                or (phone_key and phone_to_id.get(phone_key))
                or None
            )

            if match_id is not None:
                if mode == ImportMode.upsert:
                    record = (
                        await db.execute(select(model).where(model.id == match_id))
                    ).scalar_one_or_none()
                    if record is not None:
                        # Only non-empty incoming values overwrite — a blank
                        # cell is "no change", not "clear the field".
                        for fld, val in clean.items():
                            if val is not None:
                                setattr(record, fld, val)
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
                continue

            # New record. owner defaults to the importer so the rows land
            # in their pipeline view; org_id is set explicitly (RLS would
            # reject a row whose org_id doesn't match the GUC anyway).
            obj = model(**clean, organization_id=org_uuid)
            if hasattr(obj, "owner_id") and created_by is not None:
                obj.owner_id = created_by
            db.add(obj)
            await db.flush()  # assign PK so within-file dupes match this row
            created += 1
            if email_key:
                email_to_id.setdefault(email_key, obj.id)
            if phone_key:
                phone_to_id.setdefault(phone_key, obj.id)

        job = (
            await db.execute(select(ImportJob).where(ImportJob.id == job_uuid))
        ).scalar_one_or_none()
        if job is None:
            # Job deleted mid-flight (org teardown). Abandon the writes.
            await db.rollback()
            log.warning("process_import.job_vanished", import_job_id=import_job_id)
            return {"status": "missing"}
        job.status = ImportStatus.completed
        job.total_rows = len(raw_rows)
        job.created_count = created
        job.updated_count = updated
        job.skipped_count = skipped
        job.error_count = errors
        job.error_report = error_report or None
        job.finished_at = datetime.now(UTC)
        await record_audit(
            db,
            actor=None,
            action="import.completed",
            entity_type="import_job",
            entity_id=job_uuid,
            organization_id=org_uuid,
            metadata={
                "entity_type": entity_type.value,
                "mode": mode.value,
                "total_rows": len(raw_rows),
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "errors": errors,
                "via": "worker",
            },
        )
        await db.commit()

    log.info(
        "process_import.done",
        import_job_id=import_job_id,
        organization_id=organization_id,
        total_rows=len(raw_rows),
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )
    return {
        "status": "completed",
        "total_rows": len(raw_rows),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


async def prune_expired_invites(ctx: dict) -> dict:
    """Daily sweep: delete OrgInvite rows that expired > 30 days ago and
    were never accepted. Keeps the table clean for audit while preserving
    recently-expired rows in case an admin needs to see the history.

    `org_invites` is NOT RLS'd (invites are org-scoped by FK, not by
    policy), so no tenant GUC needed here.
    """
    SessionLocal = ctx["SessionLocal"]
    cutoff = datetime.now(UTC) - timedelta(days=30)
    async with SessionLocal() as db:
        result = await db.execute(
            delete(OrgInvite).where(
                OrgInvite.accepted_at.is_(None),
                OrgInvite.expires_at < cutoff,
            )
        )
        await db.commit()
    pruned = result.rowcount
    log.info("invites.pruned", count=pruned)
    return {"pruned": pruned}
