from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Optional, Set

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _load_nacos_sync() -> None:
    """
    同步加载 Nacos 配置。

    在首次调用 get_settings() 时加载，使用线程池执行异步的 load_nacos_config()。
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, _load_nacos_config_async())
                future.result(timeout=30)
        else:
            asyncio.run(_load_nacos_config_async())
    except Exception as e:
        logger.warning("Failed to load Nacos config during module import: %s", e)


async def _load_nacos_config_async() -> None:
    """异步加载 Nacos 配置的内部函数。"""
    try:
        from .nacos import load_nacos_config

        result = await load_nacos_config()
        if result:
            logger.info("Nacos config loaded %d keys", len(result))
    except Exception as e:
        logger.warning("Failed to load Nacos config: %s", e)


# 可热更新的配置键集合（从 Nacos 加载时会动态更新）
_hot_reloadable_keys: Set[str] = set()
_nacos_loaded: bool = False


def _mark_reloadable_keys(keys: set[str]) -> None:
    """标记哪些配置键可以从 Nacos 热更新。"""
    global _hot_reloadable_keys
    _hot_reloadable_keys = keys
    logger.debug("Hot reloadable keys marked: %s", keys)


class DatabaseSettings(BaseSettings):
    """
    数据库配置（支持独立配置项，热更新友好）。

    可以通过 DATABASE_URL 整体配置，也可以通过单独的选项配置。
    单独配置项优先级高于 DATABASE_URL。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 传统方式：整体连接字符串
    database_url: Optional[str] = Field(None)

    # 独立配置项（优先级高于 DATABASE_URL）
    db_host: str = Field("localhost")
    db_port: int = Field(5432)
    db_user: str = Field("postgres")
    db_password: Optional[str] = Field(None)
    db_name: str = Field("thvote")
    db_schema: str = Field("public")
    db_driver: str = Field("postgresql+asyncpg")

    # 连接池配置
    db_pool_size: int = Field(5)
    db_max_overflow: int = Field(10)
    db_pool_timeout: int = Field(30)
    db_pool_recycle: int = Field(3600)
    db_echo: bool = Field(False)

    def build_url(self) -> str:
        """
        构建数据库连接 URL。

        优先使用独立的配置项，如果没有设置则回退到 DATABASE_URL。
        """
        if self.database_url:
            return self.database_url

        password = self.db_password or ""
        return (
            f"{self.db_driver}://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    def build_url_with_schema(self) -> str:
        """构建包含 schema 的数据库连接 URL（PostgreSQL 专用）。"""
        base_url = self.build_url()
        if self.db_schema and self.db_schema != "public":
            # PostgreSQL 支持 ?options=... 格式设置 search_path
            return f"{base_url}?options=-csearch_path%3D{self.db_schema}"
        return base_url


class RedisSettings(BaseSettings):
    """Redis 配置（支持独立配置项，热更新友好）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 传统方式
    redis_url: Optional[str] = Field(None)

    # 独立配置项
    redis_host: str = Field("localhost")
    redis_port: int = Field(6379)
    redis_db: int = Field(0)
    redis_password: Optional[str] = Field(None)
    redis_ssl: bool = Field(False)

    def build_url(self) -> str:
        """构建 Redis 连接 URL。"""
        if self.redis_url:
            return self.redis_url

        password_part = f":{self.redis_password}@" if self.redis_password else ""
        ssl_part = "?ssl=1" if self.redis_ssl else ""
        base = f"redis://{password_part}{self.redis_host}:{self.redis_port}"
        return f"{base}/{self.redis_db}{ssl_part}"


class Settings(BaseSettings):
    """Application configuration derived from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 数据库配置
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    # Redis 配置
    redis: RedisSettings = Field(default_factory=RedisSettings)

    # JWT 配置
    jwt_algorithm: str = Field("HS256")
    jwt_secret_key: Optional[str] = Field(None)
    jwt_secret_key_file: Optional[str] = Field(None)
    jwt_public_key_path: Optional[str] = Field(None)
    jwt_private_key_path: Optional[str] = Field(None)
    # session_token 有效期(天)。决定"多久不来就要重新发验证码登录"。
    # 默认 30:覆盖较长的不活跃间隔以减少短信发送;权衡是会话被盗用窗口更长。
    session_expire_days: int = Field(30, validation_alias="SESSION_EXPIRE_DAYS")

    # Nacos 配置
    nacos_enabled: bool = Field(False)
    nacos_server_addrs: str = Field("http://localhost:8848")
    nacos_namespace: str = Field("")
    nacos_group: str = Field("DEFAULT_GROUP")
    nacos_data_id: str = Field("thvote-be")
    nacos_access_key: Optional[str] = Field(None)
    nacos_secret_key: Optional[str] = Field(None)
    # Nacos 服务注册发现配置
    nacos_service_name: str = Field("thvote-be")
    nacos_service_ip: str = Field("0.0.0.0")
    nacos_service_port: int = Field(8000)
    nacos_service_cluster: str = Field("DEFAULT")
    nacos_service_weight: float = Field(1.0)

    # 投票配置
    vote_year: int = Field(2026)
    vote_start_iso: str = Field("2026-01-01T00:00:00Z")
    vote_end_iso: str = Field("2026-12-31T23:59:59Z")

    # 提名(二创)配置
    nomination_start_iso: Optional[str] = Field(
        None, validation_alias="NOMINATION_START_ISO"
    )
    nomination_end_iso: Optional[str] = Field(
        None, validation_alias="NOMINATION_END_ISO"
    )
    work_eligible_start_iso: Optional[str] = Field(
        None, validation_alias="WORK_ELIGIBLE_START_ISO"
    )
    work_eligible_end_iso: Optional[str] = Field(
        None, validation_alias="WORK_ELIGIBLE_END_ISO"
    )
    dojin_domain_allowlist_raw: Optional[str] = Field(
        None, validation_alias="DOJIN_DOMAIN_ALLOWLIST"
    )

    @property
    def dojin_domain_allowlist(self) -> list[str]:
        if not self.dojin_domain_allowlist_raw:
            return []
        return [
            d.strip()
            for d in self.dojin_domain_allowlist_raw.split(",")
            if d.strip()
        ]

    # 结果计算配置
    gender_question_id: str = Field("q11011")
    gender_male_value: str = Field("male")
    gender_female_value: str = Field("female")
    admin_secret: Optional[str] = Field(None)

    # MongoDB 历史数据同步（可选，未配置时同步端点返回 503）
    mongodb_uri: Optional[str] = Field(None, validation_alias="MONGODB_URI")
    mongodb_db_users: str = Field("thvote_users", validation_alias="MONGODB_DB_USERS")
    mongodb_db_submits: str = Field("submits_v1", validation_alias="MONGODB_DB_SUBMITS")
    mongodb_db_results: str = Field(
        "submits_v1_final", validation_alias="MONGODB_DB_RESULTS"
    )
    mongodb_batch_size: int = Field(500, validation_alias="MONGO_BATCH_SIZE")

    # 爬虫配置
    youtube_api_key: Optional[str] = Field(None)

    # 安全配置
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["*"])
    trusted_proxy_ips: list[str] = Field(default_factory=list)

    # SSO 配置（通过 Nacos 下发，与 ALIYUN_* 字段同等对待）
    qq_app_id: Optional[str] = Field(None, validation_alias="QQ_APP_ID")
    qq_app_secret: Optional[str] = Field(None, validation_alias="QQ_APP_SECRET")
    thbwiki_client_id: Optional[str] = Field(None, validation_alias="THBWIKI_CLIENT_ID")
    thbwiki_client_secret: Optional[str] = Field(
        None, validation_alias="THBWIKI_CLIENT_SECRET"
    )
    sso_callback_base_url: Optional[str] = Field(
        None, validation_alias="SSO_CALLBACK_BASE_URL"
    )

    # 应用配置
    app_host: str = Field("0.0.0.0")
    app_port: int = Field(8000)

    # 阿里云短信配置
    aliyun_pnvs_access_key_id: Optional[str] = Field(
        None, validation_alias="ALIYUN_PNVS_ACCESS_KEY_ID"
    )
    aliyun_pnvs_access_key_secret: Optional[str] = Field(
        None, validation_alias="ALIYUN_PNVS_ACCESS_KEY_SECRET"
    )
    aliyun_pnvs_endpoint: Optional[str] = Field(
        None, validation_alias="ALIYUN_PNVS_ENDPOINT"
    )
    aliyun_pnvs_region_id: Optional[str] = Field(
        None, validation_alias="ALIYUN_PNVS_REGION_ID"
    )
    aliyun_pnvs_scheme_name: Optional[str] = Field(
        None, validation_alias="ALIYUN_PNVS_SCHEME_NAME"
    )
    aliyun_pnvs_sms_sign_name: Optional[str] = Field(
        None, validation_alias="ALIYUN_PNVS_SMS_SIGN_NAME"
    )
    aliyun_pnvs_sms_template_code: Optional[str] = Field(
        None, validation_alias="ALIYUN_PNVS_SMS_TEMPLATE_CODE"
    )
    aliyun_pnvs_code_length: Optional[int] = Field(
        None, validation_alias="ALIYUN_PNVS_CODE_LENGTH"
    )
    aliyun_pnvs_valid_time: Optional[int] = Field(
        None, validation_alias="ALIYUN_PNVS_VALID_TIME"
    )
    aliyun_pnvs_interval: Optional[int] = Field(
        None, validation_alias="ALIYUN_PNVS_INTERVAL"
    )
    # 短信模板参数 JSON。``##code##`` 是 PNVS 自动填充验证码的占位符。
    # 默认只含 code；若模板还有别的变量（如有效期 min），需在此提供匹配的 JSON，
    # 否则阿里云会报「模板内容与模板参数不匹配」(SMS_SEND_FAILED)。
    aliyun_pnvs_template_param: Optional[str] = Field(
        None, validation_alias="ALIYUN_PNVS_TEMPLATE_PARAM"
    )

    # 阿里云邮件配置
    aliyun_dm_access_key_id: Optional[str] = Field(
        None, validation_alias="ALIYUN_DM_ACCESS_KEY_ID"
    )
    aliyun_dm_access_key_secret: Optional[str] = Field(
        None, validation_alias="ALIYUN_DM_ACCESS_KEY_SECRET"
    )
    aliyun_dm_endpoint: Optional[str] = Field(
        None, validation_alias="ALIYUN_DM_ENDPOINT"
    )
    aliyun_dm_region_id: Optional[str] = Field(
        None, validation_alias="ALIYUN_DM_REGION_ID"
    )
    aliyun_dm_account_name: Optional[str] = Field(
        None, validation_alias="ALIYUN_DM_ACCOUNT_NAME"
    )
    aliyun_dm_from_alias: Optional[str] = Field(
        None, validation_alias="ALIYUN_DM_FROM_ALIAS"
    )
    aliyun_dm_tag_name: Optional[str] = Field(
        None, validation_alias="ALIYUN_DM_TAG_NAME"
    )
    aliyun_dm_smtp_host: Optional[str] = Field(
        None, validation_alias="ALIYUN_DM_SMTP_HOST"
    )
    aliyun_dm_smtp_port: Optional[int] = Field(
        None, validation_alias="ALIYUN_DM_SMTP_PORT"
    )
    aliyun_dm_smtp_username: Optional[str] = Field(
        None, validation_alias="ALIYUN_DM_SMTP_USERNAME"
    )
    aliyun_dm_smtp_password: Optional[str] = Field(
        None, validation_alias="ALIYUN_DM_SMTP_PASSWORD"
    )

    @property
    def database_url(self) -> str:
        """兼容性别段，返回数据库连接 URL。"""
        return self.database.build_url()

    @property
    def redis_url(self) -> str:
        """兼容性别段，返回 Redis 连接 URL。"""
        return self.redis.build_url()

    @property
    def database_echo(self) -> bool:
        """兼容性别段。"""
        return self.database.db_echo


