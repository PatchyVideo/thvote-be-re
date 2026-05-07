"""
Nacos 配置中心官方 SDK 客户端模块

使用官方 nacos-sdk-python 库连接 Nacos 2.2.3
文档: https://github.com/nacos-group/nacos-sdk-python
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY_VALUES


def _normalize_nacos_url(raw_value: str | None) -> str:
    """Normalize Nacos server URL."""
    value = (raw_value or "http://localhost:8848").strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


class NacosConfigClient:
    """
    Nacos 配置中心客户端 (基于官方 nacos-sdk-python)

    支持:
    - 获取配置 get_config
    - 发布配置 publish_config
    - 删除配置 remove_config
    - 配置监听 add_config_watchers
    - 热更新回调
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
                              例如: "192.168.1.1:8848,192.168.1.2:8848"
            namespace: 命名空间 ID (您的: ce2b18cc-e2ee-4673-a2a3-6b5b33309fb1)
            group: 配置分组，默认 DEFAULT_GROUP
            username: 用户名 (用于鉴权)
            password: 密码 (用于鉴权)
            ak: Access Key (阿里云 RAM 鉴权)
            sk: Secret Key (阿里云 RAM 鉴权)
            log_level: 日志级别
        """
        self.namespace = namespace
        self.group = group
        self._client = None
        self._lock = threading.Lock()

        import nacos

        client_kwargs: dict[str, Any] = {
            "server_addresses": server_addresses,
            "namespace": namespace,
        }

        if username and password:
            client_kwargs["username"] = username
            client_kwargs["password"] = password
        elif ak and sk:
            client_kwargs["ak"] = ak
            client_kwargs["sk"] = sk

        if log_level:
            client_kwargs["log_level"] = log_level

        self._client = nacos.NacosClient(**client_kwargs)
        logger.info(
            "Nacos client initialized: servers=%s, namespace=%s, group=%s",
            server_addresses,
            namespace,
            group,
        )

    def get_config(self, data_id: str, group: Optional[str] = None) -> Optional[str]:
        """
        获取配置

        Args:
            data_id: 配置 dataId
            group: 配置分组，默认使用初始化时的分组

        Returns:
            配置内容字符串，配置不存在返回 None
        """
        if group is None:
            group = self.group

        try:
            content = self._client.get_config(data_id, group)
            logger.debug(
                "Config fetched: dataId=%s, group=%s, content_len=%d",
                data_id,
                group,
                len(content) if content else 0,
            )
            return content
        except Exception as exc:
            logger.warning("Failed to get config: dataId=%s, error=%s", data_id, exc)
            return None

    def get_config_as_dict(
        self, data_id: str, group: Optional[str] = None
    ) -> dict[str, Any]:
        """
        获取配置并解析为字典

        支持 JSON 格式和 Properties 格式

        Args:
            data_id: 配置 dataId
            group: 配置分组

        Returns:
            配置字典
        """
        content = self.get_config(data_id, group)
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

    def publish_config(
        self, data_id: str, content: str, group: Optional[str] = None
    ) -> bool:
        """
        发布配置

        Args:
            data_id: 配置 dataId
            content: 配置内容
            group: 配置分组

        Returns:
            是否成功
        """
        if group is None:
            group = self.group

        try:
            self._client.publish_config(data_id, group, content)
            logger.info("Config published: dataId=%s, group=%s", data_id, group)
            return True
        except Exception as exc:
            logger.error("Failed to publish config: dataId=%s, error=%s", data_id, exc)
            return False

    def remove_config(self, data_id: str, group: Optional[str] = None) -> bool:
        """
        删除配置

        Args:
            data_id: 配置 dataId
            group: 配置分组

        Returns:
            是否成功
        """
        if group is None:
            group = self.group

        try:
            self._client.remove_config(data_id, group)
            logger.info("Config removed: dataId=%s, group=%s", data_id, group)
            return True
        except Exception as exc:
            logger.error("Failed to remove config: dataId=%s, error=%s", data_id, exc)
            return False

    def add_config_watchers(
        self, data_id: str, callbacks: list[Callable[[str], None]], group: Optional[str] = None
    ) -> None:
        """
        添加配置监听器

        Args:
            data_id: 配置 dataId
            callbacks: 回调函数列表，接收新配置内容作为参数
            group: 配置分组
        """
        if group is None:
            group = self.group

        def make_callback(cb: Callable[[str], None]) -> Callable[[str], None]:
            def wrapper(config: str) -> None:
                try:
                    cb(config)
                except Exception as exc:
                    logger.warning("Config watcher callback error: %s", exc)

            return wrapper

        wrapped_callbacks = [make_callback(cb) for cb in callbacks]
        self._client.add_config_watchers(data_id, group, wrapped_callbacks)
        logger.info(
            "Config watchers added: dataId=%s, group=%s, callback_count=%d",
            data_id,
            group,
            len(callbacks),
        )


# 全局客户端实例
_client: Optional[NacosConfigClient] = None


def get_nacos_client() -> Optional[NacosConfigClient]:
    """获取全局 Nacos 客户端实例。"""
    return _client


def init_nacos_client() -> Optional[NacosConfigClient]:
    """
    从环境变量初始化全局 Nacos 客户端

    环境变量:
        NACOS_ENABLED: 是否启用 Nacos
        NACOS_SERVER_ADDRS: Nacos 服务器地址
        NACOS_NAMESPACE: 命名空间 ID
        NACOS_GROUP: 配置分组
        NACOS_USERNAME: 用户名 (可选)
        NACOS_PASSWORD: 密码 (可选)
        NACOS_ACCESS_KEY: Access Key (可选)
        NACOS_SECRET_KEY: Secret Key (可选)

    Returns:
        NacosConfigClient 实例，失败返回 None
    """
    global _client

    if not _env_flag("NACOS_ENABLED", "false"):
        logger.debug("Nacos disabled (NACOS_ENABLED != true)")
        return None

    server_addrs = os.getenv("NACOS_SERVER_ADDRS", "")
    if not server_addrs:
        logger.warning("NACOS_ENABLED is true but NACOS_SERVER_ADDRS is empty")
        return None

    namespace = os.getenv("NACOS_NAMESPACE", "")
    group = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
    username = os.getenv("NACOS_USERNAME")
    password = os.getenv("NACOS_PASSWORD")
    ak = os.getenv("NACOS_ACCESS_KEY")
    sk = os.getenv("NACOS_SECRET_KEY")
    log_level = os.getenv("NACOS_LOG_LEVEL")

    try:
        _client = NacosConfigClient(
            server_addresses=server_addrs,
            namespace=namespace,
            group=group,
            username=username,
            password=password,
            ak=ak,
            sk=sk,
            log_level=log_level,
        )
        logger.info(
            "Nacos client initialized: servers=%s, namespace=%s",
            server_addrs,
            namespace,
        )
        return _client
    except Exception as exc:
        logger.error("Failed to initialize Nacos client: %s", exc)
        return None


def load_nacos_config(data_id: Optional[str] = None) -> dict[str, Any]:
    """
    加载 Nacos 配置并返回字典

    Args:
        data_id: 配置 dataId，默认从环境变量 NACOS_DATA_ID 获取

    Returns:
        配置字典
    """
    if data_id is None:
        data_id = os.getenv("NACOS_DATA_ID", "")

    if not data_id:
        logger.warning("No data_id specified for Nacos config loading")
        return {}

    client = get_nacos_client()
    if not client:
        client = init_nacos_client()

    if not client:
        return {}

    return client.get_config_as_dict(data_id)
