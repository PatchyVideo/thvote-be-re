"""
Nacos 配置中心集成模块 (基于官方 nacos-sdk-python)

文档: https://nacos.io/en/docs/latest/manual/user/python-sdk/usage
"""
from __future__ import annotations

import asyncio
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


def _parse_config_content(content: str) -> dict[str, str]:
    """解析 Nacos 配置内容，支持 JSON 和 Properties 格式。"""
    content = content.strip()

    if content.startswith("{"):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v is not None}
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


class NacosConfigWatcher:
    """
    Nacos 配置监听器，支持配置热更新。

    使用官方 nacos-sdk-python 库实现配置变更检测。
    """

    def __init__(
        self,
        server_addr: str,
        namespace: str,
        group: str,
        data_id: str,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        on_change: Optional[Callable[[dict[str, str]], None]] = None,
        timeout: float = 30.0,
    ):
        import nacos

        self.server_addr = _normalize_nacos_url(server_addr)
        self.namespace = namespace
        self.group = group
        self.data_id = data_id
        self.on_change = on_change
        self.timeout = timeout

        client_kwargs: dict[str, Any] = {
            "server_addresses": server_addr,
            "namespace": namespace,
        }

        if username and password:
            client_kwargs["username"] = username
            client_kwargs["password"] = password
        elif access_key and secret_key:
            client_kwargs["ak"] = access_key
            client_kwargs["sk"] = secret_key

        self._nacos_client = nacos.NacosClient(**client_kwargs)
        self._current_config: dict[str, str] = {}
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._watch_callbacks: list[Callable[[str], None]] = []

        logger.debug(
            "NacosConfigWatcher initialized: server=%s, namespace=%s, group=%s, dataId=%s",
            self.server_addr,
            self.namespace,
            self.group,
            self.data_id,
        )

    def _on_config_change(self, content: str) -> None:
        """Nacos 配置变更回调"""
        try:
            new_config = _parse_config_content(content)
            if new_config != self._current_config:
                old_keys = set(self._current_config.keys())
                new_keys = set(new_config.keys())

                added = new_keys - old_keys
                removed = old_keys - new_keys
                changed = {
                    k for k in old_keys & new_keys
                    if self._current_config[k] != new_config[k]
                }

                logger.info(
                    "Nacos config updated: +%d/-%d/~%d keys",
                    len(added),
                    len(removed),
                    len(changed),
                )

                if added:
                    logger.debug("Added keys: %s", added)
                if removed:
                    logger.debug("Removed keys: %s", removed)
                if changed:
                    logger.debug("Changed keys: %s", changed)

                self._current_config = new_config

                if self.on_change:
                    self.on_change(new_config)
        except Exception as exc:
            logger.warning("Error processing config change: %s", exc)

    async def _fetch_current_config(self) -> dict[str, str]:
        """获取当前配置。"""
        loop = asyncio.get_event_loop()
        try:
            content = await loop.run_in_executor(
                None,
                lambda: self._nacos_client.get_config(self.data_id, self.group),
            )
            if content:
                logger.debug("Nacos config fetched: %s", content[:500])
                return _parse_config_content(content)
            return {}
        except Exception as exc:
            logger.warning("Failed to fetch Nacos config: %s", exc)
            return {}

    async def _watch_loop(self) -> None:
        """监听循环。"""
        logger.info(
            "Nacos watcher started: server=%s, namespace=%s, group=%s, dataId=%s",
            self.server_addr,
            self.namespace,
            self.group,
            self.data_id,
        )

        # 添加监听器
        self._watch_callbacks.append(self._on_config_change)
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._nacos_client.add_config_watchers(
                    self.data_id, self.group, self._watch_callbacks
                ),
            )
            logger.debug("Nacos config watcher registered")
        except Exception as exc:
            logger.warning("Failed to register config watcher: %s", exc)

        # 首次获取配置
        self._current_config = await self._fetch_current_config()
        if self._current_config:
            logger.info("Initial config loaded: %d keys", len(self._current_config))

        # 保持运行直到被停止
        while self._running:
            await asyncio.sleep(60)

        logger.info("Nacos watcher stopped")

    def start(self) -> None:
        """启动监听器（在事件循环中调用）。"""
        if self._running:
            return

        self._running = True
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._watch_loop())

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

        logger.info("Nacos watcher stopped")

    @property
    def current_config(self) -> dict[str, str]:
        """获取当前配置。"""
        return self._current_config.copy()


# 全局 watcher 实例
_watcher: Optional[NacosConfigWatcher] = None


def _apply_config_to_env(config: dict[str, str]) -> None:
    """
    将配置应用到环境变量。

    使用 setdefault 确保只设置尚未存在的值，
    保留环境变量的优先级。
    """
    for key, value in config.items():
        os.environ.setdefault(key, value)


