"""FastAPI application factory for thvote-be-re."""

from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from .api.graphql.schema import schema as graphql_schema
from .api.rest.router import router as rest_router
from .common.errors import register_exception_handlers
from .common.lifespan import lifespan
from .common.logging import setup_logging


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    setup_logging()

    app = FastAPI(
        title="THVote Backend Rewrite",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(rest_router)
    app.include_router(GraphQLRouter(graphql_schema), prefix="/graphql")
    register_exception_handlers(app)
    return app


app = create_app()
