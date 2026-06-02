"""Shared SQLAlchemy mixins.

Lives in its own module to break the otherwise-circular import:
`app.models` needs the mixins to declare its tables, and
`app.database` needs the mixin classes to register the global
`do_orm_execute` filter — but `app.models` also imports `Base` from
`app.database`, so having `database.py` import from `models.py`
creates a circle. Keeping the mixin here lets BOTH modules import it
without depending on each other.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """Marker mixin: tables that inherit this get a `deleted_at` column
    AND are auto-excluded from SELECTs unless the caller explicitly
    opts in via `session.execute(stmt.execution_options(include_deleted=True))`.

    The global filter is wired in `database.py` via SQLAlchemy's
    `do_orm_execute` event + `with_loader_criteria` — see that file
    for the mechanism. Trash endpoints (list / restore / purge) are
    the only callers that need to see soft-deleted rows; everything
    else gets the filter for free and no longer needs the repetitive
    `.where(Model.deleted_at.is_(None))` clause.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
