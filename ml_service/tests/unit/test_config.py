"""Тесты модуля конфигурации и типизированных ошибок."""
import pytest
from app.core.config import Settings, get_settings
from app.core.errors import (
    AppError,
    NotFoundError,
    ValidationError,
    InvalidImageError,
    ModelUnavailableError,
    error_response,
)


def test_settings_default_values():
    settings = Settings()
    assert settings.app_name == "FixRate AI ML Service"
    assert settings.cv_enabled is True
    assert settings.cv_provider == "mock"
    assert settings.cv_confidence_threshold == 0.25
    assert "facade_crack" in settings.cv_allowed_classes
    assert settings.llm_provider == "mock"


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("ML_APP_NAME", "Custom ML")
    monkeypatch.setenv("ML_CV_CONFIDENCE_THRESHOLD", "0.5")
    monkeypatch.setenv("ML_CV_PROVIDER", "yolo")
    
    settings = Settings()
    assert settings.app_name == "Custom ML"
    assert settings.cv_confidence_threshold == 0.5
    assert settings.cv_provider == "yolo"


def test_app_error_hierarchy():
    err = NotFoundError("Дефект не найден", details=[{"field": "defect_id", "issue": "not found"}])
    assert err.status_code == 404
    assert err.code == "NOT_FOUND"
    assert err.message == "Дефект не найден"
    assert len(err.details) == 1

    val_err = ValidationError("Поле обязательно")
    assert val_err.status_code == 422
    assert val_err.code == "VALIDATION_ERROR"

    img_err = InvalidImageError("Файл повреждён")
    assert img_err.status_code == 400
    assert img_err.code == "INVALID_IMAGE"

    model_err = ModelUnavailableError("Веса не найдены")
    assert model_err.status_code == 503
    assert model_err.code == "MODEL_UNAVAILABLE"


def test_error_response_shape():
    resp = error_response(
        request=None,
        status_code=404,
        code="NOT_FOUND",
        message="Элемент не найден",
        details=[{"field": "id", "issue": "missing"}],
        request_id="test-req-123",
    )
    assert resp.status_code == 404
    assert resp.headers["X-Request-ID"] == "test-req-123"
    
    import json
    body = json.loads(resp.body)
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Элемент не найден"
    assert body["error"]["request_id"] == "test-req-123"
    assert body["error"]["details"] == [{"field": "id", "issue": "missing"}]
