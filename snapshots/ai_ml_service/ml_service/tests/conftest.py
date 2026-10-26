"""Общие фикстуры для тестирования ML Service."""
import pytest
from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def default_mock_env(monkeypatch):
    """По умолчанию в тестах используем mock-провайдеры, чтобы тесты были герметичны."""
    monkeypatch.setenv("ML_LLM_PROVIDER", "mock")
    monkeypatch.setenv("ML_CV_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
