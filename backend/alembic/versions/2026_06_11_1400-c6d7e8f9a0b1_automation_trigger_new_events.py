"""automation_trigger_new_events

Adds the three previously-missing event-family members to the native
`automationtrigger` enum so rules can be stored for them:

    customer_created — fires on POST /api/customers and lead conversion
    task_overdue     — fires from the worker's daily overdue-task sweep
    user_invited     — fires on invite create

The matching `EventType` members live in app/events.py; outbox rows
store the event type as a plain string column, so only the rules
table's enum needs DDL.

ADD VALUE is transaction-safe on PG12+ as long as the new value isn't
USED in the same transaction — this migration only adds. Downgrade is
a no-op: Postgres cannot drop enum values, and stray members are
harmless (no rule rows reference them after an app rollback).

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-06-11 14:00:00.000000+00:00
"""

from alembic import op

revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE automationtrigger ADD VALUE IF NOT EXISTS 'customer_created'")
    op.execute("ALTER TYPE automationtrigger ADD VALUE IF NOT EXISTS 'task_overdue'")
    op.execute("ALTER TYPE automationtrigger ADD VALUE IF NOT EXISTS 'user_invited'")


def downgrade() -> None:
    pass
