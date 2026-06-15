"""grant crm_app on fx_rates + llm_usage (prod outage fix)

The runtime role `crm_app` (NOBYPASSRLS) was created without grants on
`fx_rates` (c4d5e6f7a8b9) and `llm_usage` (e7c8d9a0b1f2) in production: the
`ALTER DEFAULT PRIVILEGES FOR ROLE crm` set in f5fde59e0dc8 only auto-grants
tables CREATED BY crm, and on the prod deploy these two were created under a
different owner — so every authed read of them (dashboard/stats, /fx/rates,
/llm-usage/summary, /performance/summary) raised "permission denied" → 500.

This GRANT is idempotent: a no-op on environments where the default
privileges already covered the tables (dev/CI), and the durable fix for prod
and any fresh deploy / staging / disaster-recovery restore.

Guidance for future table-creating migrations: do NOT rely on default
privileges — add an explicit `GRANT ... TO crm_app` (the runtime role can't
be assumed to inherit access).

Revision ID: d3c4b5a6e7f8
Revises: f8a9b0c1d2e3
Create Date: 2026-06-15 15:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "d3c4b5a6e7f8"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE fx_rates, llm_usage TO crm_app;")


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE fx_rates, llm_usage FROM crm_app;")
