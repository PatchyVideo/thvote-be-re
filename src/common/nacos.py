"""
Nacos 配置中心 + 注册中心集成模块

配置中心: 使用 nacos-sdk-python 连接 Nacos 配置中心，实现配置热更新。
注册中心: 使用 NacosNamingService 实现服务注册、发现与注销。

文档:
  配置中心: https://nacos.io/docs/latest/manual/user/python-sdk/usage
  注册中心: https://github.com/nacos-group/nacos-sdk-python
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY_VALUES


def _parse_config_content(content: str) -> dict[str, str]:
    """解析 Nacos 配置内容，支持标准 JSON、JS 风格 JSON 和 Properties 格式。"""
    import re

    content = content.strip()
    if not content:
        return {}

    if content.startswith("{"):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v is not None}
        except Exception:
            pass

        try:
            result = {}

            def extract_value(content: str, start: int, end: int) -> str:
                raw = content[start:end].strip().rstrip(",").rstrip("}").strip()
                if not raw:
                    return ""
                if raw.startswith('"') and raw.endswith('"'):
                    return raw[1:-1]
                if raw.startswith("'") and raw.endswith("'"):
                    return raw[1:-1]
                if raw in ("true", "false", "null"):
                    return raw
                try:
                    if "." in raw:
                        float(raw)
                    else:
                        int(raw)
                    return raw
                except ValueError:
                    pass
                return raw

            pattern = r"[,{\s](\w+)\s*:"
            matches = list(re.finditer(pattern, content))

            for i, match in enumerate(matches):
                key = match.group(1)
                value_start = match.end()
                if i + 1 < len(matches):
                    value_end = matches[i + 1].start()
                else:
                    value_end = len(content)
                result[key] = extract_value(content, value_start, value_end)

            if result:
                return result
        except Exception:
            pass

    result = {}
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


def _apply_config_to_env(config: dict[str, str]) -> None:
    """将配置应用到环境变量。"""
    for key, value in config.items():
        os.environ[key] = value


# ---------------------------------------------------------------------------
# 配置中心
# ---------------------------------------------------------------------------


class NacosConfigListener:
    """
    Nacos 配置监听器，使用 SDK 的长连接监听机制。

    相比轮询方式，SDK 的长连接能即时感知配置变更。
    """

    def __init__(
        self,
        server_addrs: str,
        namespace: str,
        group: str,
        data_id: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        on_change: Optional[Callable[[dict[str, str]], None]] = None,
    ):
        self.server_addrs = server_addrs
        self.namespace = namespace
        self.group = group
        self.data_id = data_id
        self.username = username
        self.password = password
        self.on_change = on_change

        self._config_client = None
        self._current_config: dict[str, str] = {}
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

        logger.debug(
            "NacosConfigListener initialized: server=%s, namespace=%s, "
            "group=%s, dataId=%s",
            server_addrs,
            namespace,
            group,
            data_id,
        )

    async def _init_client(self) -> None:
        """初始化 SDK 客户端。"""
        if self._config_client is not None:
            return

        try:
            from v2.nacos import (
                NacosConfigService,
                ClientConfigBuilder,
                ConfigParam,
            )

            builder = ClientConfigBuilder().server_address(self.server_addrs)

            if self.namespace:
                builder.namespace_id(self.namespace)

            if self.username and self.password:
                builder.username(self.username).password(self.password)

            config = builder.build()
            self._config_client = await NacosConfigService.create_config_service(config)

            # 获取初始配置
            param = ConfigParam(
                data_id=self.data_id,
                group=self.group,
            )

            content = await self._config_client.get_config(param)
            if content:
                self._current_config = _parse_config_content(content)
                logger.info(
                    "Initial config loaded from SDK: %d keys", len(self._current_config)
                )
                _apply_config_to_env(self._current_config)
                if self.on_change:
                    self.on_change(self._current_config)

        except ImportError as e:
            logger.error("nacos-sdk-python not installed: %s", e)
            raise
        except Exception as e:
            logger.error("Failed to initialize Nacos SDK client: %s", e)
            raise

    def _on_sdk_config_change(
        self, tenant: str, group: str, data_id: str, content: str
    ) -> None:
        """SDK 配置变更回调。"""
        logger.info(
            "Nacos config changed (SDK callback): dataId=%s, content_len=%d",
            data_id,
            len(content) if content else 0,
        )

        if content:
            new_config = _parse_config_content(content)
            self._current_config = new_config
            _apply_config_to_env(new_config)

            if self.on_change:
                self.on_change(new_config)

    async def _watch_loop(self) -> None:
        """监听循环。"""
        logger.info(
            "Nacos SDK listener started: server=%s, namespace=%s, group=%s, dataId=%s",
            self.server_addrs,
            self.namespace,
            self.group,
            self.data_id,
        )

        await self._init_client()

        if self._config_client is None:
            logger.error("Nacos SDK client not initialized")
            return

        # 使用 SDK 的长连接监听
        try:
            await self._config_client.add_listener(
                data_id=self.data_id,
                group=self.group,
                listener=self._on_sdk_config_change,
            )
            logger.info("SDK listener registered for %s/%s", self.group, self.data_id)

            # 保持运行，等待配置变更
            while self._running:
                await asyncio.sleep(60)

        except Exception as e:
            logger.error("Error in SDK listener: %s", e)
        finally:
            logger.info("Nacos SDK listener stopped")

    def start(self) -> None:
        """启动监听器。"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.debug("Nacos SDK listener task started")

    async def stop(self) -> None:
        """停止监听器。"""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._config_client:
            try:
                await self._config_client.remove_listener(
                    data_id=self.data_id,
                    group=self.group,
                    listener=self._on_sdk_config_change,
                )
            except Exception as e:
                logger.warning("Error removing SDK listener: %s", e)

        logger.info("Nacos SDK listener stopped")

    @property
    def current_config(self) -> dict[str, str]:
        """获取当前配置。"""
        return self._current_config.copy()


