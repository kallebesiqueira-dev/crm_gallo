"""Audit log helper. Writes mutation events to the audit_logs table."""

import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_setup import get_logger
from app.models import AuditLog, User

log = get_logger(__name__)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):  # enum
        return value.value
    return value


async def record_audit(
    db: AsyncSession,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
    organization_id: uuid.UUID | None = None,
    commit: bool = False,
) -> None:
    """Append an entry to the audit log.

    `organization_id` is nullable on the column itself — platform-level
    events (login, logout, Stripe webhook reconciliation) leave it None.
    Tenant-scoped mutations should always pass `organization_id` so the
    audit can be filtered per-org in reporting later.

    Caller is responsible for the outer transaction unless commit=True.
    Errors are logged but never raised — auditing must not break the request.
    """
    try:
        payload = None
        if metadata is not None:
            sanitized = {k: _to_jsonable(v) for k, v in metadata.items()}
            payload = json.dumps(sanitized, default=str)

        entry = AuditLog(
            actor_id=actor.id if actor else None,
            organization_id=organization_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            metadata_json=payload,
        )
        db.add(entry)
        if commit:
            await db.commit()
        log.info(
            "audit",
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            actor_id=str(actor.id) if actor else None,
            organization_id=str(organization_id) if organization_id else None,
        )
    except Exception as e:
        log.warning("audit_failed", action=action, error=str(e))
