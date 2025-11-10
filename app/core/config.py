from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

from pydantic import AnyUrl, Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        alias="APP_ENV",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: Annotated[PostgresDsn, Field(alias="DATABASE_URL")]
    alembic_config: Path | None = Field(default=None, alias="ALEMBIC_CONFIG")
    fernet_key: str | None = Field(default=None, alias="FERNET_KEY")
    admin_ids: list[int] = Field(default_factory=list, alias="ADMIN_IDS")

    bot_main_token: str | None = Field(default=None, alias="BOT_MAIN_TOKEN")
    bot_standby_token: str | None = Field(default=None, alias="BOT_STANDBY_TOKEN")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, value: Any) -> list[int]:
        if value in (None, "", []):
            return []
        if isinstance(value, (list, tuple)):
            return [int(v) for v in value]
        return [int(v.strip()) for v in str(value).split(",") if v.strip()]

    @field_validator("alembic_config", mode="before")
    @classmethod
    def _resolve_alembic_path(cls, value: Any) -> Path | None:
        if not value:
            return None
        return Path(value)

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> AppSettings:
    """Return cached application settings."""

    return AppSettings()  # type: ignore[call-arg]

