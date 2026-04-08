"""Dependency helpers for API layers."""

from .config import Settings, get_settings


def get_app_settings() -> Settings:
    """Expose cached settings for FastAPI dependency injection."""
    return get_settings()
