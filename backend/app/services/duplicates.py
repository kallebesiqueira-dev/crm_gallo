"""Duplicate detection + merge for contact-shaped + account entities.

Detection groups live rows that collide on a normalised signal — email,
phone (digits only), or name (lower/trimmed). It is exact-on-normalised,
NOT trigram-fuzzy: pg_trgm would mean a Postgres extension in the
migration, which the deploy path keeps portable on purpose. Exact-on-
normalised already catches the overwhelming majority of real dupes
(case, whitespace, phone formatting) with zero schema cost; trigram
ranking is a clean follow-up if customers ask for it.

Merge folds one or more `loser` rows into a `survivor`: every child that
points at a loser is re-parented to the survivor, then the losers are
soft-deleted. The survivor's own scalar fields are left untouched —
field-level "keep this value from that record" is a UI concern and out
of scope here.
"""

import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    Company,
    Contract,
    Customer,
    Deal,
    EntityTag,
    FileAttachment,
    Lead,
    Note,
    Quote,
    Task,
)
from app.schemas import DuplicateGroup, DuplicateRecord, MergeResult

DUPLICATE_ENTITY_TYPES = ("lead", "customer", "company")

_MODELS: dict[str, type] = {"lead": Lead, "customer": Customer, "company": Company}

# Typed FK columns that point at the merged entity, per entity type.
# Each tuple is (referencing_model, fk_attribute_name).
_TYPED_FK_REFS: dict[str, list[tuple[type, str]]] = {
    "lead": [(Task, "lead_id")],
    "customer": [
        (Deal, "customer_id"),
        (Task, "customer_id"),
        (Quote, "customer_id"),
        (Contract, "customer_id"),
    ],
    "company": [
        (Lead, "company_id"),
        (Customer, "company_id"),
        (Deal, "company_id"),
    ],
}

# Polymorphic (entity_type, entity_id) references — identical for every
# mergeable entity type. EntityTag is handled separately because its
# unique constraint needs dedupe on re-parent.
_POLY_MODELS: tuple[type, ...] = (Note, Activity, FileAttachment)


def _norm_phone(value: str | None) -> str:
    return re.sub(r"\D", "", value) if value else ""


def _norm_str(value: str | None) -> str:
    return value.strip().lower() if value else ""


def _label_and_signals(entity_type: str, row) -> tuple[str, dict[str, str]]:
    if entity_type == "company":
        label = (row.name or "").strip()
        name_sig = _norm_str(row.name)
    else:
        label = f"{row.first_name} {row.last_name}".strip()
        name_sig = _norm_str(f"{row.first_name} {row.last_name}")
    return label, {
        "email": _norm_str(row.email),
        "phone": _norm_phone(row.phone),
        "name": name_sig,
    }


async def detect_duplicates(
    db: AsyncSession, org_id: uuid.UUID, entity_type: str
) -> list[DuplicateGroup]:
    """Live rows of `entity_type` grouped by colliding signal.

    A record can appear in several groups (e.g. shares an email with one
    row and a phone with another) — each signal is its own group so the
    user can act on them independently.
    """
    model = _MODELS[entity_type]
    rows = (await db.execute(select(model).where(model.organization_id == org_id))).scalars().all()

    buckets: dict[str, dict[str, list[uuid.UUID]]] = {
        "email": defaultdict(list),
        "phone": defaultdict(list),
        "name": defaultdict(list),
    }
    info: dict[uuid.UUID, DuplicateRecord] = {}
    for row in rows:
        label, signals = _label_and_signals(entity_type, row)
        info[row.id] = DuplicateRecord(
            id=row.id,
            label=label or "—",
            email=row.email,
            phone=row.phone,
            created_at=row.created_at,
        )
        for signal, value in signals.items():
            if value:
                buckets[signal][value].append(row.id)

    groups: list[DuplicateGroup] = []
    for signal in ("email", "phone", "name"):
        for value, ids in buckets[signal].items():
            if len(ids) < 2:
                continue
            members = sorted((info[i] for i in ids), key=lambda r: r.created_at)
            groups.append(DuplicateGroup(match_type=signal, key=value, records=members))
    # Largest collisions first, then a stable order by key.
    groups.sort(key=lambda g: (-len(g.records), g.match_type, g.key))
    return groups


async def merge_records(
    db: AsyncSession,
    org_id: uuid.UUID,
    entity_type: str,
    survivor_id: uuid.UUID,
    loser_ids: list[uuid.UUID],
) -> MergeResult:
    """Re-parent every child of `loser_ids` onto `survivor_id`, soft-delete
    the losers, and report per-relation counts. Does NOT commit — the
    caller owns the transaction (so the audit entry lands atomically).

    Raises:
        ValueError("no_losers") — losers reduce to empty after dedupe.
        LookupError("survivor" | "loser") — an id is missing/soft-deleted/
            out of org.
    """
    model = _MODELS[entity_type]
    # Dedupe losers and never let the survivor merge into itself.
    loser_ids = [lid for lid in dict.fromkeys(loser_ids) if lid != survivor_id]
    if not loser_ids:
        raise ValueError("no_losers")

    needed = [survivor_id, *loser_ids]
    found = set(
        (
            await db.execute(
                select(model.id).where(model.organization_id == org_id, model.id.in_(needed))
            )
        )
        .scalars()
        .all()
    )
    if survivor_id not in found:
        raise LookupError("survivor")
    if any(lid not in found for lid in loser_ids):
        raise LookupError("loser")

    reparented: dict[str, int] = {}

    def _bump(table: str, n: int) -> None:
        if n:
            reparented[table] = reparented.get(table, 0) + n

    # Typed FK references.
    for ref_model, fk in _TYPED_FK_REFS[entity_type]:
        res = await db.execute(
            update(ref_model)
            .where(
                getattr(ref_model, fk).in_(loser_ids),
                ref_model.organization_id == org_id,
            )
            .values({fk: survivor_id})
        )
        _bump(ref_model.__tablename__, res.rowcount or 0)

    # Polymorphic references.
    for ref_model in _POLY_MODELS:
        res = await db.execute(
            update(ref_model)
            .where(
                ref_model.organization_id == org_id,
                ref_model.entity_type == entity_type,
                ref_model.entity_id.in_(loser_ids),
            )
            .values(entity_id=survivor_id)
        )
        _bump(ref_model.__tablename__, res.rowcount or 0)

    # Tags: re-parent with dedupe — the survivor must not end up with two
    # rows for the same tag (uq_entity_tag). Drop a loser's tag if the
    # survivor already has it (whether pre-existing or just moved from an
    # earlier loser), otherwise move it.
    tag_rows = (
        (
            await db.execute(
                select(EntityTag).where(
                    EntityTag.organization_id == org_id,
                    EntityTag.entity_type == entity_type,
                    EntityTag.entity_id.in_(needed),
                )
            )
        )
        .scalars()
        .all()
    )
    survivor_tag_ids = {t.tag_id for t in tag_rows if t.entity_id == survivor_id}
    moved = 0
    for tag in tag_rows:
        if tag.entity_id == survivor_id:
            continue
        if tag.tag_id in survivor_tag_ids:
            await db.delete(tag)
        else:
            tag.entity_id = survivor_id
            survivor_tag_ids.add(tag.tag_id)
            moved += 1
    _bump("entity_tags", moved)

    # Soft-delete the losers.
    await db.execute(
        update(model)
        .where(model.id.in_(loser_ids), model.organization_id == org_id)
        .values(deleted_at=datetime.now(UTC))
    )

    return MergeResult(
        survivor_id=survivor_id,
        merged_count=len(loser_ids),
        reparented=reparented,
    )