# 全局监听器实例
_listener: Optional[NacosConfigListener] = None


async def load_nacos_config() -> dict[str, str]:
    """
    从 Nacos 一次性加载配置。

    使用 SDK 获取配置，适用于启动时加载配置。
    如需热更新，请使用 start_nacos_listener()。
    """
    if not _env_flag("NACOS_ENABLED", "false"):
        logger.debug("Nacos disabled (NACOS_ENABLED != true)")
        return {}

    server_addrs = os.getenv("NACOS_SERVER_ADDRS", "")
    namespace = os.getenv("NACOS_NAMESPACE", "")
    group = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
    data_id = os.getenv("NACOS_DATA_ID", "")
    username = os.getenv("NACOS_USERNAME")
    password = os.getenv("NACOS_PASSWORD")

    if not server_addrs:
        logger.warning("NACOS_ENABLED is true but NACOS_SERVER_ADDRS is empty")
        return {}

    if not data_id:
        logger.warning("NACOS_DATA_ID is not set, skipping Nacos config loading")
        return {}

    logger.debug(
        "Nacos config: server=%s, namespace=%s, group=%s, data_id=%s",
        server_addrs,
        namespace,
        group,
        data_id,
    )

    try:
        from v2.nacos import NacosConfigService, ClientConfigBuilder, ConfigParam

        builder = ClientConfigBuilder().server_address(server_addrs)

        if namespace:
            builder.namespace_id(namespace)

        if username and password:
            builder.username(username).password(password)

        config = builder.build()
        config_client = await NacosConfigService.create_config_service(config)

        param = ConfigParam(
            data_id=data_id,
            group=group,
        )

        content = await config_client.get_config(param)

        if content:
            config_dict = _parse_config_content(content)
            _apply_config_to_env(config_dict)
            logger.info("Nacos loaded %d config values", len(config_dict))
            return config_dict
        else:
            logger.debug("Nacos config not found: dataId=%s, group=%s", data_id, group)

    except ImportError:
        logger.error("nacos-sdk-python not installed, cannot load Nacos config")
    except Exception as e:
        logger.warning("Failed to fetch Nacos config from %s: %s", server_addrs, e)

    # 回退到本地文件
    local_data_id = os.getenv("NACOS_DATA_ID", "")
    if local_data_id:
        local_path = Path(__file__).parent.parent.parent / local_data_id
        if local_path.exists():
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    content = f.read()
                logger.info("Loading config from local file: %s", local_path)
                config = _parse_config_content(content)
                _apply_config_to_env(config)
                logger.info("Loaded %d config values from local file", len(config))
                return config
            except Exception as e:
                logger.warning("Failed to load local config file: %s", e)

    return {}


