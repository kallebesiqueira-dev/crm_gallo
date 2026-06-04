"""Optimistic-locking guard shared by versioned entities (TD-12).

Deal pioneered the pattern (migration `4d3d59906702`); Customer and
Task adopt it (`9a8b7c6d5e4f`). Each carries a `version int` bumped on
every mutation. Clients echo the value they last read as `If-Match`;
a mismatch means someone else wrote in between → 412 Precondition
Failed (RFC 7232 §4.2). v1 keeps the header OPTIONAL — a missing header
logs a warning (rollout signal) and proceeds, so the frontend doesn't
have to land in lockstep.
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
    """Raise 412 if `if_match` disagrees with `current_version`; 400 if it
    is not an integer. A missing header is lenient (logs `{entity}.if_match_missing`).
    """
    if if_match is None:
        log.warning(
            f"{entity}.if_match_missing",
            entity_id=str(entity_id),
            current_version=current_version,
        )
        return
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
