"""Postgres refresh-token sessions for deploys without Redis.

Revision ID: c0ffee11d3e0
Revises: d3c4b5a6e7f8
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c0ffee11d3e0"
down_revision: Union[str, None] = "d3c4b5a6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE auth_refresh_sessions (
            token_hash text PRIMARY KEY,
            user_id text NOT NULL,
            session_id text NOT NULL UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_seen_at timestamptz NOT NULL DEFAULT now(),
            user_agent text NOT NULL DEFAULT '',
            ip_address text NOT NULL DEFAULT '',
            expires_at timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_auth_refresh_sessions_user ON auth_refresh_sessions (user_id)")
    op.execute(
        """
        CREATE TABLE auth_refresh_tombstones (
            token_hash text PRIMARY KEY,
            user_id text NOT NULL,
            expires_at timestamptz NOT NULL
        )
        """
    )
    op.execute("ALTER TABLE auth_refresh_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auth_refresh_sessions FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auth_refresh_tombstones ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auth_refresh_tombstones FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY auth_refresh_sessions_all ON auth_refresh_sessions
            FOR ALL USING (true) WITH CHECK (true)
        """
    )
    op.execute(
        """
        CREATE POLICY auth_refresh_tombstones_all ON auth_refresh_tombstones
            FOR ALL USING (true) WITH CHECK (true)
        """
    )
    op.execute("REVOKE ALL ON auth_refresh_sessions FROM PUBLIC")
    op.execute("REVOKE ALL ON auth_refresh_tombstones FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON auth_refresh_sessions TO crm_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON auth_refresh_tombstones TO crm_app;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON auth_refresh_sessions FROM anon;
            REVOKE ALL ON auth_refresh_tombstones FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON auth_refresh_sessions FROM authenticated;
            REVOKE ALL ON auth_refresh_tombstones FROM authenticated;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_refresh_tombstones;")
    op.execute("DROP TABLE IF EXISTS auth_refresh_sessions;")
