from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession,
                                    async_sessionmaker, create_async_engine)
from sqlalchemy.pool import NullPool

from src.common.config import get_settings


def normalize_async_database_url(raw_url: str) -> str:
    """Normalize DATABASE_URL to an async SQLAlchemy dialect+driver."""

    url: URL = make_url(raw_url)
    drivername = url.drivername

    if drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")
    elif drivername == "mysql":
        url = url.set(drivername="mysql+asyncmy")
    elif drivername == "sqlite":
        url = url.set(drivername="sqlite+aiosqlite")

    return url.render_as_string(hide_password=False)


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    normalized_url = normalize_async_database_url(settings.database_url)

    connect_args: dict = {}
    engine_kwargs: dict = {}

    if normalized_url.startswith("sqlite+aiosqlite:"):
        connect_args = {"check_same_thread": False}
        engine_kwargs["poolclass"] = NullPool

    return create_async_engine(
        normalized_url,
        echo=settings.database_echo,
        future=True,
        connect_args=connect_args,
        **engine_kwargs,
    )


engine: AsyncEngine = _create_engine()
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an `AsyncSession`."""

    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database schema (for dev/testing).

    In production, prefer Alembic migrations; this function can be
    used in tests or early development to create all tables.
    """
    from src.db_model.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
