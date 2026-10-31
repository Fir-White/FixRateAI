"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["local", "development", "production", "test"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    debug: bool = Field(default=False)

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+psycopg://fixrate:ChangeMe-local-only@127.0.0.1:5433/fixrate"
    )

    # Security
    jwt_secret: str = Field(default="ChangeMe-long-random-string", min_length=32)
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60, ge=5, le=1440)

    # Storage
    storage_dir: str = Field(default="var/storage")
    storage_max_file_size: int = Field(default=10_485_760, gt=0)
    storage_max_image_pixels: int = Field(default=20_000_000, gt=0)

    # ML Service
    ml_base_url: str = Field(default="http://127.0.0.1:8001")

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: str, info) -> str:
        """Warn about weak JWT secret in production."""
        env = info.data.get("app_env")
        weak_secrets = ("ChangeMe", "secret", "test", "dev")
        if env == "production" and any(weak in value for weak in weak_secrets):
            raise ValueError(
                "JWT_SECRET must be strong in production environment"
            )
        return value

    @property
    def is_test(self) -> bool:
        """Check if running in test environment."""
        return self.app_env == "test"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env in ("local", "development")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
