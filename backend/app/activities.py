"""User-facing activity helper — analogue to `app.audit.record_audit`
but targeted at the timeline view, not the security ledger.

Why a separate ledger:
  * `audit_logs` records EVERY mutation including system events that
    are noise for a sales rep (e.g. login, cache invalidation,
    soft-delete metadata). Admin-only. Retention is forensic.
  * `activities` records ONLY the events a user reading a customer /
    lead / deal page cares about. Visible to any org member. Curated
    type vocabulary (the `ActivityType` enum) so the UI can render
    icons + i18n labels without parsing free-form strings.

Calling convention mirrors `record_audit`: emit alongside the audit
row at the same commit boundary so both ledgers stay consistent
with the underlying mutation.
"""

from __future__ import annotations

import enum
import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, User


class ActivityType(str, enum.Enum):
    """Curated event vocabulary the timeline UI knows how to render.
    Adding a new type is two changes: a member here + a translation
    in the frontend `activity.*` namespace. No schema migration —
    the column is a free-form string."""

    # Lifecycle
    created = "created"
    updated = "updated"
    deleted = "deleted"
    restored = "restored"

    # Lead / Deal specific
    stage_change = "stage_change"
    ai_scored = "ai_scored"

    # Conversational / activity
    note_added = "note_added"
    file_attached = "file_attached"
    file_removed = "file_removed"
    call = "call"
    meeting = "meeting"
    email_sent = "email_sent"
    email_received = "email_received"

    # Workflow
    task_completed = "task_completed"
    imported = "imported"
    system = "system"


# Entity strings used in `activities.entity_type`. Kept as plain
# strings (not an enum) so a future Quote / Contract entity can opt
# in without modifying this module.
ENTITY_LEAD = "lead"
ENTITY_CUSTOMER = "customer"
ENTITY_DEAL = "deal"
ENTITY_COMPANY = "company"


async def record_activity(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    activity_type: ActivityType,
    organization_id: uuid.UUID,
    actor: User | None = None,
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Activity:
    """Append one activity row. Same session as the caller — the
    caller's commit/rollback decides durability, so a failed lead
    update doesn't leave an orphan activity claiming the change
    happened.

    `content` is the free-form summary string the UI renders as the
    primary line. Optional — for type=stage_change the UI can build
    a label from the metadata alone (`{"from": "new", "to": "qualified"}`).

    `metadata` is stored as JSON. None → null in the DB.
    """
    row = Activity(
        organization_id=organization_id,
        actor_user_id=actor.id if actor else None,
        entity_type=entity_type,
        entity_id=entity_id,
        type=activity_type.value,
        content=content,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(row)
    # Flush so the caller can rely on `row.id` being populated; the
    # outer transaction is still in-flight.
    await db.flush()
    return row
