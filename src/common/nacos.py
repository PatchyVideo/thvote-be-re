"""
Nacos 配置中心集成模块

使用 HTTP API 方式调用 Nacos，兼容所有版本。
文档: https://nacos.io/docs/latest/guide/user/open-api/
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
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
    """解析 Nacos 配置内容，支持标准 JSON、JS 风格 JSON 和 Properties 格式。"""
    content = content.strip()

    # 尝试标准 JSON
    if content.startswith("{"):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v is not None}
        except Exception:
            pass

        # 尝试转换为标准 JSON（处理 JavaScript 风格的键无引号格式）
        try:
            def _to_json(text: str) -> str | None:
                if text.startswith("{") and text.endswith("}"):
                    inner = text[1:-1]
                else:
                    return None

                result_pairs = []
                i = 0
                n = len(inner)

                while i < n:
                    # 跳过空白
                    while i < n and inner[i] in " \t\n":
                        i += 1
                    if i >= n:
                        break

                    # 解析键（标识符）
                    if inner[i].isalpha() or inner[i] == "_":
                        key_start = i
                        while i < n and (inner[i].isalnum() or inner[i] == "_"):
                            i += 1
                        key = inner[key_start:i]

                        # 跳过空白和冒号
                        while i < n and inner[i] in " \t":
                            i += 1
                        if i < n and inner[i] == ":":
                            i += 1

                        # 跳过空白
                        while i < n and inner[i] in " \t":
                            i += 1

                        # 解析值
                        if i < n:
                            if inner[i] == '"':
                                # 带引号的字符串值
                                i += 1
                                value_chars = []
                                while i < n:
                                    if inner[i] == "\\" and i + 1 < n:
                                        value_chars.append(inner[i])
                                        i += 1
                                        value_chars.append(inner[i])
                                        i += 1
                                    elif inner[i] == '"':
                                        i += 1
                                        break
                                    else:
                                        value_chars.append(inner[i])
                                        i += 1
                                value = "".join(value_chars)
                                result_pairs.append(f'"{key}": "{value}"')
                            elif inner[i] in "tfn":  # true, false, null
                                # 布尔值或 null
                                value_start = i
                                while i < n and inner[i] not in ",}":
                                    i += 1
                                value = inner[value_start:i].strip().rstrip(",").strip()
                                result_pairs.append(f'"{key}": {value}')
                            else:
                                # 裸值（数字、裸字符串等）
                                value_start = i
                                while i < n and inner[i] not in ",}":
                                    i += 1
                                value = inner[value_start:i].strip().rstrip(",").strip()
                                if value:
                                    # 尝试作为数字
                                    try:
                                        if "." in value:
                                            num_val = float(value)
                                        else:
                                            num_val = int(value)
                                        result_pairs.append(f'"{key}": {num_val}')
                                    except ValueError:
                                        result_pairs.append(f'"{key}": "{value}"')

                        # 跳过逗号
                        while i < n and inner[i] in " \t,":
                            i += 1

                return "{" + ",".join(result_pairs) + "}"

            fixed = _to_json(content)
            if fixed:
                data = json.loads(fixed)
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items() if v is not None}
        except Exception:
            pass

    # 回退到 Properties 格式解析
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


class NacosHTTPClient:
    """
    Nacos HTTP API 客户端。

    使用 Nacos Open API 直接调用，避免 SDK gRPC 兼容性问题。
    """

    def __init__(
        self,
        server_addresses: str,
        namespace: str = "",
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 5.0,
    ):
        self.servers = [s.strip() for s in server_addresses.split(",") if s.strip()]
        self.namespace = namespace
        self.username = username
        self.password = password
        self.timeout = timeout
        self._access_token: Optional[str] = None

    async def _get_access_token(self, base_url: str) -> Optional[str]:
        """获取访问令牌"""
        import aiohttp

        if self.username and self.password:
            try:
                url = f"{base_url}/nacos/v1/auth/login"
                data = {"username": self.username, "password": self.password}

                async with aiohttp.ClientSession() as session:
                    async with session.post(url, data=data, timeout=self.timeout) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            return result.get("accessToken")
            except Exception as e:
                logger.warning("Failed to get access token: %s", e)
        return None

    async def get_config(self, data_id: str, group: str = "DEFAULT_GROUP") -> Optional[str]:
        """获取配置"""
        import aiohttp

        for server in self.servers:
            base_url = _normalize_nacos_url(server)

            try:
                # 获取 token
                token = await self._get_access_token(base_url)

                # 构建请求参数
                params = {
                    "dataId": data_id,
                    "group": group,
                }
                if self.namespace:
                    params["namespaceId"] = self.namespace
                if token:
                    params["accessToken"] = token

                url = f"{base_url}/nacos/v1/cs/configs"

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, timeout=self.timeout) as resp:
                        if resp.status == 200:
                            content = await resp.text()
                            if content:
                                return content
                        elif resp.status == 403:
                            logger.warning("Access denied for config: %s", data_id)
            except Exception as e:
                logger.warning("Failed to get config from %s: %s", base_url, e)
                continue

        return None

    async def publish_config(
        self, data_id: str, content: str, group: str = "DEFAULT_GROUP"
    ) -> bool:
        """发布配置"""
        import aiohttp

        for server in self.servers:
            base_url = _normalize_nacos_url(server)

            try:
                token = await self._get_access_token(base_url)

                data = {
                    "dataId": data_id,
                    "group": group,
                    "content": content,
                }
                if self.namespace:
                    data["namespaceId"] = self.namespace
                if token:
                    data["accessToken"] = token

                url = f"{base_url}/nacos/v1/cs/configs"

                async with aiohttp.ClientSession() as session:
                    async with session.post(url, data=data, timeout=self.timeout) as resp:
                        if resp.status == 200:
                            result = await resp.text()
                            return result == "true"
            except Exception as e:
                logger.warning("Failed to publish config to %s: %s", base_url, e)
                continue

        return False

    async def remove_config(self, data_id: str, group: str = "DEFAULT_GROUP") -> bool:
        """删除配置"""
        import aiohttp

        for server in self.servers:
            base_url = _normalize_nacos_url(server)

            try:
                token = await self._get_access_token(base_url)

                params = {
                    "dataId": data_id,
                    "group": group,
                }
                if self.namespace:
                    params["namespaceId"] = self.namespace
                if token:
                    params["accessToken"] = token

                url = f"{base_url}/nacos/v1/cs/configs"

                async with aiohttp.ClientSession() as session:
                    async with session.delete(url, params=params, timeout=self.timeout) as resp:
                        if resp.status == 200:
                            result = await resp.text()
                            return result == "true"
            except Exception as e:
                logger.warning("Failed to remove config from %s: %s", base_url, e)
                continue

        return False


class NacosConfigWatcher:
    """
    Nacos 配置监听器，支持配置热更新。

    使用轮询方式检查配置变更。
    """

    def __init__(
        self,
        server_addr: str,
        namespace: str,
        group: str,
        data_id: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        on_change: Optional[Callable[[dict[str, str]], None]] = None,
        timeout: float = 30.0,
        poll_interval: float = 30.0,
    ):
        self.server_addr = _normalize_nacos_url(server_addr)
        self.namespace = namespace
        self.group = group
        self.data_id = data_id
        self.username = username
        self.password = password
        self.on_change = on_change
        self.timeout = timeout
        self.poll_interval = poll_interval

        self._client: Optional[NacosHTTPClient] = None
        self._current_config: dict[str, str] = {}
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

        logger.debug(
            "NacosConfigWatcher initialized: server=%s, namespace=%s, group=%s, dataId=%s",
            self.server_addr,
            self.namespace,
            self.group,
            self.data_id,
        )

    async def _fetch_current_config(self) -> dict[str, str]:
        """获取当前配置。"""
        if self._client is None:
            self._client = NacosHTTPClient(
                server_addresses=self.server_addr,
                namespace=self.namespace,
                username=self.username,
                password=self.password,
                timeout=self.timeout,
            )

        content = await self._client.get_config(self.data_id, self.group)
        if content:
            return _parse_config_content(content)
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

        # 首次获取配置
        self._current_config = await self._fetch_current_config()
        if self._current_config:
            logger.info("Initial config loaded: %d keys", len(self._current_config))
            if self.on_change:
                self.on_change(self._current_config)

        # 轮询检查配置变更
        while self._running:
            await asyncio.sleep(self.poll_interval)

            try:
                new_config = await self._fetch_current_config()

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

                    self._current_config = new_config

                    if self.on_change:
                        self.on_change(new_config)

            except Exception as exc:
                logger.warning("Error in Nacos watch loop: %s", exc)

        logger.info("Nacos watcher stopped")

    def start(self) -> None:
        """启动监听器。"""
        if self._running:
            return

        self._running = True
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

    使用 HTTP API 调用 Nacos。

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

    try:
        import requests

        # 获取 access token
        access_token = None
        server = server_addrs.split(",")[0].strip()
        base_url = _normalize_nacos_url(server)

        if username and password:
            try:
                token_url = f"{base_url}/nacos/v1/auth/login"
                response = requests.post(
                    token_url,
                    data={"username": username, "password": password},
                    timeout=timeout,
                )
                if response.status_code == 200:
                    token_result = response.json()
                    access_token = token_result.get("accessToken")
            except Exception as e:
                logger.warning("Failed to get access token: %s", e)

        # 获取配置
        params = {
            "dataId": data_id,
            "group": group,
        }
        if namespace:
            params["namespaceId"] = namespace
        if access_token:
            params["accessToken"] = access_token

        config_url = f"{base_url}/nacos/v1/cs/configs"
        response = requests.get(config_url, params=params, timeout=timeout)

        if response.status_code == 200 and response.text:
            logger.debug("Nacos config response: %s", response.text[:500])
            config = _parse_config_content(response.text)

            _apply_config_to_env(config)
            logger.info("Nacos loaded %d config values", len(config))
            return config
        else:
            logger.debug(
                "Nacos config not found: dataId=%s, group=%s", data_id, group
            )

    except ImportError:
        # requests 未安装，尝试使用同步方式
        logger.warning("requests library not found, trying sync aiohttp")
        try:
            import aiohttp
            import ssl

            server = server_addrs.split(",")[0].strip()
            base_url = _normalize_nacos_url(server)

            # 使用 SSL context 避免问题
            ssl_context = ssl.create_default_context()

            async def _fetch():
                nonlocal access_token

                # 获取 token
                if username and password:
                    token_url = f"{base_url}/nacos/v1/auth/login"
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            token_url,
                            data={"username": username, "password": password},
                            timeout=aiohttp.ClientTimeout(total=timeout),
                            ssl=ssl_context,
                        ) as resp:
                            if resp.status == 200:
                                token_result = await resp.json()
                                access_token = token_result.get("accessToken")

                # 获取配置
                params = {"dataId": data_id, "group": group}
                if namespace:
                    params["namespaceId"] = namespace
                if access_token:
                    params["accessToken"] = access_token

                config_url = f"{base_url}/nacos/v1/cs/configs"
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        config_url,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                        ssl=ssl_context,
                    ) as resp:
                        if resp.status == 200:
                            return await resp.text()
                return None

            # 尝试在新的事件循环中运行
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 已有运行中的循环，创建新任务
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, _fetch())
                        content = future.result(timeout=timeout * 2)
                else:
                    content = asyncio.run(_fetch())
            except Exception:
                # 最后尝试
                content = None

            if content:
                logger.debug("Nacos config response: %s", content[:500])
                config = _parse_config_content(content)
                _apply_config_to_env(config)
                logger.info("Nacos loaded %d config values", len(config))
                return config

        except Exception as e:
            logger.warning("Failed to fetch Nacos config from %s: %s", server_addrs, e)

    except Exception as exc:
        logger.warning("Failed to fetch Nacos config from %s: %s", server_addrs, exc)

    # Nacos server unavailable, try local file fallback
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


def start_nacos_watcher(
    on_change: Optional[Callable[[dict[str, str]], None]] = None,
) -> Optional[NacosConfigWatcher]:
    """
    启动 Nacos 配置监听器，实现热更新。

    使用轮询方式检查配置变更。

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
    timeout = float(os.getenv("NACOS_TIMEOUT_SECONDS", "30"))
    poll_interval = float(os.getenv("NACOS_POLL_INTERVAL", "30"))

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
        on_change=combined_callback,
        timeout=timeout,
        poll_interval=poll_interval,
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
