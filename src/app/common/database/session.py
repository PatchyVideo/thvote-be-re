"""Database engine and session helpers."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..config import get_settings


@lru_cache
def get_engine():
    """Create a cached SQLAlchemy engine."""
    settings = get_settings()
    return create_engine(settings.database_url, future=True)


SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)
