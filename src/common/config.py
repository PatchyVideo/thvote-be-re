from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration derived from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field("postgresql+async://localhost/thvote", env="DATABASE_URL")
    database_echo: bool = Field(False, env="DATABASE_ECHO")
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_secret_key: Optional[str] = Field(None, env="JWT_SECRET_KEY")
    jwt_public_key_path: Optional[str] = Field(None, env="JWT_PUBLIC_KEY_PATH")
    jwt_private_key_path: Optional[str] = Field(None, env="JWT_PRIVATE_KEY_PATH")
    vote_year: int = Field(2024, env="VOTE_YEAR")
    vote_start_iso: str = Field("2024-01-01T00:00:00Z", env="VOTE_START_ISO")
    vote_end_iso: str = Field("2024-12-31T23:59:59Z", env="VOTE_END_ISO")
    app_host: str = Field("0.0.0.0", env="APP_HOST")
    app_port: int = Field(8000, env="APP_PORT")
    aliyun_pnvs_access_key_id: Optional[str] = Field(
        None, alias="ALIYUN_PNVS_ACCESS_KEY_ID"
    )
    aliyun_pnvs_access_key_secret: Optional[str] = Field(
        None, alias="ALIYUN_PNVS_ACCESS_KEY_SECRET"
    )
    aliyun_pnvs_endpoint: Optional[str] = Field(None, alias="ALIYUN_PNVS_ENDPOINT")
    aliyun_pnvs_region_id: Optional[str] = Field(None, alias="ALIYUN_PNVS_REGION_ID")
    aliyun_pnvs_scheme_name: Optional[str] = Field(
        None, alias="ALIYUN_PNVS_SCHEME_NAME"
    )
    aliyun_pnvs_sms_sign_name: Optional[str] = Field(
        None, alias="ALIYUN_PNVS_SMS_SIGN_NAME"
    )
    aliyun_pnvs_sms_template_code: Optional[str] = Field(
        None, alias="ALIYUN_PNVS_SMS_TEMPLATE_CODE"
    )
    aliyun_pnvs_code_length: Optional[int] = Field(
        None, alias="ALIYUN_PNVS_CODE_LENGTH"
    )
    aliyun_pnvs_valid_time: Optional[int] = Field(None, alias="ALIYUN_PNVS_VALID_TIME")
    aliyun_pnvs_interval: Optional[int] = Field(None, alias="ALIYUN_PNVS_INTERVAL")
    aliyun_dm_access_key_id: Optional[str] = Field(
        None, alias="ALIYUN_DM_ACCESS_KEY_ID"
    )
    aliyun_dm_access_key_secret: Optional[str] = Field(
        None, alias="ALIYUN_DM_ACCESS_KEY_SECRET"
    )
    aliyun_dm_endpoint: Optional[str] = Field(None, alias="ALIYUN_DM_ENDPOINT")
    aliyun_dm_region_id: Optional[str] = Field(None, alias="ALIYUN_DM_REGION_ID")
    aliyun_dm_account_name: Optional[str] = Field(None, alias="ALIYUN_DM_ACCOUNT_NAME")
    aliyun_dm_from_alias: Optional[str] = Field(None, alias="ALIYUN_DM_FROM_ALIAS")
    aliyun_dm_tag_name: Optional[str] = Field(None, alias="ALIYUN_DM_TAG_NAME")
    aliyun_dm_smtp_host: Optional[str] = Field(None, alias="ALIYUN_DM_SMTP_HOST")
    aliyun_dm_smtp_port: Optional[int] = Field(None, alias="ALIYUN_DM_SMTP_PORT")
    aliyun_dm_smtp_username: Optional[str] = Field(
        None, alias="ALIYUN_DM_SMTP_USERNAME"
    )
    aliyun_dm_smtp_password: Optional[str] = Field(
        None, alias="ALIYUN_DM_SMTP_PASSWORD"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()


# Alias for backward compatibility
settings = get_settings()
