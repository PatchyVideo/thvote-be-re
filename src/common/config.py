from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field

try:
    # Pydantic v2
    from pydantic_settings import BaseSettings, SettingsConfigDict
except Exception:  # pragma: no cover
    # Pydantic v1 fallback
    from pydantic import BaseSettings  # type: ignore

    SettingsConfigDict = None  # type: ignore


class Settings(BaseSettings):
    """Application configuration derived from environment variables.

    This mirrors the cross‑cutting concerns from the original Rust services:
    - database connection
    - Redis for rate limiting / caching
    - JWT key material
    - vote window configuration
    - server binding configuration
    """

    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    database_echo: bool = Field(False, env="DATABASE_ECHO")

    # Redis (rate limiting, locks, cache)
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")

    # JWT / auth
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_secret_key: Optional[str] = Field(None, env="JWT_SECRET_KEY")
    jwt_public_key_path: Optional[str] = Field(None, env="JWT_PUBLIC_KEY_PATH")
    jwt_private_key_path: Optional[str] = Field(None, env="JWT_PRIVATE_KEY_PATH")

    # Vote window (mirrors config.toml in Rust version)
    vote_year: int = Field(2024, env="VOTE_YEAR")
    vote_start_iso: str = Field(..., env="VOTE_START_ISO")
    vote_end_iso: str = Field(..., env="VOTE_END_ISO")

    # HTTP server
    app_host: str = Field("0.0.0.0", env="APP_HOST")
    app_port: int = Field(8000, env="APP_PORT")

    # Aliyun PNVS (SMS authentication service)
    aliyun_pnvs_access_key_id: str | None = Field(default=None, alias="ALIYUN_PNVS_ACCESS_KEY_ID")
    aliyun_pnvs_access_key_secret: str | None = Field(default=None, alias="ALIYUN_PNVS_ACCESS_KEY_SECRET")
    aliyun_pnvs_endpoint: str | None = Field(default=None, alias="ALIYUN_PNVS_ENDPOINT")
    aliyun_pnvs_region_id: str | None = Field(default=None, alias="ALIYUN_PNVS_REGION_ID")
    aliyun_pnvs_scheme_name: str | None = Field(default=None, alias="ALIYUN_PNVS_SCHEME_NAME")
    aliyun_pnvs_sms_sign_name: str | None = Field(default=None, alias="ALIYUN_PNVS_SMS_SIGN_NAME")
    aliyun_pnvs_sms_template_code: str | None = Field(default=None, alias="ALIYUN_PNVS_SMS_TEMPLATE_CODE")
    aliyun_pnvs_code_length: int | None = Field(default=None, alias="ALIYUN_PNVS_CODE_LENGTH")
    aliyun_pnvs_valid_time: int | None = Field(default=None, alias="ALIYUN_PNVS_VALID_TIME")
    aliyun_pnvs_interval: int | None = Field(default=None, alias="ALIYUN_PNVS_INTERVAL")

    # Aliyun Direct Mail
    aliyun_dm_access_key_id: str | None = Field(default=None, alias="ALIYUN_DM_ACCESS_KEY_ID")
    aliyun_dm_access_key_secret: str | None = Field(default=None, alias="ALIYUN_DM_ACCESS_KEY_SECRET")
    aliyun_dm_endpoint: str | None = Field(default=None, alias="ALIYUN_DM_ENDPOINT")
    aliyun_dm_region_id: str | None = Field(default=None, alias="ALIYUN_DM_REGION_ID")
    aliyun_dm_account_name: str | None = Field(default=None, alias="ALIYUN_DM_ACCOUNT_NAME")
    aliyun_dm_from_alias: str | None = Field(default=None, alias="ALIYUN_DM_FROM_ALIAS")
    aliyun_dm_tag_name: str | None = Field(default=None, alias="ALIYUN_DM_TAG_NAME")
    aliyun_dm_smtp_host: str | None = Field(default=None, alias="ALIYUN_DM_SMTP_HOST")
    aliyun_dm_smtp_port: int | None = Field(default=None, alias="ALIYUN_DM_SMTP_PORT")
    aliyun_dm_smtp_username: str | None = Field(default=None, alias="ALIYUN_DM_SMTP_USERNAME")
    aliyun_dm_smtp_password: str | None = Field(default=None, alias="ALIYUN_DM_SMTP_PASSWORD")

    # Pydantic v2 config
    if SettingsConfigDict is not None:  # pragma: no cover
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",
        )
    else:
        # Pydantic v1 config
        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()


# Alias for backward compatibility
settings = get_settings()
