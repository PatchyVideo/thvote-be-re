"""Centralized application settings."""

from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    app_env: str = os.getenv("APP_ENV", "development")
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/dev.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings object."""
    return Settings()
