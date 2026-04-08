"""Database engine and session helpers."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ..config import get_settings
from .base import Base


def normalize_async_database_url(raw_url: str) -> str:
    """Normalize a sync SQLAlchemy URL to an async driver URL."""
    url: URL = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")
    elif url.drivername == "mysql":
        url = url.set(drivername="mysql+asyncmy")
    elif url.drivername == "sqlite":
        url = url.set(drivername="sqlite+aiosqlite")
    return url.render_as_string(hide_password=False)


@lru_cache
def get_engine() -> AsyncEngine:
    """Create a cached async SQLAlchemy engine."""
    settings = get_settings()
    normalized_url = normalize_async_database_url(settings.database_url)

    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {}
    if normalized_url.startswith("sqlite+aiosqlite:"):
        connect_args["check_same_thread"] = False
        engine_kwargs["poolclass"] = NullPool

    return create_async_engine(
        normalized_url,
        echo=settings.database_echo,
        future=True,
        connect_args=connect_args,
        **engine_kwargs,
    )


SessionLocal = async_sessionmaker(
    bind=get_engine(),
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async SQLAlchemy session for request handlers."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Create tables in local dev mode before Alembic is adopted."""
    from ...models.orm import raw_submit  # noqa: F401

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
