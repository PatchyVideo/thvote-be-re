"""
Nacos 配置中心官方 SDK 客户端模块

使用官方 nacos-sdk-python v3 库连接 Nacos 2.x
文档: https://nacos.io/docs/latest/manual/user/python-sdk/usage/
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class NacosConfigClient:
    """
    Nacos 配置中心客户端 (基于官方 nacos-sdk-python v3)

    支持:
    - 获取配置 get_config
    - 发布配置 publish_config
    - 删除配置 remove_config
    - 配置监听 add_config_watcher
    """

    def __init__(
        self,
        server_addresses: str,
        namespace: str = "",
        group: str = "DEFAULT_GROUP",
        username: Optional[str] = None,
        password: Optional[str] = None,
        ak: Optional[str] = None,
        sk: Optional[str] = None,
        log_level: Optional[str] = None,
    ):
        """
        初始化 Nacos 客户端

        Args:
            server_addresses: Nacos 服务器地址，支持多服务器逗号分隔
            namespace: 命名空间 ID
            group: 配置分组，默认 DEFAULT_GROUP
            username: 用户名 (用于鉴权)
            password: 密码 (用于鉴权)
            ak: Access Key (阿里云 RAM 鉴权)
            sk: Secret Key (阿里云 RAM 鉴权)
            log_level: 日志级别
        """
        self.namespace = namespace
        self.group = group

        # v3 SDK 使用 v2.nacos 模块
        from v2.nacos import ClientConfigBuilder, NacosConfigService, GRPCConfig

        # 构建客户端配置
        builder = ClientConfigBuilder()
        builder.server_address(server_addresses)

        if namespace:
            builder.namespace_id(namespace)

        if username and password:
            builder.username(username)
            builder.password(password)
        elif ak and sk:
            builder.access_key(ak)
            builder.secret_key(sk)

        if log_level:
            builder.log_level(log_level)
        else:
            builder.log_level("WARNING")

        # 配置 gRPC 超时
        builder.grpc_config(GRPCConfig(grpc_timeout=5000))

        self._client_config = builder.build()
        self._service: Optional[Any] = None
        self._config_service_class = NacosConfigService

        logger.info(
            "Nacos client initialized: servers=%s, namespace=%s, group=%s",
            server_addresses,
            namespace,
            group,
        )

    async def _get_service(self):
        """获取或创建配置服务实例"""
        if self._service is None:
            self._service = await self._config_service_class.create_config_service(self._client_config)
        return self._service

    async def get_config(self, data_id: str, group: Optional[str] = None) -> Optional[str]:
        """获取配置"""
        if group is None:
            group = self.group

        try:
            service = await self._get_service()
            from v2.nacos import ConfigParam

            content = await service.get_config(
                ConfigParam(data_id=data_id, group=group)
            )
            if content:
                logger.debug(
                    "Config fetched: dataId=%s, group=%s, content_len=%d",
                    data_id,
                    group,
                    len(content),
                )
            return content
        except Exception as exc:
            logger.warning("Failed to get config: dataId=%s, error=%s", data_id, exc)
            return None

    async def get_config_as_dict(
        self, data_id: str, group: Optional[str] = None
    ) -> dict[str, Any]:
        """获取配置并解析为字典，支持 JSON 和 Properties 格式"""
        content = await self.get_config(data_id, group)
        if not content:
            return {}

        content = content.strip()

        # 尝试解析 JSON
        if content.startswith("{"):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass

        # 解析 Properties 格式
        result: dict[str, Any] = {}
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("!"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip()
            elif ":" in line:
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip()

        return result

    async def publish_config(
        self, data_id: str, content: str, group: Optional[str] = None
    ) -> bool:
        """发布配置"""
        if group is None:
            group = self.group

        try:
            service = await self._get_service()
            from v2.nacos import ConfigParam

            result = await service.publish_config(
                ConfigParam(data_id=data_id, group=group, content=content)
            )
            logger.info("Config published: dataId=%s, group=%s, result=%s", data_id, group, result)
            return result is True or result is None
        except Exception as exc:
            logger.error("Failed to publish config: dataId=%s, error=%s", data_id, exc)
            return False

    async def remove_config(self, data_id: str, group: Optional[str] = None) -> bool:
        """删除配置"""
        if group is None:
            group = self.group

        try:
            service = await self._get_service()
            from v2.nacos import ConfigParam

            result = await service.remove_config(
                ConfigParam(data_id=data_id, group=group)
            )
            logger.info("Config removed: dataId=%s, group=%s, result=%s", data_id, group, result)
            return result is True or result is None
        except Exception as exc:
            logger.error("Failed to remove config: dataId=%s, error=%s", data_id, exc)
            return False

    async def add_config_watcher(
        self, data_id: str, callback: Callable[[str], None], group: Optional[str] = None
    ) -> None:
        """添加配置监听器"""
        if group is None:
            group = self.group

        async def wrapped_callback(tenant: str, did: str, g: str, config: str) -> None:
            try:
                callback(config)
            except Exception as exc:
                logger.warning("Config watcher callback error: %s", exc)

        service = await self._get_service()
        await service.add_listener(data_id, group, wrapped_callback)
        logger.info(
            "Config watcher added: dataId=%s, group=%s",
            data_id,
            group,
        )

    async def shutdown(self) -> None:
        """关闭客户端"""
        if self._service:
            await self._service.shutdown()
            self._service = None
