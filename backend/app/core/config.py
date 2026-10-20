"""Конфигурация приложения.

Все настройки берутся из переменных окружения / файла `.env` (pydantic-settings).
Секретов в коде нет: значения по умолчанию — безопасные заглушки.
Часть ключей (DATABASE_URL, STORAGE_DIR, ML_BASE_URL, JWT_*) пока только зарезервирована
под следующие карточки (2, 3, 5) — приложение их читает, но не использует.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",  # ищется относительно каталога, откуда запущен uvicorn (backend/)
        env_file_encoding="utf-8",
        extra="ignore",  # лишние переменные окружения не должны ронять приложение
    )

    app_name: str = "FixRate AI API"
    app_version: str = "0.1.0"
    app_env: str = "local"
    log_level: str = "INFO"

    # Заделы под следующие карточки. Реальные значения — только в .env.
    database_url: str = ""
    storage_dir: str = "var/storage"
    ml_base_url: str = ""
    jwt_secret: str = ""
    jwt_expire_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    """Один экземпляр настроек на процесс (кэшируется)."""
    return Settings()
