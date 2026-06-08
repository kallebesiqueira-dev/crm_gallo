"""Automation rules CRUD + execution log (ADR-007).

The rule is config — the firing happens out-of-band in the worker
(`app.automations`): event-driven rules ride the outbox dispatch,
time-based `lead_stale` rules run on the `scan_stale_leads` cron. This
router only manages the rule rows and surfaces the run log.

`action_config` is exchanged as a JSON object but stored as text on the
model (sqlite-test parity, like webhook `enabled_events`) — we serialise
on write and parse on read.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import get_current_org_id, get_current_user, require_roles
from app.models import AutomationRule, AutomationRun, User, UserRole
from app.schemas import (
    AutomationRuleCreate,
    AutomationRuleOut,
    AutomationRuleUpdate,
    AutomationRunOut,
)

router = APIRouter(prefix="/api/automations", tags=["automations"])

# Automations mutate CRM data on their own (create tasks, move deals), so
# creating/editing them is an admin/manager privilege. Listing rules and
# the run log is read-only and open to any member.
manage = require_roles(UserRole.admin, UserRole.manager)


def _rule_out(rule: AutomationRule) -> AutomationRuleOut:
    try:
        cfg = json.loads(rule.action_config or "{}")
        if not isinstance(cfg, dict):
            cfg = {}
    except json.JSONDecodeError:
        cfg = {}
    return AutomationRuleOut(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        trigger=rule.trigger,
        action=rule.action,
        action_config=cfg,
        run_count=rule.run_count,
        last_run_at=rule.last_run_at,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


async def _get_rule_or_404(
    db: AsyncSession, rule_id: uuid.UUID, org_id: uuid.UUID
) -> AutomationRule:
    rule = (
        await db.execute(
            select(AutomationRule).where(
                AutomationRule.id == rule_id, AutomationRule.organization_id == org_id
            )
        )
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    return rule


@router.get("", response_model=list[AutomationRuleOut])
async def list_rules(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[AutomationRuleOut]:
    rules = (
        (
            await db.execute(
                select(AutomationRule)
                .where(AutomationRule.organization_id == org_id)
                .order_by(AutomationRule.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_rule_out(r) for r in rules]


@router.post("", response_model=AutomationRuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: AutomationRuleCreate,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> AutomationRuleOut:
    rule = AutomationRule(
        organization_id=org_id,
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
        trigger=payload.trigger,
        action=payload.action,
        action_config=json.dumps(payload.action_config or {}),
        created_by_user_id=user.id,
    )
    db.add(rule)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="automation_rule.create",
        entity_type="automation_rule",
        entity_id=rule.id,
        organization_id=org_id,
        metadata={"trigger": rule.trigger.value, "action": rule.action.value},
    )
    await db.commit()
    await db.refresh(rule)
    return _rule_out(rule)


@router.patch("/{rule_id}", response_model=AutomationRuleOut)
async def update_rule(
    rule_id: uuid.UUID,
    payload: AutomationRuleUpdate,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> AutomationRuleOut:
    rule = await _get_rule_or_404(db, rule_id, org_id)
    changes = payload.model_dump(exclude_unset=True)
    if "action_config" in changes:
        rule.action_config = json.dumps(changes.pop("action_config") or {})
    for field, value in changes.items():
        setattr(rule, field, value)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="automation_rule.update",
        entity_type="automation_rule",
        entity_id=rule.id,
        organization_id=org_id,
        metadata={"fields": list(payload.model_dump(exclude_unset=True).keys())},
    )
    await db.commit()
    await db.refresh(rule)
    return _rule_out(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    rule = await _get_rule_or_404(db, rule_id, org_id)
    await db.delete(rule)
    await record_audit(
        db,
        actor=user,
        action="automation_rule.delete",
        entity_type="automation_rule",
        entity_id=rule_id,
        organization_id=org_id,
    )
    await db.commit()


@router.get("/runs", response_model=list[AutomationRunOut])
async def list_runs(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    rule_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[AutomationRunOut]:
    # automation_runs is NOT RLS'd (worker writes cross-org), so scope the
    # read explicitly by the denormalised organization_id.
    stmt = select(AutomationRun).where(AutomationRun.organization_id == org_id)
    if rule_id is not None:
        stmt = stmt.where(AutomationRun.rule_id == rule_id)
    stmt = stmt.order_by(AutomationRun.created_at.desc()).limit(limit)
    runs = (await db.execute(stmt)).scalars().all()
    return [AutomationRunOut.model_validate(r) for r in runs]
