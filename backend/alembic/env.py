"""Alembic environment for an **async** SQLAlchemy backend.

Strategy:
 - `sqlalchemy.url` is overridden at runtime from `app.config.get_settings()`
   so migrations always see the same DATABASE_URL as the live app. No risk
   of pointing migrations at a stale `alembic.ini` URL.
 - Importing `app.models` is what populates `Base.metadata` — alembic's
   `target_metadata` then has the full schema for `--autogenerate`.
 - The online path uses `async_engine_from_config` and runs the actual
   migrations via `connection.run_sync(do_run_migrations)`, which is the
   official pattern documented by Alembic for asyncpg.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app import models  # noqa: F401 — side-effect: registers ORM classes

# Models must be imported BEFORE we hand `Base.metadata` to alembic, so
# every mapped class registers itself on the metadata.
from app.config import get_settings
from app.database import Base

config = context.config

# Override the URL in alembic.ini (left blank on purpose) with the live
# app's DATABASE_URL. Single source of truth.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Render SQL to stdout without touching the database.

    Useful for code review or for pre-generating SQL bundles to ship to a
    DBA. `--sql` flag is the entry point.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Sync function the async engine hands a real connection to.

    `compare_type` and `compare_server_default` make autogenerate notice
    column type changes and default changes — without them, those diffs
    silently vanish.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
