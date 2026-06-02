import uuid
from collections.abc import AsyncGenerator
from contextvars import ContextVar

from sqlalchemy import event
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


# ---------- Transaction-scoped tenant GUC ----------
# RLS policies read `app.current_org_id`. This MUST be applied as a
# transaction-local setting (`set_config(..., true)` == SET LOCAL),
# not a session/connection-level one, because:
#   1. Routes commit mid-request. A connection-scoped GUC survives the
#      commit on *that* connection, but `commit()` releases the
#      connection back to the pool. The post-commit readback (e.g.
#      `_get_quote_or_404`, `db.refresh()`) reacquires a possibly
#      DIFFERENT pooled connection — one with no GUC (→ 404/empty) or,
#      worse, another tenant's GUC (→ cross-tenant data leak). A
#      concurrent repro showed 7/10 requests reading back the wrong org.
#   2. A transaction-local GUC auto-clears at COMMIT/ROLLBACK, so it can
#      never leak across pooled connections to a later request.
#
# Because SET LOCAL is wiped at every commit, we must re-apply it at the
# start of *every* transaction. The request stashes its org in a
# ContextVar (task-local, so isolated per request); the `begin` event
# below re-reads it whenever SQLAlchemy opens a new DBAPI transaction
# (including the autobegin after a mid-request commit). SQLAlchemy's
# greenlet bridge copies the contextvars into the sync greenlet, so the
# handler sees the value set on the async request task.
current_org_id_ctx: ContextVar[str | None] = ContextVar("current_org_id", default=None)


def set_current_org_id(org_id: uuid.UUID) -> None:
    """Stash the tenant for the current task (request OR worker job) so
    every transaction on that task re-applies the RLS GUC. Stored as a
    string; the source is always a validated `uuid.UUID`, so it is safe
    to inline into SQL."""
    current_org_id_ctx.set(str(org_id))


def register_org_guc(target_engine) -> None:
    """Attach the transaction-begin GUC re-application to an engine's
    sync_engine. Call once per engine. The FastAPI runtime engine is
    wired below; the Arq worker builds its own engine and calls this in
    its startup hook so background jobs get the same transaction-scoped
    tenant isolation (no reliance on connection-scoped GUCs lingering on
    pooled connections between jobs)."""

    @event.listens_for(target_engine.sync_engine, "begin")
    def _apply_org_guc(conn):
        org = current_org_id_ctx.get()
        if org:
            # `org` is str(uuid.UUID) — no injection surface, so inlining
            # is safe and sidesteps asyncpg paramstyle quirks here.
            conn.exec_driver_sql(f"SELECT set_config('app.current_org_id', '{org}', true)")


register_org_guc(engine)


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
            # The org GUC is now transaction-local (see
            # `_apply_org_guc`), so it auto-clears at every commit /
            # rollback and can't leak across pooled connections — no
            # connection-level wipe needed. Reset the ContextVar so a
            # later coroutine reusing this task's context starts with no
            # implicit tenant.
            current_org_id_ctx.set(None)
