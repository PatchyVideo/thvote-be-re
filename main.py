from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from config import get_settings
from database import get_db_session, init_db
from app_router import login as login_router
from app_router import submit as submit_router


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="THVote FastAPI Backend",
        version="0.1.0",
    )

    # CORS middleware – keep permissive for now; can be tightened later.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check / server time style endpoint.
    @app.get("/health", tags=["system"])
    async def health(db: AsyncSession = Depends(get_db_session)) -> dict:
        # DB ping to validate connectivity across postgres/mysql/sqlite.
        await db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "vote_year": settings.vote_year,
        }

    # Router registration (user manager, will expand with more routers later).
    app.include_router(login_router.router)
    app.include_router(submit_router.router)

    @app.on_event("startup")
    async def on_startup() -> None:  # pragma: no cover - side-effect only
        # For early development we auto-create tables.
        # In real deployments prefer Alembic migrations instead.
        await init_db()

    return app


app = create_app()

