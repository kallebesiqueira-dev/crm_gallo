"""Per-org custom-field validation & coercion.

Custom fields are an org-defined schema extension: admins declare
`CustomFieldDefinition` rows (one per field, per entity type), and the
actual values live in a JSONB `custom_fields` bag on each entity. The
definitions can't be expressed as static Pydantic models — they're data,
loaded per request — so validation happens here, in the API layer,
against the live definitions for (org, entity_type).

`validate_custom_fields` is the single choke point. Every lead /
customer / deal / company create+update routes its incoming
`custom_fields` through it before persisting. Unknown keys, wrong types,
out-of-range select options, and (on create) missing required fields all
raise 422.
"""

import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CustomFieldDefinition, CustomFieldType

# The entity types that can carry custom fields. Mirrors the ENTITY_*
# slugs in app/activities.py — kept here so this module has no reason to
# import the API layer.
ENTITY_TYPES = ("lead", "customer", "deal", "company")


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


async def load_definitions(
    db: AsyncSession, org_id: uuid.UUID, entity_type: str
) -> list[CustomFieldDefinition]:
    """All live definitions for one (org, entity_type), in display order."""
    result = await db.execute(
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.organization_id == org_id,
            CustomFieldDefinition.entity_type == entity_type,
        )
        .order_by(CustomFieldDefinition.position.asc(), CustomFieldDefinition.label.asc())
    )
    return list(result.scalars().all())


def _coerce_one(defn: CustomFieldDefinition, value: object) -> object:
    """Coerce/validate a single value against its definition. Returns the
    JSON-serialisable stored form. Raises 422 on type mismatch."""
    label = defn.label
    t = defn.field_type

    if t in (CustomFieldType.text, CustomFieldType.textarea):
        if not isinstance(value, str):
            raise _bad(f"'{label}' must be text")
        return value

    if t == CustomFieldType.url:
        if not isinstance(value, str):
            raise _bad(f"'{label}' must be a URL string")
        if value and not (value.startswith("http://") or value.startswith("https://")):
            raise _bad(f"'{label}' must start with http:// or https://")
        return value

    if t == CustomFieldType.email:
        if not isinstance(value, str):
            raise _bad(f"'{label}' must be an email string")
        if value and "@" not in value:
            raise _bad(f"'{label}' must be a valid email")
        return value

    if t == CustomFieldType.number:
        # Reject bool (a subclass of int) — a checkbox is not a number.
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise _bad(f"'{label}' must be a number")
        return value

    if t == CustomFieldType.boolean:
        if not isinstance(value, bool):
            raise _bad(f"'{label}' must be true or false")
        return value

    if t == CustomFieldType.date:
        if not isinstance(value, str):
            raise _bad(f"'{label}' must be an ISO date string (YYYY-MM-DD)")
        try:
            date.fromisoformat(value)
        except ValueError as e:
            raise _bad(f"'{label}' must be a valid date (YYYY-MM-DD)") from e
        return value

    if t == CustomFieldType.select:
        options = defn.options or []
        if value not in options:
            raise _bad(f"'{label}' must be one of: {', '.join(map(str, options))}")
        return value

    if t == CustomFieldType.multiselect:
        options = defn.options or []
        if not isinstance(value, list):
            raise _bad(f"'{label}' must be a list of choices")
        for v in value:
            if v not in options:
                raise _bad(f"'{label}' contains an invalid choice: {v}")
        return value

    # Unreachable while the enum is exhaustive above.
    raise _bad(f"'{label}' has an unsupported field type")


async def validate_custom_fields(
    db: AsyncSession,
    org_id: uuid.UUID,
    entity_type: str,
    incoming: dict | None,
    *,
    existing: dict | None = None,
    partial: bool,
) -> dict:
    """Validate + coerce an incoming `custom_fields` bag.

    - `incoming` is the client-supplied bag (may be None / omitted).
    - On create (`partial=False`) required fields must be present.
    - On update (`partial=True`) only the supplied keys are validated and
      merged onto `existing`; required fields aren't re-checked (the row
      already satisfied them at create).
    - Unknown keys (not matching any live definition) always raise 422.

    Returns the full bag to persist.
    """
    incoming = incoming or {}
    base = dict(existing or {})

    defns = await load_definitions(db, org_id, entity_type)
    by_key = {d.key: d for d in defns}

    unknown = set(incoming) - set(by_key)
    if unknown:
        raise _bad(f"Unknown custom field(s): {', '.join(sorted(unknown))}")

    cleaned: dict = {}
    for key, value in incoming.items():
        defn = by_key[key]
        # Explicit clear: null / "" / [] drops the value from the bag.
        if value is None or value == "" or value == []:
            base.pop(key, None)
            continue
        cleaned[key] = _coerce_one(defn, value)

    if not partial:
        for defn in defns:
            if defn.required and defn.key not in cleaned:
                raise _bad(f"'{defn.label}' is required")

    base.update(cleaned)
    return base