def load_nacos_overrides() -> dict[str, str]:
    """
    从 Nacos 一次性加载配置并覆盖环境变量。

    使用官方 nacos-sdk-python 库。

    注意：此函数仅覆盖尚未设置的环境变量（setdefault），
    因此环境变量优先级高于 Nacos 配置。

    如需热更新，请使用 start_nacos_watcher()。
    """
    from dotenv import load_dotenv

    load_dotenv(override=False)

    if not _env_flag("NACOS_ENABLED", "false"):
        logger.debug("Nacos disabled (NACOS_ENABLED != true)")
        return {}

    server_addrs = os.getenv("NACOS_SERVER_ADDRS", "")
    namespace = os.getenv("NACOS_NAMESPACE", "")
    group = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
    data_id = os.getenv("NACOS_DATA_ID", "")
    username = os.getenv("NACOS_USERNAME")
    password = os.getenv("NACOS_PASSWORD")
    access_key = os.getenv("NACOS_ACCESS_KEY")
    secret_key = os.getenv("NACOS_SECRET_KEY")
    timeout = float(os.getenv("NACOS_TIMEOUT_SECONDS", "5"))

    if not server_addrs:
        logger.warning("NACOS_ENABLED is true but NACOS_SERVER_ADDRS is empty")
        return {}

    if not data_id:
        logger.warning("NACOS_DATA_ID is not set, skipping Nacos config loading")
        return {}

    logger.debug(
        "Nacos config: server=%s, namespace=%s, group=%s, data_id=%s, timeout=%s",
        server_addrs,
        namespace,
        group,
        data_id,
        timeout,
    )

    import nacos

    client_kwargs: dict[str, Any] = {
        "server_addresses": server_addrs,
        "namespace": namespace,
    }

    if username and password:
        client_kwargs["username"] = username
        client_kwargs["password"] = password
    elif access_key and secret_key:
        client_kwargs["ak"] = access_key
        client_kwargs["sk"] = secret_key

    try:
        client = nacos.NacosClient(**client_kwargs)
        content = client.get_config(data_id, group)

        if content:
            logger.debug("Nacos config response: %s", content[:500])
            config = _parse_config_content(content)

            _apply_config_to_env(config)
            logger.info("Nacos loaded %d config values", len(config))
            return config
        else:
            logger.debug(
                "Nacos config not found: dataId=%s, group=%s", data_id, group
            )
            return {}

    except Exception as exc:
        logger.warning("Failed to fetch Nacos config from %s: %s", server_addrs, exc)
        return {}


def start_nacos_watcher(
    on_change: Optional[Callable[[dict[str, str]], None]] = None,
) -> Optional[NacosConfigWatcher]:
    """
    启动 Nacos 配置监听器，实现热更新。

    使用官方 nacos-sdk-python 库。

    Args:
        on_change: 配置变更时的回调函数

    Returns:
        NacosConfigWatcher 实例，如果 Nacos 未启用则返回 None
    """
    global _watcher

    if not _env_flag("NACOS_ENABLED", "false"):
        logger.debug("Nacos disabled, not starting watcher")
        return None

    server_addrs = os.getenv("NACOS_SERVER_ADDRS", "")
    namespace = os.getenv("NACOS_NAMESPACE", "")
    group = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
    data_id = os.getenv("NACOS_DATA_ID", "thvote-be")
    username = os.getenv("NACOS_USERNAME")
    password = os.getenv("NACOS_PASSWORD")
    access_key = os.getenv("NACOS_ACCESS_KEY")
    secret_key = os.getenv("NACOS_SECRET_KEY")
    timeout = float(os.getenv("NACOS_TIMEOUT_SECONDS", "30"))

    if not server_addrs or not data_id:
        logger.warning("NACOS_ENABLED is true but server or data_id is missing")
        return None

    # 合并回调
    def combined_callback(config: dict[str, str]) -> None:
        _apply_config_to_env(config)
        if on_change:
            on_change(config)

    # 取第一个服务器地址
    servers = [s.strip() for s in server_addrs.split(",") if s.strip()]
    if not servers:
        logger.warning("No valid Nacos servers found")
        return None

    _watcher = NacosConfigWatcher(
        server_addr=servers[0],
        namespace=namespace,
        group=group,
        data_id=data_id,
        username=username,
        password=password,
        access_key=access_key,
        secret_key=secret_key,
        on_change=combined_callback,
        timeout=timeout,
    )

    _watcher.start()
    return _watcher


async def stop_nacos_watcher() -> None:
    """停止 Nacos 配置监听器。"""
    global _watcher
    if _watcher:
        await _watcher.stop()
        _watcher = None


def get_nacos_watcher() -> Optional[NacosConfigWatcher]:
    """获取当前的 watcher 实例。"""
    return _watcher
