"""Optimistic-locking guard shared by versioned entities (TD-12).

Deal pioneered the pattern (migration `4d3d59906702`); Customer and
Task adopt it (`9a8b7c6d5e4f`). Each carries a `version int` bumped on
every mutation. Clients echo the value they last read as `If-Match`;
a mismatch means someone else wrote in between → 412 Precondition
Failed (RFC 7232 §4.2). The header is REQUIRED (strict mode, 2026-06-04):
a missing header → 428 Precondition Required (RFC 6585 §3). The frontend
echoes `version` on every mutation path (customer PATCH, task PATCH,
deal `/move`), so there is no lenient rollout window left.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status

from app.logging_setup import get_logger

log = get_logger(__name__)


def check_if_match(
    *,
    entity: str,
    entity_id: uuid.UUID | str,
    current_version: int,
    if_match: str | None,
) -> None:
    """Enforce the optimistic-locking precondition.

    - missing header → 428 Precondition Required
    - non-integer value → 400 Bad Request
    - value ≠ `current_version` → 412 Precondition Failed
    """
    if if_match is None:
        log.warning(
            f"{entity}.if_match_missing",
            entity_id=str(entity_id),
            current_version=current_version,
        )
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="If-Match header is required for this mutation.",
        )
    # Accept both the bare form (`If-Match: 7`) and the RFC etag-quoted
    # form (`If-Match: "7"`) for client ergonomics.
    raw = if_match.strip().strip('"')
    try:
        sent = int(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"If-Match must be an integer, got {if_match!r}",
        ) from None
    if sent != current_version:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=(
                f"{entity.capitalize()} version mismatch: client has {sent}, "
                f"current is {current_version}. Reload before retrying."
            ),
        )