# 缓存的设置实例
_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Return a cached Settings instance, loading Nacos config on first call."""
    global _settings_instance, _nacos_loaded
    if _settings_instance is None:
        if not _nacos_loaded:
            _load_nacos_sync()
            _nacos_loaded = True
        _settings_instance = Settings()
    return _settings_instance


def reload_settings() -> Settings:
    """
    重新加载配置。

    对于可热更新的配置（如数据库地址、Redis 地址等），会从环境变量重新读取。
    对于需要完全重启的配置（如 JWT 算法变更），需要重启应用。
    """
    global _settings_instance
    _settings_instance = Settings()
    logger.info("Settings reloaded")
    return _settings_instance


def reload_from_env(keys: set[str]) -> Settings:
    """
    仅从环境变量重新加载指定配置键。

    Args:
        keys: 需要重新加载的配置键集合

    Returns:
        重新加载后的 Settings 实例
    """
    global _settings_instance
    new_settings = Settings()
    _settings_instance = new_settings
    logger.info("Partial settings reloaded for keys: %s", keys)
    return new_settings


# 注册热更新回调
def _on_nacos_config_change(config: dict[str, str]) -> None:
    """
    Nacos 配置变更回调。

    重新加载从 Nacos 获取的配置。
    """
    logger.info(
        "Nacos config changed, %d keys reloaded. "
        "Note: Some configs require application restart to take effect.",
        len(config),
    )
    _mark_reloadable_keys(set(config.keys()))


# 导出回调供外部注册
nacos_config_change_callback = _on_nacos_config_change
