"""Test AI models discovery and dynamic provider/model selection for photo-review."""
import pytest
from pydantic import ValidationError
from unittest.mock import patch
from uuid import UUID
from fastapi.testclient import TestClient

from app.config import RuntimeSettings
from app.main import create_app
from app.integration.ml import MLCommand


class DummyPrincipal:
    user_id = UUID("00000000-0000-4000-8000-000000000001")
    role = "engineer"
    site_id = UUID("00000000-0000-4000-8000-000000000002")


class DummyViews:
    principal = DummyPrincipal()


@pytest.fixture
def client():
    app = create_app()
    route = next(r for r in app.routes if getattr(r, "path", None) == "/api/v1/maintenance/ai/models")
    views_dep = route.dependant.dependencies[0].call
    app.dependency_overrides[views_dep] = lambda: DummyViews()
    return TestClient(app)


def test_list_ai_models_excludes_clip_and_defaults_to_aitunnel(client, monkeypatch):
    monkeypatch.setenv("AITUNNEL_API_KEY", "test-secret-do-not-expose")
    resp = client.get("/api/v1/maintenance/ai/models")
    assert resp.status_code == 200
    assert "test-secret-do-not-expose" not in resp.text
    data = resp.json()

    assert data["current_provider"] == "aitunnel"
    provider_ids = [p["id"] for p in data["providers"]]
    assert "clip" not in provider_ids
    assert provider_ids == ["aitunnel", "ollama"]

    aitunnel_prov = next(p for p in data["providers"] if p["id"] == "aitunnel")
    assert aitunnel_prov["available"] is True
    assert aitunnel_prov["has_server_key"] is True
    model_ids = [m["id"] for m in aitunnel_prov["models"]]
    assert "qwen3.7-flash" in model_ids
    assert all("clip" not in m.lower() for m in model_ids)


def test_list_ai_models_with_mocked_ollama(client):
    mock_models = [
        {"id": "qwen3.5:4b", "name": "qwen3.5:4b", "digest": "sha256:1234", "size": 2500000000},
        {"id": "llava:13b", "name": "llava:13b", "digest": "sha256:5678", "size": 7500000000},
    ]

    with patch("ml_service.app.cv.local_vision.scan_local_ollama_models", return_value=(True, mock_models, None)):
        resp = client.get("/api/v1/maintenance/ai/models")
        assert resp.status_code == 200
        data = resp.json()
        ollama_prov = next(p for p in data["providers"] if p["id"] == "ollama")
        assert ollama_prov["available"] is True
        assert len(ollama_prov["models"]) == 2
        assert ollama_prov["models"][0]["name"] == "qwen3.5:4b"


def test_ml_command_and_runtime_settings_reject_clip():
    cmd = MLCommand(
        expected_revision=1,
        comparability_confirmed=True,
        provider="aitunnel",
        model="qwen3.7-flash",
        api_key="sk-test-key",
    )
    assert cmd.provider == "aitunnel" and cmd.model == "qwen3.7-flash"

    with pytest.raises(ValidationError):
        MLCommand(expected_revision=1, provider="clip")

    import os
    old = os.environ.get("PHOTO_REVIEW_PROVIDER")
    try:
        os.environ["PHOTO_REVIEW_PROVIDER"] = "clip"
        with pytest.raises(ValueError, match="aitunnel or ollama"):
            RuntimeSettings.from_environment()
    finally:
        if old is None:
            os.environ.pop("PHOTO_REVIEW_PROVIDER", None)
        else:
            os.environ["PHOTO_REVIEW_PROVIDER"] = old
