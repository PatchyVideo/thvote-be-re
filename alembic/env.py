"""Alembic migration environment.

Reads DATABASE_URL from src.common.config (which itself loads .env / Nacos
overrides) and uses src.db_model.Base.metadata as the autogenerate target.
"""

from __future__ import annotations

import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.engine import Connection

from src.common.config import get_settings
from src.common.database import normalize_async_database_url
from src.db_model import Base  # noqa: F401  (registers all models with Base.metadata)

logger = logging.getLogger("alembic.env")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option(
    "sqlalchemy.url", normalize_async_database_url(settings.database_url)
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate migration SQL without a live database connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# Sentinel tables for each migration revision.
# If `alembic_version` is missing but the sentinel exists, the DB is already
# at that revision and we baseline by writing alembic_version directly,
# avoiding CREATE TABLE conflicts on first run against legacy init_db()
# create_all schemas.
_SENTINELS = (
    ("0002", "raw_character"),   # voting tables (B-001)
    ("0001", "user"),            # user + activity_log
)


def _maybe_baseline_existing_schema(connection: Connection) -> None:
    """Auto-stamp existing pre-Alembic schemas so `upgrade head` is idempotent.

    Triggers only when alembic_version is missing AND at least one of our
    managed tables exists. Fresh DBs hit neither condition and go through
    the normal upgrade flow. Once stamped, future migrations work normally.
    """
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())

    if "alembic_version" in existing:
        return

    target_rev = next((rev for rev, table in _SENTINELS if table in existing), None)
    if target_rev is None:
        return  # genuinely fresh DB

    logger.warning(
        "Existing schema detected (no alembic_version, but %s exists); "
        "auto-stamping to %s. This runs once per legacy deployment.",
        next(t for r, t in _SENTINELS if r == target_rev),
        target_rev,
    )
    connection.execute(
        text(
            "CREATE TABLE alembic_version ("
            "  version_num VARCHAR(32) NOT NULL,"
            "  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
            ")"
        )
    )
    connection.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
        {"rev": target_rev},
    )
    connection.commit()


def do_run_migrations(connection: Connection) -> None:
    _maybe_baseline_existing_schema(connection)
    # The shim above runs inspect()/SELECTs which, in SQLAlchemy 2.0
    # "commit-as-you-go" mode, leave an open (read-only) transaction on the
    # connection when alembic_version already exists (early return). If left
    # open, alembic's begin_transaction() sees an in-progress transaction it
    # does not own and therefore does NOT commit on exit — so the whole upgrade
    # rolls back on connection close (migrations run, exit 0, but never persist).
    # Clear it so begin_transaction() owns and commits its own transaction.
    if connection.in_transaction():
        connection.rollback()
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live async database connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        future=True,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
