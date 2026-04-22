"""Dependency injection container configuration."""

from typing import AsyncGenerator

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.config import get_settings
from src.common.database import get_db_session, get_engine, get_session_maker


class DatabaseContainer(containers.DeclarativeContainer):
    """Container for database-related dependencies."""

    engine = providers.Singleton(get_engine)
    session_factory = providers.Singleton(get_session_maker)

    db_session = providers.Factory[AsyncGenerator[AsyncSession, None]](get_db_session)


class SettingsContainer(containers.DeclarativeContainer):
    """Container for application settings."""

    settings = providers.Singleton(get_settings)


class Container(containers.DeclarativeContainer):
    """Main application container that wires all dependencies."""

    # Settings
    settings = providers.Singleton(get_settings)

    # Database
    engine = providers.Singleton(get_engine)
    session_factory = providers.Singleton(get_session_maker)

    # Wiring for async session dependency
    db = providers.Factory[AsyncGenerator[AsyncSession, None]](get_db_session)


# Global container instance
container = Container()
