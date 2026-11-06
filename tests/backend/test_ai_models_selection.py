"""Test AI models discovery and dynamic provider/model selection for photo-review."""
import pytest
from unittest.mock import patch
from uuid import UUID
from fastapi.testclient import TestClient

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


def test_list_ai_models_returns_all_three_providers(client):
    resp = client.get("/api/v1/maintenance/ai/models")
    assert resp.status_code == 200
    data = resp.json()

    assert "current_provider" in data
    assert "providers" in data
    provider_ids = [p["id"] for p in data["providers"]]
    assert "clip" in provider_ids
    assert "ollama" in provider_ids
    assert "aitunnel" in provider_ids

    clip_prov = next(p for p in data["providers"] if p["id"] == "clip")
    assert clip_prov["available"] is True
    assert len(clip_prov["models"]) >= 1

    aitunnel_prov = next(p for p in data["providers"] if p["id"] == "aitunnel")
    assert aitunnel_prov["available"] is True
    assert len(aitunnel_prov["models"]) >= 2


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


def test_ml_command_accepts_dynamic_ai_options():
    cmd = MLCommand(
        expected_revision=1,
        comparability_confirmed=True,
        provider="ollama",
        model="qwen3.5:4b",
        api_key="sk-test-key",
    )
    assert cmd.provider == "ollama"
    assert cmd.model == "qwen3.5:4b"
    assert cmd.api_key == "sk-test-key"
