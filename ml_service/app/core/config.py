"""Конфигурация ML Service FixRate AI.

Все параметры считываются из переменных окружения и .env файлов (префикс ML_).
Значения по умолчанию безопасны и готовы для локального запуска и тестов.
"""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ML_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Базовые параметры сервиса
    app_name: str = "FixRate AI ML Service"
    app_version: str = "0.1.0"
    app_env: str = "local"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8001

    # Компьютерное зрение (CV)
    cv_enabled: bool = True
    cv_provider: str = "mock"  # "mock" | "yolo"
    cv_model_path: str = "models/defect-yolo.pt"
    cv_confidence_threshold: float = 0.25
    cv_iou_threshold: float = 0.45
    cv_device: str = "cpu"  # "cpu" | "cuda" | "auto"
    cv_max_image_pixels: int = 20_000_000  # Защита от Decompression Bomb (Pillow)
    cv_allowed_classes: list[str] = [
        "facade_crack",
        "tile_chip",
        "parking_leak",
    ]

    # Языковая модель (LLM / Model Gateway)
    llm_enabled: bool = True
    llm_provider: str = "mock"  # "mock" | "gigachat" | "openai"
    llm_api_key: str = ""
    llm_model_name: str = "mock-normalizer"
    llm_timeout_seconds: int = 15

    # GigaChat (Сбер) настройки
    gigachat_credentials: str = ""  # Base64 Auth Key (авторизационные данные)
    gigachat_scope: str = "GIGACHAT_API_PERS"  # GIGACHAT_API_PERS | GIGACHAT_API_CORP | GIGACHAT_API_B2B
    gigachat_model: str = "GigaChat-Pro"  # GigaChat-Pro | GigaChat-Lite | GigaChat-Max
    gigachat_verify_ssl_certs: bool = False  # False для избежания проблем с НУЦ Минцифры в Linux
    gigachat_timeout: float = 30.0

    # RAG и нормативно-справочная база
    rag_catalog_path: str = "data/demo_rates.json"
    database_url: str = ""  # При подключении к PostgreSQL + pgvector
    vector_dims: int = 768

    @property
    def base_dir(self) -> Path:
        """Корневая директория ml_service."""
        return Path(__file__).resolve().parent.parent.parent


@lru_cache
def get_settings() -> Settings:
    """Кэшированный синглтон настроек на процесс."""
    return Settings()
