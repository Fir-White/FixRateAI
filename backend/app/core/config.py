"""Конфигурация приложения из переменных окружения."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Настройки runtime. Секреты только из env / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(
        default="postgresql+psycopg://fixrate:fixrate@localhost:5432/fixrate",
        alias="DATABASE_URL",
    )
    storage_dir: Path = Field(
        default=BACKEND_ROOT / "var" / "storage",
        alias="STORAGE_DIR",
    )
    ml_base_url: str = Field(
        default="http://localhost:8001",
        alias="ML_BASE_URL",
    )
    jwt_secret: str = Field(
        default="ChangeMe-JwtSecret-LocalOnly",
        alias="JWT_SECRET",
    )
    jwt_expire_minutes: int = Field(default=60, alias="JWT_EXPIRE_MINUTES")


@lru_cache
def get_settings() -> Settings:
    return Settings()
