"""create_crm_app_runtime_role — make RLS actually enforce

Phase 6 follow-up. The previous migration enabled `FORCE ROW LEVEL
SECURITY` on tenant tables, but `crm` (the role both the app and
Alembic use) is the postgres bootstrap superuser — both SUPERUSER and
BYPASSRLS silently bypass RLS regardless of FORCE. So policies were
dormant.

Postgres protects the bootstrap superuser ("The bootstrap user must
have the SUPERUSER attribute"), so we can't simply strip it. Instead
we adopt the textbook two-role split:

  * `crm` — bootstrap superuser, owns all tables. Used ONLY by Alembic
    for migrations (DDL bypasses RLS naturally; data backfills can
    use it without surprises).
  * `crm_app` — regular LOGIN role, NOSUPERUSER NOBYPASSRLS, with
    table-level SELECT/INSERT/UPDATE/DELETE grants. Used by the
    FastAPI process at runtime. RLS policies are enforced.

The migration grants `crm_app` SELECT/INSERT/UPDATE/DELETE on every
current table and sets ALTER DEFAULT PRIVILEGES so future tables
created by `crm` get the same grants automatically.

After this migration the operator must:
  1. Update `.env` to add `APP_DATABASE_URL=postgresql+asyncpg://crm_app:...@db:5432/crm`
  2. Restart backend so the connection pool reconnects as `crm_app`

Password is `crm_app_dev_2026` — fine for docker dev, MUST be rotated
for any deployment outside the developer machine.

Revision ID: f5fde59e0dc8
Revises: ca1013e5bde6
Create Date: 2026-05-30 19:54:31.682491+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f5fde59e0dc8"
down_revision: Union[str, None] = "ca1013e5bde6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables crm_app needs full CRUD on. We grant via "ALL TABLES IN SCHEMA"
# below — listing them here only for documentation. Future tables get
# the grant via ALTER DEFAULT PRIVILEGES.
RUNTIME_TABLES = (
    "users", "organizations", "org_memberships", "org_invites",
    "leads", "customers", "deals", "tasks",
    "audit_logs", "stripe_events",
)


def upgrade() -> None:
    # Portability: in docker-compose the bootstrap superuser is `crm`
    # (POSTGRES_USER=crm), so the role already exists. On a managed
    # Postgres (Railway / Scaleway / RDS) the bootstrap role is
    # different (e.g. `postgres`), so `crm` must exist for the
    # `ALTER DEFAULT PRIVILEGES ... FOR ROLE crm` statements below to be
    # valid. Idempotent — a no-op wherever `crm` already exists. On a
    # managed DB the tables end up owned by the bootstrap role, not
    # `crm`, but each migration also issues explicit
    # `GRANT ... TO crm_app`, so the runtime role's access does not
    # depend on these default-privilege rules.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm') THEN
            CREATE ROLE crm;
          END IF;
        END
        $$;
        """
    )

    # Create crm_app role idempotently. Password is fine for local dev;
    # the docker-compose network isolates Postgres from the host
    # network anyway.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_app') THEN
            CREATE ROLE crm_app
              WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
              PASSWORD 'crm_app_dev_2026';
          END IF;
        END
        $$;
        """
    )

    # Schema access. crm_app needs USAGE to reach the objects in public
    # and SELECT on the schema itself for some introspection.
    op.execute("GRANT USAGE ON SCHEMA public TO crm_app;")

    # CRUD on every existing table + sequence (for SERIAL/IDENTITY).
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON ALL TABLES IN SCHEMA public TO crm_app;"
    )
    op.execute(
        "GRANT USAGE, SELECT, UPDATE "
        "ON ALL SEQUENCES IN SCHEMA public TO crm_app;"
    )

    # ALTER DEFAULT PRIVILEGES applies only to objects created BY THE
    # SPECIFIED ROLE (crm here) AFTER this statement runs. Without
    # this, future migrations create tables owned by crm that crm_app
    # has no grants on — silent breakage. The `FOR ROLE crm` clause
    # is critical: it scopes the default to objects crm creates.
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE crm IN SCHEMA public
          GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO crm_app;
        """
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE crm IN SCHEMA public
          GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO crm_app;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE crm IN SCHEMA public
          REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM crm_app;
        """
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE crm IN SCHEMA public
          REVOKE USAGE, SELECT, UPDATE ON SEQUENCES FROM crm_app;
        """
    )
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM crm_app;")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM crm_app;")
    op.execute("REVOKE USAGE ON SCHEMA public FROM crm_app;")
    op.execute("DROP ROLE IF EXISTS crm_app;")
