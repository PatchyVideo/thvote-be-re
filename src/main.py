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
from api.graphql.schema import schema as graphql_schema
from api.rest.v1 import api_router
from common.config import get_settings, reload_settings, nacos_config_change_callback
from common.database import get_db_session, init_db, reload_engine
from common.middleware.logging import LoggingMiddleware
from common.nacos import (
    register_service_to_nacos,
    deregister_service_from_nacos,
    discover_service_from_nacos,
    get_service_register,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    await init_db()
    logger.info("Database initialized")

    # Start Nacos config watcher for hot reload
    settings = get_settings()
    if settings.nacos_enabled:
        from common.nacos import start_nacos_watcher, stop_nacos_watcher

        start_nacos_watcher(on_change=nacos_config_change_callback)
        logger.info("Nacos config watcher started")

        # Register service to Nacos naming service
        svc = await register_service_to_nacos(
            server_addrs=settings.nacos_server_addrs,
            namespace=settings.nacos_namespace,
            service_name=settings.nacos_service_name,
            ip=settings.nacos_service_ip,
            port=settings.nacos_service_port,
            group=settings.nacos_group,
            cluster_name=settings.nacos_service_cluster,
            weight=settings.nacos_service_weight,
            username=settings.nacos_access_key,
            password=settings.nacos_secret_key,
        )
        logger.info(
            "Service registered to Nacos: %s @ %s:%s (cluster=%s, weight=%s)",
            settings.nacos_service_name,
            settings.nacos_service_ip,
            settings.nacos_service_port,
            settings.nacos_service_cluster,
            settings.nacos_service_weight,
        )
        # Store in app state for access in endpoints
        app.state.nacos_service_register = svc
    else:
        logger.info("Nacos config watcher disabled (NACOS_ENABLED=false)")

    yield

    # Shutdown
    if settings.nacos_enabled:
        from common.nacos import stop_nacos_watcher

        await deregister_service_from_nacos()
        await stop_nacos_watcher()
        logger.info("Nacos service deregistered and config watcher stopped")


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
        try:
            await db.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as e:
            logger.warning("Health check DB query failed: %s", e)
            db_status = "unavailable"
        return {
            "status": "ok",
            "db_status": db_status,
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

    # Service discovery endpoint
    @app.get("/admin/discover/{service_name}", tags=["admin"])
    async def discover_service(
        service_name: str,
        group: str | None = None,
        healthy_only: bool = False,
    ) -> dict:
        """
        从 Nacos 发现指定服务的实例列表。

        Args:
            service_name: Nacos 服务名
            group: 分组名，默认为配置的 NACOS_GROUP
            healthy_only: 是否只返回健康实例
        """
        settings = get_settings()
        group = group or settings.nacos_group

        instances = await discover_service_from_nacos(
            service_name=service_name,
            group=group,
            healthy_only=healthy_only,
            namespace=settings.nacos_namespace,
            server_addrs=settings.nacos_server_addrs,
            username=settings.nacos_access_key,
            password=settings.nacos_secret_key,
        )

        return {
            "service_name": service_name,
            "group": group,
            "healthy_only": healthy_only,
            "count": len(instances),
            "instances": [
                {
                    "ip": inst.ip,
                    "port": inst.port,
                    "healthy": inst.healthy,
                    "weight": inst.weight,
                    "cluster": inst.cluster_name,
                    "enabled": inst.enabled,
                    "metadata": inst.metadata,
                    "instance_id": inst.instance_id,
                }
                for inst in instances
            ],
        }

    # Self service discovery endpoint (discover this service)
    @app.get("/admin/discover-self", tags=["admin"])
    async def discover_self(healthy_only: bool = False) -> dict:
        """
        发现当前服务的所有实例。

        基于 NACOS_SERVICE_NAME 配置的服务名进行查询。
        """
        settings = get_settings()
        reg = get_service_register()
        if reg is None:
            return {
                "service_name": settings.nacos_service_name,
                "count": 0,
                "instances": [],
                "note": "Service not registered to Nacos (NACOS_ENABLED may be false)",
            }

        instances = await reg.discover(
            service_name=settings.nacos_service_name,
            group=settings.nacos_group,
            healthy_only=healthy_only,
        )

        return {
            "service_name": settings.nacos_service_name,
            "group": settings.nacos_group,
            "healthy_only": healthy_only,
            "count": len(instances),
            "instances": [
                {
                    "ip": inst.ip,
                    "port": inst.port,
                    "healthy": inst.healthy,
                    "weight": inst.weight,
                    "cluster": inst.cluster_name,
                    "enabled": inst.enabled,
                    "metadata": inst.metadata,
                    "instance_id": inst.instance_id,
                }
                for inst in instances
            ],
        }

    # REST API v1 endpoints
    app.include_router(api_router)

    # GraphQL endpoint (Strawberry)
    graphql_app = GraphQLRouter(graphql_schema)
    app.include_router(graphql_app, prefix="/graphql")

    return app


app = create_app()
