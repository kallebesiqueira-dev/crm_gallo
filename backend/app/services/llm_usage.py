"""Persist per-org LLM token usage (cost observability).

Pairs with `app.services.llm.capture_usage`: a call site wraps its blocking
LLM call in `with llm.capture_usage() as usage:` and then hands the collected
records here with the org/user context it owns. Keeping persistence out of
`llm.py` means that module stays DB-free.

Best-effort: a metering failure must never break the user-facing AI feature,
so errors are swallowed (logged). Adds rows to the caller's session and
commits them — the RLS `app.current_org_id` GUC is already set by the request
(`get_current_org_id`) or the worker (`set_current_org_id`), so the inserts
pass the `tenant_isolation` WITH CHECK.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LlmUsage

logger = logging.getLogger(__name__)


async def persist_usage(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    use_case: str,
    records: list[dict],
    user_id: uuid.UUID | None = None,
) -> None:
    if not records:
        return
    try:
        for r in records:
            db.add(
                LlmUsage(
                    organization_id=organization_id,
                    user_id=user_id,
                    use_case=use_case,
                    provider=r.get("provider", ""),
                    model=r.get("model", ""),
                    input_tokens=r.get("input_tokens", 0),
                    output_tokens=r.get("output_tokens", 0),
                )
            )
        await db.commit()
    except Exception:
        # Metering is never worth failing (or rolling back) the actual call for.
        logger.warning("llm_usage.persist_failed", exc_info=True)
        await db.rollback()
