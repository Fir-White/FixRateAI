"""Pytest fixtures for ML service tests."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from ml_service.app.core.config import settings
from ml_service.app.forecast.model import RandomForestForecaster
from ml_service.app.forecast.synthetic import generate_synthetic_forecast_dataset
from ml_service.app.schemas import ForecastSnapshot


@pytest.fixture(scope="session")
def trained_forecaster() -> RandomForestForecaster:
    """Fixture providing a fitted RandomForestForecaster trained on synthetic demo."""
    model_path = settings.artifacts_path / "rf_model.joblib"
    forecaster = RandomForestForecaster()
    if model_path.exists():
        forecaster.load(model_path)
    else:
        snapshots, targets = generate_synthetic_forecast_dataset(n_samples=25, seed=42)
        from ml_service.app.forecast.features import FeatureExtractor
        X = FeatureExtractor().extract_batch(snapshots)
        forecaster.fit(X, targets)
    return forecaster


@pytest.fixture
def synthetic_snapshot() -> ForecastSnapshot:
    """Fixture providing a valid synthetic ForecastSnapshot."""
    snapshots, _ = generate_synthetic_forecast_dataset(n_samples=1, seed=42)
    return snapshots[0]


@pytest.fixture
def canonical_example_snapshot() -> ForecastSnapshot:
    """Fixture loading the exact canonical forecast_snapshot from contracts/examples/maintenance.json."""
    examples_path = Path(__file__).resolve().parents[2] / "contracts/examples/maintenance.json"
    with open(examples_path, "r", encoding="utf-8") as f:
        examples = json.load(f)["examples"]
    ex = next(x for x in examples if x["name"] == "forecast_snapshot")
    return ForecastSnapshot.model_validate_json(json.dumps(ex["payload"]))


@pytest.fixture
def canonical_photo_review_request() -> PhotoReviewRequest:
    """Fixture loading the exact canonical photo_review_request from contracts/examples/maintenance.json."""
    from ml_service.app.schemas import PhotoReviewRequest
    examples_path = Path(__file__).resolve().parents[2] / "contracts/examples/maintenance.json"
    with open(examples_path, "r", encoding="utf-8") as f:
        examples = json.load(f)["examples"]
    ex = next(x for x in examples if x["name"] == "photo_review_request")
    return PhotoReviewRequest.model_validate_json(json.dumps(ex["payload"]))

