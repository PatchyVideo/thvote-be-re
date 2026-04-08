"""Logging bootstrap."""

import logging

from .config import get_settings


def setup_logging() -> None:
    """Initialize application logging once at startup."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
