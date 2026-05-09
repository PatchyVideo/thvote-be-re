from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv

# Load .env first so LOG_LEVEL can be set before logging.config
load_dotenv(override=False)

import logging

# Configure logging level from environment
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter

from .api.graphql.schema import schema as graphql_schema
from .api.rest.v1 import api_router
from .common.config import get_settings, reload_settings, nacos_config_change_callback
from .common.database import get_db_session, init_db, reload_engine
from .common.middleware.logging import LoggingMiddleware
from .common.nacos import start_nacos_watcher, stop_nacos_watcher


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    await init_db()
    logger.info("Database initialized")

    # Start Nacos config watcher for hot reload
    settings = get_settings()
    if settings.nacos_enabled:
        start_nacos_watcher(on_change=nacos_config_change_callback)
        logger.info("Nacos config watcher started")
    else:
        logger.info("Nacos config watcher disabled (NACOS_ENABLED=false)")

    yield

    # Shutdown
    await stop_nacos_watcher()
    logger.info("Nacos config watcher stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="THVote FastAPI Backend",
        version="0.2.1",
        lifespan=lifespan,
    )

    # Logging middleware
    app.add_middleware(LoggingMiddleware)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get("/health", tags=["system"])
    async def health(db: AsyncSession = Depends(get_db_session)) -> dict:
        await db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "vote_year": settings.vote_year,
        }

    # Reload settings endpoint (for hot reload testing)
    @app.post("/admin/reload-config", tags=["admin"])
    async def reload_config() -> dict:
        """
        重新加载配置。

        从 Nacos 获取最新配置并更新环境变量。
        同时重新创建数据库连接池。
        """
        new_settings = reload_settings()
        await reload_engine()
        return {
            "status": "ok",
            "message": "Configuration and database engine reloaded",
            "database_url": new_settings.database.db_host + ":" + str(new_settings.database.db_port),
            "database_name": new_settings.database.db_name,
            "vote_year": new_settings.vote_year,
        }

    # REST API v1 endpoints
    app.include_router(api_router)

    # GraphQL endpoint (Strawberry)
    graphql_app = GraphQLRouter(graphql_schema)
    app.include_router(graphql_app, prefix="/graphql")

    return app


app = create_app()
