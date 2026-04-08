"""Application lifespan hooks."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from .database import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown hooks for the application."""
    logger.info("Starting thvote-be-re application")
    await init_db()
    yield
    logger.info("Stopping thvote-be-re application")
