"""Общие фикстуры для тестирования ML Service."""
import pytest
from app.core.config import Settings, get_settings


@pytest.fixture
def test_settings() -> Settings:
    """Фикстура настроек с тестовыми дефолтами."""
    get_settings.cache_clear()
    return Settings(
        app_name="Test ML Service",
        app_env="test",
        cv_provider="mock",
        llm_provider="mock",
    )