def start_nacos_listener(
    on_change: Optional[Callable[[dict[str, str]], None]] = None,
) -> Optional[NacosConfigListener]:
    """
    启动 Nacos 配置监听器，实现热更新。

    使用 SDK 的长连接机制实时监听配置变更。

    Args:
        on_change: 配置变更时的回调函数

    Returns:
        NacosConfigListener 实例，如果 Nacos 未启用则返回 None
    """
    global _listener

    if not _env_flag("NACOS_ENABLED", "false"):
        logger.debug("Nacos disabled, not starting listener")
        return None

    server_addrs = os.getenv("NACOS_SERVER_ADDRS", "")
    namespace = os.getenv("NACOS_NAMESPACE", "")
    group = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
    data_id = os.getenv("NACOS_DATA_ID", "thvote-be")
    username = os.getenv("NACOS_USERNAME")
    password = os.getenv("NACOS_PASSWORD")

    if not server_addrs or not data_id:
        logger.warning("NACOS_ENABLED is true but server or data_id is missing")
        return None

    def combined_callback(config: dict[str, str]) -> None:
        if on_change:
            on_change(config)

    _listener = NacosConfigListener(
        server_addrs=server_addrs,
        namespace=namespace,
        group=group,
        data_id=data_id,
        username=username,
        password=password,
        on_change=combined_callback,
    )

    _listener.start()
    return _listener


async def stop_nacos_listener() -> None:
    """停止 Nacos 配置监听器。"""
    global _listener
    if _listener:
        await _listener.stop()
        _listener = None


def get_nacos_listener() -> Optional[NacosConfigListener]:
    """获取当前的监听器实例。"""
    return _listener


# 向后兼容别名
NacosConfigWatcher = NacosConfigListener


