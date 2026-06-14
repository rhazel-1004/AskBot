"""Alembic migration environment for AskBot.

Resolves the target database from the SAME source as the running app
(`database.db.get_database_url`), so migrations apply to SQLite locally and to
PostgreSQL in production purely off the DATABASE_URL environment variable —
no per-environment editing of alembic.ini, and no secrets committed to the repo.

`target_metadata` is wired to the app's declarative Base (with every model
imported) so `alembic revision --autogenerate` produces correct diffs for both
backends.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- App wiring ------------------------------------------------------------ #
# Import the shared URL resolver and metadata. Importing the models registers
# every table on Base.metadata so autogenerate sees the full schema.
from database.db import Base, get_database_url, is_sqlite_url
from database import (  # noqa: F401  (imported for metadata side effects)
    models,
    models_subscription,
    models_webhook,
    models_checkout,
    models_question_draft,
    models_email_idempotency,
    models_app_setting,
)

config = context.config

# Inject the resolved URL (env-driven) so both offline and online modes use it.
DATABASE_URL = get_database_url()
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _render_as_batch() -> bool:
    """SQLite cannot ALTER columns in place — batch mode rewrites the table.

    Enabled only for SQLite so PostgreSQL keeps using native, transactional
    ALTERs.
    """
    return is_sqlite_url(DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_render_as_batch(),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_render_as_batch(),
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
