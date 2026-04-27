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

# Configure logging level from environment
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter

from .api.graphql.schema import schema as graphql_schema
from .api.rest.v1 import api_router
from .common.apollo import load_apollo_overrides
from .common.config import get_settings
from .common.database import get_db_session, init_db
from .common.middleware.logging import LoggingMiddleware
from .common.redis import close_redis


_TRUTHY = {"1", "true", "yes", "on"}


def _is_debug_mode() -> bool:
    """Whether the app should auto-create tables on startup.

    Production / test deployments rely on Alembic migrations
    (`alembic upgrade head` in the CI deploy step) and MUST NOT call
    `init_db()` — running `Base.metadata.create_all` alongside Alembic
    risks creating tables out of sync with `alembic_version`, leaving
    the schema in a state Alembic cannot reconcile.

    Local developers who want the old "first-run create_all" ergonomics
    can opt in with ``DEBUG=true`` (or ``APP_DEBUG``).
    """
    raw = os.getenv("DEBUG") or os.getenv("APP_DEBUG") or "false"
    return raw.strip().lower() in _TRUTHY


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    if _is_debug_mode():
        await init_db()
        logger.warning(
            "DEBUG=true: ran Base.metadata.create_all(); production must use "
            "`alembic upgrade head` instead, see docs/operations/cicd-pipeline.md"
        )
    else:
        logger.info(
            "Skipping init_db(); schema is owned by Alembic. "
            "Set DEBUG=true to enable create_all for local development."
        )

    # Load Apollo config
    apollo_config = load_apollo_overrides()
    if apollo_config:
        logger.info("Apollo config loaded: %d values", len(apollo_config))
        logger.debug("Apollo config keys: %s", list(apollo_config.keys()))
    else:
        logger.info("Apollo config not loaded (APOLLO_ENABLED=false or no namespaces)")

    yield
    # Shutdown
    await close_redis()


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

    # REST API v1 endpoints
    app.include_router(api_router)

    # GraphQL endpoint (Strawberry)
    graphql_app = GraphQLRouter(graphql_schema)
    app.include_router(graphql_app, prefix="/graphql")

    return app


app = create_app()
