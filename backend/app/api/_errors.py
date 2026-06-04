"""Translate low-level DB integrity errors into friendly HTTP responses.

Lead and Customer carry a partial-unique index on
`(organization_id, lower(email)) WHERE deleted_at IS NULL`
(`uq_leads_org_email_live` / `uq_customers_org_email_live`, migration
`ddd83138c832`). A duplicate email otherwise surfaces as a raw
`IntegrityError` → HTTP 500; this maps it to a 409 with a human message and
re-raises anything else so genuine failures are never masked.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError


def raise_for_duplicate_email(exc: IntegrityError, entity: str) -> NoReturn:
    """Re-raise `exc` unless it is the per-org email-uniqueness violation, in
    which case raise a 409. Call this from an `except IntegrityError` block
    AFTER `await db.rollback()`.

    Both indices share the `_org_email_live` suffix, so matching the
    constraint name keeps the 409 specific to the email collision and lets
    every other integrity failure (FKs, other unique indices) propagate
    untouched.
    """
    if "_org_email_live" in str(exc.orig):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {entity} with this email already exists in this workspace.",
        ) from exc
    raise exc
