"""No-/low-code automation engine — the consumer that turns outbox
events (and a time-based scan) into actions. Built on ADR-007.

Two firing paths, one executor:

  * **Event-driven** — `run_event_automations` is a wildcard outbox
    subscriber (registered in `app.events_dispatcher`, mirroring
    `_fanout_to_webhooks`). For each fired event it loads the org's
    enabled rules whose `trigger` matches the event type and runs each.
  * **Time-based** — the `scan_stale_leads` cron (in `app.worker.jobs`)
    evaluates `lead_stale` rules against `Lead.updated_at` and calls the
    same `_run_rule`.

Idempotency is a UNIQUE `automation_runs.idempotency_key`: event runs key
on `{rule}:{event_id}` (the outbox drain is at-least-once), stale runs on
`{rule}:{lead}:{date}` (fire once per lead per day). A duplicate key →
the run is skipped. Per-rule errors are caught and logged as a failed
run; they never propagate, so one broken rule can't wedge the outbox
drain or storm the webhook fanout sharing the same event.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities import ENTITY_DEAL, ENTITY_LEAD, ActivityType, record_activity
from app.database import SessionLocal, set_current_org_id
from app.events import EventType
from app.models import (
    AutomationAction,
    AutomationRule,
    AutomationRun,
    AutomationTrigger,
    Deal,
    DealStage,
    Lead,
    LeadStage,
    Task,
    TaskPriority,
    TaskStatus,
)
from app.notifications import NotificationType, notify

if TYPE_CHECKING:
    from app.events_dispatcher import EventContext

log = structlog.get_logger(__name__)


# Which outbox EventType drives which automation trigger. `lead_stale`
# is intentionally absent — it has no event, the cron evaluates it.
EVENT_TRIGGERS: dict[EventType, AutomationTrigger] = {
    EventType.lead_created: AutomationTrigger.lead_created,
    EventType.deal_created: AutomationTrigger.deal_created,
    EventType.deal_won: AutomationTrigger.deal_won,
    EventType.deal_lost: AutomationTrigger.deal_lost,
    EventType.deal_stage_changed: AutomationTrigger.deal_stage_changed,
}

# Which payload key carries the subject entity's id, per trigger, plus
# the activity/Task entity label. Lead triggers carry `lead_id`; every
# deal trigger carries `deal_id`.
_ENTITY_FOR_TRIGGER: dict[AutomationTrigger, str] = {
    AutomationTrigger.lead_created: ENTITY_LEAD,
    AutomationTrigger.deal_created: ENTITY_DEAL,
    AutomationTrigger.deal_won: ENTITY_DEAL,
    AutomationTrigger.deal_lost: ENTITY_DEAL,
    AutomationTrigger.deal_stage_changed: ENTITY_DEAL,
    AutomationTrigger.lead_stale: ENTITY_LEAD,
}

# Hard cap so a misconfigured stale rule can't spawn thousands of rows in
# one sweep — process the oldest N stale leads per rule per tick.
_STALE_SCAN_LIMIT = 200
# Default staleness threshold when a rule omits `stale_days`.
_DEFAULT_STALE_DAYS = 7


def _cfg(rule: AutomationRule) -> dict[str, Any]:
    try:
        parsed = json.loads(rule.action_config or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


async def _execute_action(
    db: AsyncSession,
    rule: AutomationRule,
    *,
    org_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    owner_id: uuid.UUID | None,
) -> str:
    """Perform the rule's action against one entity. Returns a short
    human-readable detail string for the run log. Raises on a genuine
    failure (caught by the caller and logged as a failed run).

    All mutations land in the caller's session/transaction — the caller
    commits them together with the `AutomationRun` row so action + log
    are atomic.
    """
    cfg = _cfg(rule)

    if rule.action == AutomationAction.create_task:
        due_in_days = cfg.get("due_in_days")
        due_date = None
        if isinstance(due_in_days, int) and due_in_days >= 0:
            due_date = (datetime.now(UTC) + timedelta(days=due_in_days)).date()
        try:
            priority = TaskPriority(cfg.get("priority", "medium"))
        except ValueError:
            priority = TaskPriority.medium
        assignee_id = owner_id if cfg.get("assignee", "owner") == "owner" else None
        task = Task(
            organization_id=org_id,
            title=(cfg.get("title") or rule.name)[:255],
            description=cfg.get("description"),
            status=TaskStatus.todo,
            priority=priority,
            due_date=due_date,
            assignee_id=assignee_id,
            lead_id=entity_id if entity_type == ENTITY_LEAD else None,
            deal_id=entity_id if entity_type == ENTITY_DEAL else None,
        )
        db.add(task)
        await db.flush()
        return f"created task {task.id}"

    if rule.action == AutomationAction.send_notification:
        if owner_id is None:
            return "no owner to notify"
        await notify(
            db,
            user_id=owner_id,
            organization_id=org_id,
            notification_type=NotificationType.automation,
            title=(cfg.get("title") or rule.name)[:255],
            body=cfg.get("body"),
            link_url=f"/{entity_type}s/{entity_id}",
            metadata={"automation_rule_id": str(rule.id)},
        )
        return f"notified {owner_id}"

    if rule.action == AutomationAction.change_stage:
        if entity_type != ENTITY_DEAL:
            return "change_stage ignored (not a deal)"
        try:
            to_stage = DealStage(cfg.get("to_stage"))
        except ValueError:
            raise ValueError(f"invalid to_stage: {cfg.get('to_stage')!r}") from None
        deal = (
            await db.execute(
                select(Deal).where(Deal.id == entity_id, Deal.organization_id == org_id)
            )
        ).scalar_one_or_none()
        if deal is None:
            return "deal not found"
        if deal.stage == to_stage:
            return f"already in {to_stage.value}"
        prev = deal.stage
        deal.stage = to_stage
        deal.version = deal.version + 1
        # Deliberately NOT re-emitting a deal.stage_changed outbox event:
        # an automation-driven stage move must not cascade into another
        # automation run (loop) or a duplicate webhook fanout. The
        # timeline still records it (actor=None = system).
        await record_activity(
            db,
            entity_type=ENTITY_DEAL,
            entity_id=deal.id,
            activity_type=ActivityType.stage_change,
            organization_id=org_id,
            actor=None,
            content=None,
            metadata={"from": prev.value, "to": to_stage.value, "via": "automation"},
        )
        return f"moved {prev.value} -> {to_stage.value}"

    return f"unknown action {rule.action}"


async def _run_rule(
    db: AsyncSession,
    rule: AutomationRule,
    *,
    org_id: uuid.UUID,
    idempotency_key: str,
    entity_type: str,
    entity_id: uuid.UUID,
    owner_id: uuid.UUID | None,
) -> str:
    """Execute one rule against one entity, idempotently, committing the
    action + the `AutomationRun` together. Returns the run status
    (`success` / `skipped` / `failed`). Never raises — a failure is
    logged as a `failed` run so it surfaces in the admin log without
    wedging the dispatcher.
    """
    run = AutomationRun(
        rule_id=rule.id,
        organization_id=org_id,
        idempotency_key=idempotency_key,
        status="success",
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(run)
    try:
        # Flush the run row first so a duplicate idempotency_key trips the
        # UNIQUE constraint BEFORE we do the action's work.
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return "skipped"

    try:
        detail = await _execute_action(
            db,
            rule,
            org_id=org_id,
            entity_type=entity_type,
            entity_id=entity_id,
            owner_id=owner_id,
        )
        run.detail = detail
        rule.run_count = rule.run_count + 1
        rule.last_run_at = datetime.now(UTC)
        await db.commit()
        return "success"
    except Exception as exc:  # noqa: BLE001 — isolate one rule's failure
        await db.rollback()
        log.warning(
            "automation.rule_failed",
            rule_id=str(rule.id),
            action=rule.action.value,
            error=str(exc),
        )
        # Best-effort failure log, in a fresh transaction, carrying the
        # same idempotency_key so a re-fire of the same event doesn't
        # re-attempt a rule that already errored.
        try:
            failed = AutomationRun(
                rule_id=rule.id,
                organization_id=org_id,
                idempotency_key=idempotency_key,
                status="failed",
                entity_type=entity_type,
                entity_id=entity_id,
                detail=str(exc)[:2000],
            )
            db.add(failed)
            await db.commit()
        except IntegrityError:
            await db.rollback()
        return "failed"


async def run_event_automations(ctx: EventContext) -> None:
    """Wildcard outbox subscriber: run every enabled rule whose trigger
    matches this event. Registered against each event type in
    `EVENT_TRIGGERS` by `app.events_dispatcher`.

    Swallows per-rule errors (logged as failed runs) and never raises —
    a broken rule must not fail the outbox row (which would retry the
    whole dispatch, re-firing webhooks).
    """
    if ctx.organization_id is None:
        return
    try:
        event_type = EventType(ctx.event_type)
    except ValueError:
        return
    trigger = EVENT_TRIGGERS.get(event_type)
    if trigger is None:
        return

    org_id = ctx.organization_id
    entity_type = _ENTITY_FOR_TRIGGER[trigger]
    id_key = "lead_id" if entity_type == ENTITY_LEAD else "deal_id"
    raw_entity_id = ctx.payload.get(id_key)
    if raw_entity_id is None:
        return
    entity_id = uuid.UUID(str(raw_entity_id))
    raw_owner = ctx.payload.get("owner_id")
    owner_id = uuid.UUID(str(raw_owner)) if raw_owner else None

    # RLS: the worker is crm_app (NOBYPASSRLS). Set the tenant GUC so the
    # automation_rules SELECT (an RLS'd table) sees this org's rows.
    set_current_org_id(org_id)

    async with SessionLocal() as db:
        rules = (
            (
                await db.execute(
                    select(AutomationRule).where(
                        AutomationRule.organization_id == org_id,
                        AutomationRule.trigger == trigger,
                        AutomationRule.enabled.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        for rule in rules:
            await _run_rule(
                db,
                rule,
                org_id=org_id,
                idempotency_key=f"{rule.id}:{ctx.event_id}",
                entity_type=entity_type,
                entity_id=entity_id,
                owner_id=owner_id,
            )


async def scan_org_stale_leads(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Evaluate one org's `lead_stale` rules and fire actions on leads
    idle past each rule's threshold. Caller has already set the RLS GUC
    for `org_id`. Returns the number of (rule, lead) actions attempted.
    """
    rules = (
        (
            await db.execute(
                select(AutomationRule).where(
                    AutomationRule.organization_id == org_id,
                    AutomationRule.trigger == AutomationTrigger.lead_stale,
                    AutomationRule.enabled.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rules:
        return 0

    today = date.today().isoformat()
    attempted = 0
    for rule in rules:
        cfg = _cfg(rule)
        stale_days = cfg.get("stale_days", _DEFAULT_STALE_DAYS)
        if not isinstance(stale_days, int) or stale_days < 0:
            stale_days = _DEFAULT_STALE_DAYS
        cutoff = datetime.now(UTC) - timedelta(days=stale_days)
        stale = (
            (
                await db.execute(
                    select(Lead.id, Lead.owner_id)
                    .where(
                        Lead.organization_id == org_id,
                        Lead.stage.notin_([LeadStage.won, LeadStage.lost]),
                        Lead.updated_at < cutoff,
                    )
                    .order_by(Lead.updated_at)
                    .limit(_STALE_SCAN_LIMIT)
                )
            )
            .all()
        )
        for lead_id, owner_id in stale:
            attempted += 1
            await _run_rule(
                db,
                rule,
                org_id=org_id,
                idempotency_key=f"{rule.id}:{lead_id}:{today}",
                entity_type=ENTITY_LEAD,
                entity_id=lead_id,
                owner_id=owner_id,
            )
    return attempted