def load_nacos_overrides() -> dict[str, str]:
    """
    从 Nacos 一次性加载配置并覆盖环境变量。

    注意：此函数已废弃，建议使用 load_nacos_config()。
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, load_nacos_config())
                return future.result(timeout=30)
        return asyncio.run(load_nacos_config())
    except Exception as e:
        logger.warning("Failed to load Nacos overrides: %s", e)
        return {}


def start_nacos_watcher(
    on_change: Optional[Callable[[dict[str, str]], None]] = None,
) -> Optional[NacosConfigListener]:
    """向后兼容的函数名，使用 start_nacos_listener()。"""
    return start_nacos_listener(on_change)


async def stop_nacos_watcher() -> None:
    """向后兼容的函数名，使用 stop_nacos_listener()。"""
    await stop_nacos_listener()


def get_nacos_watcher() -> Optional[NacosConfigListener]:
    """向后兼容的函数名，使用 get_nacos_listener()。"""
    return get_nacos_listener()


# ---------------------------------------------------------------------------
# 注册中心：服务注册、发现与注销
# ---------------------------------------------------------------------------


class NacosServiceRegister:
    """
    Nacos 注册中心封装，支持服务注册、注销和发现。

    使用 SDK v3 的 NacosNamingService，自动处理心跳保活。
    临时实例（ephemeral=True）由 SDK gRPC 客户端自动发送心跳。
    """

    def __init__(
        self,
        server_addrs: str,
        namespace: str,
        service_name: str,
        ip: str,
        port: int,
        group: str = "DEFAULT_GROUP",
        cluster_name: str = "DEFAULT",
        weight: float = 1.0,
        metadata: dict | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        self.server_addrs = server_addrs
        self.namespace = namespace
        self.service_name = service_name
        self.ip = ip
        self.port = port
        self.group = group
        self.cluster_name = cluster_name
        self.weight = weight
        self.metadata = metadata or {}
        self.username = username
        self.password = password

        self._naming_client = None

        logger.debug(
            "NacosServiceRegister initialized: service=%s, ip=%s, port=%s, "
            "group=%s, cluster=%s",
            service_name,
            ip,
            port,
            group,
            cluster_name,
        )

    async def _init_client(self) -> None:
        """初始化 SDK 客户端。"""
        if self._naming_client is not None:
            return

        try:
            from v2.nacos import (
                ClientConfigBuilder,
                NacosNamingService,
            )

            builder = ClientConfigBuilder().server_address(self.server_addrs)

            if self.namespace:
                builder.namespace_id(self.namespace)

            if self.username and self.password:
                builder.username(self.username).password(self.password)

            client_config = builder.build()
            self._naming_client = await NacosNamingService.create_naming_service(
                client_config
            )

        except ImportError as e:
            logger.error("nacos-sdk-python not installed: %s", e)
            raise
        except Exception as e:
            logger.error("Failed to initialize Nacos naming client: %s", e)
            raise

    async def register(self) -> bool:
        """
        注册服务实例到 Nacos。

        使用临时实例（ephemeral=True），SDK gRPC 客户端会自动发送心跳保活。

        Returns:
            True if registration succeeded, False otherwise.
        """
        await self._init_client()

        try:
            from v2.nacos import RegisterInstanceParam

            result = await self._naming_client.register_instance(
                request=RegisterInstanceParam(
                    service_name=self.service_name,
                    group_name=self.group,
                    ip=self.ip,
                    port=self.port,
                    weight=self.weight,
                    cluster_name=self.cluster_name,
                    metadata=self.metadata,
                    enabled=True,
                    healthy=True,
                    ephemeral=True,
                )
            )
            logger.info(
                "Service registered to Nacos: %s @ %s:%s (cluster=%s, weight=%s)",
                self.service_name,
                self.ip,
                self.port,
                self.cluster_name,
                self.weight,
            )
            return result is True or result is None

        except Exception as e:
            logger.error("Failed to register service %s: %s", self.service_name, e)
            return False

    async def deregister(self) -> bool:
        """
        从 Nacos 注销服务实例。

        Returns:
            True if deregistration succeeded, False otherwise.
        """
        if self._naming_client is None:
            logger.warning("Nacos naming client not initialized, skipping deregister")
            return False

        try:
            from v2.nacos import DeregisterInstanceParam

            result = await self._naming_client.deregister_instance(
                request=DeregisterInstanceParam(
                    service_name=self.service_name,
                    group_name=self.group,
                    ip=self.ip,
                    port=self.port,
                    cluster_name=self.cluster_name,
                    ephemeral=True,
                )
            )
            logger.info(
                "Service deregistered from Nacos: %s @ %s:%s",
                self.service_name,
                self.ip,
                self.port,
            )
            return result is True or result is None

        except Exception as e:
            logger.error("Failed to deregister service %s: %s", self.service_name, e)
            return False

    async def discover(
        self,
        service_name: str | None = None,
        group: str | None = None,
        healthy_only: bool = False,
    ) -> list:
        """
        从 Nacos 发现服务实例。

        Args:
            service_name: 服务名，默认为本实例的服务名。
            group: 分组名，默认为本实例的分组。
            healthy_only: 是否只返回健康实例。

        Returns:
            实例列表。
        """
        await self._init_client()

        sn = service_name or self.service_name
        grp = group or self.group

        try:
            from v2.nacos import ListInstanceParam

            instances = await self._naming_client.list_instances(
                request=ListInstanceParam(
                    service_name=sn,
                    group_name=grp,
                    healthy_only=healthy_only,
                    subscribe=False,
                )
            )

            logger.debug(
                "Discovered %d instances for service %s/%s (healthy_only=%s)",
                len(instances) if instances else 0,
                grp,
                sn,
                healthy_only,
            )
            return instances if instances else []

        except Exception as e:
            logger.error("Failed to discover service %s: %s", sn, e)
            return []

    async def list_all_services(self, page_no: int = 1, page_size: int = 20) -> dict:
        """
        分页列出所有已注册的服务。

        Returns:
            dict with 'services' (list) and 'count' (int).
        """
        await self._init_client()

        try:
            from v2.nacos import ListServiceParam

            result = await self._naming_client.list_services(
                request=ListServiceParam(
                    namespace_id=self.namespace or "public",
                    group_name=self.group,
                    page_no=page_no,
                    page_size=page_size,
                )
            )

            return {
                "services": result.domains or [],
                "count": result.count if hasattr(result, "count") else 0,
            }

        except Exception as e:
            logger.error("Failed to list services: %s", e)
            return {"services": [], "count": 0}

    async def shutdown(self) -> None:
        """关闭 SDK 客户端，释放资源。"""
        if self._naming_client is not None:
            try:
                await self._naming_client.shutdown()
            except Exception as e:
                logger.warning("Error shutting down Nacos naming client: %s", e)
            self._naming_client = None


# 全局注册器实例
_service_register: Optional[NacosServiceRegister] = None


async def register_service_to_nacos(
    server_addrs: str,
    namespace: str,
    service_name: str,
    ip: str,
    port: int,
    group: str = "DEFAULT_GROUP",
    cluster_name: str = "DEFAULT",
    weight: float = 1.0,
    metadata: dict | None = None,
    username: str | None = None,
    password: str | None = None,
) -> NacosServiceRegister:
    """
    创建并启动服务注册到 Nacos。

    便捷函数，内部创建 NacosServiceRegister 并执行注册。
    """
    global _service_register

    reg = NacosServiceRegister(
        server_addrs=server_addrs,
        namespace=namespace,
        service_name=service_name,
        ip=ip,
        port=port,
        group=group,
        cluster_name=cluster_name,
        weight=weight,
        metadata=metadata,
        username=username,
        password=password,
    )

    await reg.register()
    _service_register = reg
    return reg


async def deregister_service_from_nacos() -> None:
    """从 Nacos 注销服务（使用全局注册器实例）。"""
    global _service_register
    if _service_register is not None:
        await _service_register.deregister()
        await _service_register.shutdown()
        _service_register = None


async def discover_service_from_nacos(
    service_name: str,
    group: str = "DEFAULT_GROUP",
    healthy_only: bool = False,
    namespace: str = "",
    server_addrs: str = "",
    username: str | None = None,
    password: str | None = None,
) -> list:
    """
    发现服务实例（一次性查询，不持久化连接）。

    便捷函数，适用于客户端调用。
    """
    reg = NacosServiceRegister(
        server_addrs=server_addrs,
        namespace=namespace,
        service_name=service_name,
        ip="0.0.0.0",
        port=0,
        group=group,
        username=username,
        password=password,
    )
    try:
        instances = await reg.discover(
            service_name=service_name,
            group=group,
            healthy_only=healthy_only,
        )
        return instances
    finally:
        await reg.shutdown()


def get_service_register() -> Optional[NacosServiceRegister]:
    """获取当前的服务注册器实例。"""
    return _service_register


# 向后兼容别名
NacosServiceRegistry = NacosServiceRegister
