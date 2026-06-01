from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, with_loader_criteria

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.runtime_database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


# ---------- Soft-delete global filter ----------
# Auto-exclude soft-deleted rows from every SELECT against entities
# that inherit `SoftDeleteMixin`. Replaces ~12 hand-written
# `.where(Model.deleted_at.is_(None))` clauses scattered across
# the API layer. Trash endpoints (which need to LIST deleted rows)
# opt out per-query via `stmt.execution_options(include_deleted=True)`.
#
# The listener is registered on the synchronous Session class
# because `do_orm_execute` fires from the sync-greenlet wrapper that
# the async session uses. `with_loader_criteria(SoftDeleteMixin, …)`
# filters every mapper whose class is-a SoftDeleteMixin, including
# relationship-load joins (`include_aliases=True`).


# Import the mixin from its own module (not app.models) to avoid the
# circular import: models.py imports Base from this file, so we
# can't reach into models.py during this module's initialisation.
from app.mixins import SoftDeleteMixin  # noqa: E402


@event.listens_for(Session, "do_orm_execute")
def _filter_soft_deleted(state):
    if not state.is_select:
        return
    if state.execution_options.get("include_deleted", False):
        return
    state.statement = state.statement.options(
        with_loader_criteria(
            SoftDeleteMixin,
            lambda cls: cls.deleted_at.is_(None),
            include_aliases=True,
        )
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            # Phase 6 RLS hygiene: clear the per-session GUC set by
            # `get_current_org_id` so the next request that picks up
            # this pooled connection starts with no implicit org
            # context. The active request always sets it explicitly
            # before any tenant-table query, so wiping here is
            # belt-and-suspenders.
            try:
                await session.execute(text("SELECT set_config('app.current_org_id', '', false)"))
                await session.commit()
            except Exception as e:
                # If the session is already in a broken state (e.g.
                # rolled back by an earlier error), the reset is
                # best-effort. Log so we notice if it happens often;
                # the pool may discard the connection anyway, and any
                # next request will overwrite the GUC.
                import logging

                logging.getLogger(__name__).warning("rls_guc_cleanup_failed: %s", e)
