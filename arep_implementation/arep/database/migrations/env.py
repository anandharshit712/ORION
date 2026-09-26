"""
Alembic migration environment.  [Phase 1]

Connects to the database and runs migrations.
Supports both offline (SQL script generation) and online (live DB) modes.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Import all models so Alembic can detect schema changes
from arep.database.models import Base  # noqa: F401

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment variable if set.
#
# Through pin_postgres_driver, not raw, so migrations resolve the same DBAPI the
# application does. Reading the variable directly is how the Postgres CI job
# ended up on a driver nobody installed when SQLAlchemy 2.1 changed what a bare
# `postgresql://` means.
from arep.config.validate import pin_postgres_driver  # noqa: E402

db_url = os.environ.get("ORION_DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", pin_postgres_driver(db_url))

# Interpret the config file for Python logging
if config.config_file_name is not None:
    # disable_existing_loggers=False, which is not the default. fileConfig
    # otherwise switches off every logger configured before it, and alembic's
    # env.py runs inside whatever process invoked it. Under pytest that meant
    # any test running after a migration silently stopped capturing log output
    # and its assertions about warnings failed - a failure that points at the
    # test rather than at the migration that caused it. In production it would
    # mute the application's own logging for anything that ran migrations in
    # process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL script without DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to DB and applies changes."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
