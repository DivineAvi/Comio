"""Alembic environment configuration.

This file tells Alembic:
1. How to connect to the database
2. Where to find your models (so it can auto-detect changes)
3. How to run migrations (sync vs async)
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import our app config to get the database URL
from apps.api.config import settings

# Import Base and ALL models — this is critical!
# Alembic reads Base.metadata to know what tables should exist.
# If a model isn't imported here, Alembic won't generate migrations for it.
from apps.api.models import (  # noqa: F401 — imported for side effects
    User,
    Project,
    Sandbox,
    ChatSession,
    ChatMessage,
    Incident,
    Diagnosis,
    Remediation,
    Deployment,
    AuditLog,
)
from apps.api.database import Base

# Alembic Config object — provides access to alembic.ini values
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object that Alembic uses to compare models vs database.
# It knows about every table because we imported all models above.
target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from our app settings."""
    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This generates the SQL without connecting to the database.
    Useful for reviewing what SQL would be executed, or generating
    migration scripts for a DBA to review.

    Usage: alembic upgrade head --sql
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations using the given database connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine.

    We use asyncpg (async Postgres driver), so we need an async
    engine here. This connects to the real database and applies changes.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Don't use connection pooling for migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — wraps the async function."""
    asyncio.run(run_async_migrations())


# Decide which mode to run based on whether we're generating SQL or applying it
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
