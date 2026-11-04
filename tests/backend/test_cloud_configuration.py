"""Configuration-only checks, no external provider or demo database changes."""
from pathlib import Path
import pytest
from app.config import RuntimeSettings
from scripts.start_local import read_ai_environment


def test_cloud_wait_budget_and_provider_selection(monkeypatch):
    monkeypatch.setenv("PHOTO_REVIEW_PROVIDER", "aitunnel")
    monkeypatch.setenv("FORECAST_PROVIDER", "aitunnel")
    monkeypatch.setenv("FORECAST_TIMEOUT_SECONDS", "100")
    settings = RuntimeSettings.from_environment()
    assert settings.photo_review_provider == settings.forecast_provider == "aitunnel"
    assert settings.forecast_timeout_seconds == 100


@pytest.mark.parametrize("key,value", [("FORECAST_PROVIDER", "unknown"), ("PHOTO_REVIEW_PROVIDER", "unknown"),
    ("FORECAST_TIMEOUT_SECONDS", "121")])
def test_invalid_cloud_settings_are_rejected(monkeypatch, key, value):
    monkeypatch.setenv("FORECAST_PROVIDER", "aitunnel")
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError): RuntimeSettings.from_environment()


def test_launcher_reads_only_allowlisted_cloud_keys_and_environment_takes_precedence(tmp_path):
    path = tmp_path / ".env"
    path.write_text("AI_TUNNEL_API_KEY=fixture-token\nDATABASE_URL=do-not-import\nAITUNNEL_VISION_MODEL=qwen3.7-flash\n", encoding="utf-8")
    values = read_ai_environment(path, {"AITUNNEL_VISION_MODEL": "another-model"})
    assert values == {"AI_TUNNEL_API_KEY": "fixture-token", "AITUNNEL_VISION_MODEL": "another-model"}
