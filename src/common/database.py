from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.common.config import get_settings, reload_settings

logger = logging.getLogger(__name__)


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


def _create_engine(database_url: str, echo: bool = False) -> AsyncEngine:
    """Create a new async engine with the given database URL."""
    normalized_url = normalize_async_database_url(database_url)
    settings = get_settings()
    db_settings = settings.database

    connect_args: dict = {}
    engine_kwargs: dict = {}

    if normalized_url.startswith("sqlite+aiosqlite:"):
        connect_args = {"check_same_thread": False}
        engine_kwargs["poolclass"] = NullPool
    else:
        # 配置连接池
        engine_kwargs["pool_size"] = db_settings.db_pool_size
        engine_kwargs["max_overflow"] = db_settings.db_max_overflow
        engine_kwargs["pool_timeout"] = db_settings.db_pool_timeout
        engine_kwargs["pool_recycle"] = db_settings.db_pool_recycle

    return create_async_engine(
        normalized_url,
        echo=echo,
        future=True,
        connect_args=connect_args,
        **engine_kwargs,
    )


def _create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a new session maker bound to the given engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# 动态引擎管理
_current_engine: AsyncEngine | None = None
_current_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Get or create the current database engine."""
    global _current_engine
    if _current_engine is None:
        settings = get_settings()
        _current_engine = _create_engine(
            settings.database.build_url(),
            echo=settings.database.db_echo,
        )
    return _current_engine


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the current session maker."""
    global _current_session_maker, _current_engine
    if _current_session_maker is None or _current_engine is None:
        _current_engine = _get_engine()
        _current_session_maker = _create_session_maker(_current_engine)
    return _current_session_maker


def get_engine() -> AsyncEngine:
    """Get the current database engine."""
    return _get_engine()


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get the current session maker."""
    return _get_session_maker()


async def reload_engine() -> AsyncEngine:
    """
    Reload the database engine with new settings.

    当 Nacos 配置变更时调用此方法重新创建数据库连接。
    """
    global _current_engine, _current_session_maker

    # 重新加载配置
    reload_settings()
    settings = get_settings()
    new_url = settings.database.build_url()

    # 关闭旧引擎
    if _current_engine is not None:
        old_engine = _current_engine
        _current_engine = None
        _current_session_maker = None
        logger.info("Closing old database engine...")
        await old_engine.dispose()

    # 创建新引擎
    _current_engine = _create_engine(new_url, echo=settings.database.db_echo)
    _current_session_maker = _create_session_maker(_current_engine)

    # 隐藏密码显示
    safe_url = new_url.replace("//", "//***@") if "@" in new_url else new_url
    logger.info("Database engine reloaded with URL: %s", safe_url)
    return _current_engine


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession.

    Uses the current engine, which can be reloaded via reload_engine().
    """
    session_maker = _get_session_maker()
    async with session_maker() as session:
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

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
