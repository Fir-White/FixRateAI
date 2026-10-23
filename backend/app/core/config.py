"""Конфигурация приложения.

Все настройки берутся из переменных окружения / файла `.env` (pydantic-settings).
Секретов в коде нет: значения по умолчанию — безопасные заглушки.
`DATABASE_URL` используется карточкой 2 (engine/session и ORM-модели).
JWT_* пока только зарезервированы под следующую карточку авторизации.
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

    # PostgreSQL: используется engine/session и ORM-моделями (карточка 2).
    database_url: str = ""
    storage_dir: str = "var/storage"
    ml_base_url: str = ""
    jwt_secret: str = ""
    jwt_expire_minutes: int = 60
    demo_user_email: str = "demo.operator@fixrate.local"


@lru_cache
def get_settings() -> Settings:
    """Один экземпляр настроек на процесс (кэшируется)."""
    return Settings()
