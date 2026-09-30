"""Alembic environment configured for asyncpg and application metadata."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import load_settings
from app.db import models as _models  # noqa: F401
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = load_settings()
database_url = settings.database_url.get_secret_value().replace("%", "%%")
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def migration_options() -> dict[str, object]:
    """Return consistent comparison options for online and offline runs."""
    return {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "include_schemas": False,
    }


def run_migrations_offline() -> None:
    """Emit SQL without opening a database connection."""
    context.configure(
        url=database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **migration_options(),
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run synchronous Alembic operations on an adapted async connection."""
    context.configure(connection=connection, **migration_options())

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create a disposable async engine and execute migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against the configured PostgreSQL database."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
