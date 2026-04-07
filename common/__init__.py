# Common module - shared utilities, middleware, and configuration
from common.config import settings
from common.database import get_db_session

__all__ = ["settings", "get_db_session"]
