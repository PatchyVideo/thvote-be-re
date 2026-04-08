"""Centralized application settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        default="sqlite:///./data/dev.db",
        alias="DATABASE_URL",
    )
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_secret_key: str | None = Field(default=None, alias="JWT_SECRET_KEY")
    jwt_public_key_path: str | None = Field(default=None, alias="JWT_PUBLIC_KEY_PATH")
    jwt_private_key_path: str | None = Field(default=None, alias="JWT_PRIVATE_KEY_PATH")
    vote_year: int = Field(default=2024, alias="VOTE_YEAR")
    vote_start_iso: str | None = Field(default=None, alias="VOTE_START_ISO")
    vote_end_iso: str | None = Field(default=None, alias="VOTE_END_ISO")

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings object."""
    return Settings()
