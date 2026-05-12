# Common module - shared utilities, middleware, and configuration

from src.common.config import get_settings
from src.common.database import get_db_session

settings = get_settings()

__all__ = ["settings", "get_db_session"]
