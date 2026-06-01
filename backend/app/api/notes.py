"""Per-user markdown notes on Lead / Customer / Deal.

CRUD surface:
  * `POST   /api/notes`            create (and emit a `note_added` activity)
  * `GET    /api/notes?entity_type=&entity_id=` list by entity
  * `PATCH  /api/notes/{note_id}`  edit (author OR admin/manager only)
  * `DELETE /api/notes/{note_id}`  soft-delete (author OR admin/manager only)

Org-scoped via `get_current_org_id`. Notes inherit `SoftDeleteMixin`
so the global filter excludes deleted ones — the trash UI sees them
via the standard opt-out (not surfaced for notes today; follow-up).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.activities import ActivityType, record_activity
from app.audit import record_audit
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.models import Note, User
from app.schemas import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(prefix="/api/notes", tags=["notes"])

# Anchor to the same vocabulary the Activity timeline uses so a
# typo doesn't quietly silo notes from the rest of the entity view.
EntityType = Literal["lead", "customer", "deal"]


async def _get_note_or_404(
    db: AsyncSession, note_id: uuid.UUID, org_id: uuid.UUID
) -> Note:
    """Org-scoped fetch; raises 404 on miss (NOT 403 — same
    existence-leak rule as the rest of the CRUD layer)."""
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.organization_id == org_id)
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


def _serialize(note: Note, email: str | None, name: str | None) -> NoteOut:
    return NoteOut(
        id=note.id,
        entity_type=note.entity_type,
        entity_id=note.entity_id,
        body=note.body,
        author_user_id=note.author_user_id,
        author_name=name,
        author_email=email,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.get("", response_model=list[NoteOut])
async def list_notes(
    entity_type: EntityType,
    entity_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[NoteOut]:
    author = aliased(User)
    stmt = (
        select(Note, author.email, author.full_name)
        .outerjoin(author, author.id == Note.author_user_id)
        .where(
            Note.organization_id == org_id,
            Note.entity_type == entity_type,
            Note.entity_id == entity_id,
        )
        .order_by(desc(Note.created_at), desc(Note.id))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return [_serialize(n, e, na) for n, e, na in result.all()]


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> NoteOut:
    note = Note(
        organization_id=org_id,
        author_user_id=user.id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        body=payload.body,
    )
    db.add(note)
    await db.flush()

    # Timeline echo. Use the first ~80 chars of the body as the
    # activity `content` so the timeline previews the note without
    # rendering the whole markdown; the NotesPanel shows the full
    # body separately.
    preview = (
        payload.body[:80] + "…" if len(payload.body) > 80 else payload.body
    ).replace("\n", " ")
    await record_activity(
        db,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        activity_type=ActivityType.note_added,
        organization_id=org_id,
        actor=user,
        content=preview,
        metadata={"note_id": str(note.id)},
    )
    await record_audit(
        db,
        actor=user,
        action="note.create",
        entity_type="note",
        entity_id=note.id,
        organization_id=org_id,
        metadata={
            "target_entity_type": payload.entity_type,
            "target_entity_id": str(payload.entity_id),
        },
    )
    await db.commit()
    await db.refresh(note)
    # Return shape needs the author denorm — fetch via the same JOIN
    # the list query uses (cheaper than a second .refresh).
    return _serialize(note, user.email, user.full_name)


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> NoteOut:
    note = await _get_note_or_404(db, note_id, org_id)
    # Same ownership rule as Lead/Customer mutations: author OR
    # privileged role.
    ensure_can_mutate(user, note.author_user_id)
    note.body = payload.body
    await record_audit(
        db,
        actor=user,
        action="note.update",
        entity_type="note",
        entity_id=note.id,
        organization_id=org_id,
    )
    await db.commit()
    await db.refresh(note)
    # Author is the user we just authenticated — denorm directly.
    if note.author_user_id == user.id:
        return _serialize(note, user.email, user.full_name)
    # Edge case: admin edited someone else's note. Look up author.
    author = await db.get(User, note.author_user_id) if note.author_user_id else None
    return _serialize(
        note,
        author.email if author else None,
        author.full_name if author else None,
    )


# NOTE: no `-> None` annotation — combined with
# `from __future__ import annotations` FastAPI's introspection
# treats `None` as a JSON-serialisable response and refuses to
# register a 204 (which by spec must have no body). The other
# DELETE-204 endpoints in this codebase don't use future-
# annotations so they're unaffected.
@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    note = await _get_note_or_404(db, note_id, org_id)
    ensure_can_mutate(user, note.author_user_id)
    note.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="note.soft_delete",
        entity_type="note",
        entity_id=note.id,
        organization_id=org_id,
    )
    await db.commit()
