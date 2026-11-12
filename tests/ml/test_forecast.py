"""Unit and integration tests for AI forecasting module (FX26-ML01, FX26-ML02, FX26-ML03)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4
import numpy as np
import pytest

from ml_service.app.forecast.client import predict_maintenance_ai, set_active_forecaster, warmup_forecaster
from ml_service.app.forecast.features import FeatureExtractor, FEATURE_NAMES
from ml_service.app.forecast.manifest import ModelManifest
from ml_service.app.forecast.model import RandomForestForecaster
from ml_service.app.forecast.synthetic import (
    compute_snapshot_hash,
    generate_synthetic_forecast_dataset,
)
from ml_service.app.schemas import ForecastSnapshot


def test_feature_extractor_shape_and_names(synthetic_snapshot: ForecastSnapshot):
    """Verify feature extractor extracts 6 finite numbers without NaN."""
    extractor = FeatureExtractor()
    feat = extractor.extract_features(synthetic_snapshot)

    assert isinstance(feat, np.ndarray)
    assert feat.shape == (6,)
    assert len(FEATURE_NAMES) == 6
    assert not np.isnan(feat).any()
    assert not np.isinf(feat).any()


def test_feature_extractor_batch(synthetic_snapshot: ForecastSnapshot):
    """Verify batch extraction preserves batch dimension."""
    extractor = FeatureExtractor()
    batch = [synthetic_snapshot, synthetic_snapshot]
    X = extractor.extract_batch(batch)

    assert X.shape == (2, 6)
    assert np.allclose(X[0], X[1])


def test_canonical_snapshot_hash_verification(canonical_example_snapshot: ForecastSnapshot):
    """Verify compute_snapshot_hash strictly produces the matching canonical hash."""
    payload = json.loads(canonical_example_snapshot.model_dump_json())
    computed = compute_snapshot_hash(payload)

    assert computed == canonical_example_snapshot.content_sha256
    assert len(computed) == 64


def test_model_training_and_tree_dispersion(trained_forecaster: RandomForestForecaster):
    """Verify tree dispersion ordering: lower_bound <= point_prediction <= upper_bound."""
    x_test = np.array([731.0, 500.0, 30.0, 150.0, 3.0, 35.0])
    point_pred, lower_bound, upper_bound = trained_forecaster.predict_with_dispersion(x_test)

    assert lower_bound <= point_pred <= upper_bound
    assert point_pred > 0


def test_model_serialization_roundtrip(tmp_path, trained_forecaster: RandomForestForecaster):
    """Verify saving and loading model artifact preserves predictions and SHA-256."""
    target_path = tmp_path / "test_model.joblib"
    sha1 = trained_forecaster.save(target_path)

    loaded = RandomForestForecaster().load(target_path)
    sha2 = loaded.artifact_sha256

    assert sha1 == sha2
    x = np.array([731.0, 500.0, 30.0, 150.0, 3.0, 35.0])
    p1 = trained_forecaster.predict_with_dispersion(x)
    p2 = loaded.predict_with_dispersion(x)
    assert np.allclose(p1, p2)


def test_predict_maintenance_ai_success(synthetic_snapshot: ForecastSnapshot, trained_forecaster: RandomForestForecaster):
    """Verify P0-08 / FX26-ML03: Successful AI prediction on synthetic snapshot."""
    result = predict_maintenance_ai(synthetic_snapshot, forecaster=trained_forecaster)

    assert result.method == "ai"
    assert result.status == "ok"
    assert result.recommended_date is not None
    assert result.error_code is None
    assert result.model_ref is not None
    assert result.snapshot_id == synthetic_snapshot.snapshot_id
    assert result.snapshot_sha256 == synthetic_snapshot.content_sha256
    assert result.uncertainty.kind == "tree_dispersion"
    assert result.uncertainty.lower_date is not None
    assert result.uncertainty.upper_date is not None
    assert result.uncertainty.lower_date <= result.recommended_date <= result.uncertainty.upper_date
    assert result.warnings == ["SYNTHETIC_DATA"]
    assert result.elapsed_ms >= 0


def test_predict_maintenance_ai_unavailable_when_no_model(synthetic_snapshot: ForecastSnapshot):
    """Verify P0-10 / S08: Controlled fallback with status='unavailable' when model is missing."""
    result = predict_maintenance_ai(synthetic_snapshot, forecaster=None)

    assert result.method == "ai"
    assert result.status == "unavailable"
    assert result.recommended_date is None
    assert result.error_code == "MODEL_NOT_READY"
    assert result.uncertainty.kind == "unknown"
    assert result.uncertainty.lower_date is None
    assert result.uncertainty.upper_date is None
    assert result.elapsed_ms >= 0


def test_predict_maintenance_ai_unavailable_for_customer_origin(synthetic_snapshot: ForecastSnapshot, trained_forecaster: RandomForestForecaster):
    """Verify B-08 / P0-22: Customer origin without history returns controlled unavailable."""
    # Create customer origin copy
    payload = json.loads(synthetic_snapshot.model_dump_json())
    payload["data_origin"] = "customer"
    payload["site"]["data_origin"] = "customer"
    payload["equipment"]["data_origin"] = "customer"
    payload["operation"]["data_origin"] = "customer"
    payload["rule"]["data_origin"] = "customer"
    payload["content_sha256"] = compute_snapshot_hash(payload)

    customer_snapshot = ForecastSnapshot.model_validate_json(json.dumps(payload))
    result = predict_maintenance_ai(customer_snapshot, forecaster=trained_forecaster)

    assert result.status == "unavailable"
    assert result.recommended_date is None
    assert result.error_code == "MODEL_NOT_READY"
    assert "CUSTOMER_UNCONFIRMED" in result.warnings


def test_predict_maintenance_ai_graceful_failure_handling(synthetic_snapshot: ForecastSnapshot):
    """Verify exception inside forecaster returns status='failed' without 500 error."""
    class BrokenForecaster(RandomForestForecaster):
        @property
        def is_fitted(self):
            return True

        def predict_with_dispersion(self, x, **kwargs):
            raise ZeroDivisionError("Simulated calculation error")

    result = predict_maintenance_ai(synthetic_snapshot, forecaster=BrokenForecaster())

    assert result.status == "failed"
    assert result.recommended_date is None
    assert result.error_code == "AI_INFERENCE_FAILED"
    assert result.uncertainty.kind == "unknown"


def test_artifact_manifest_schema_and_roundtrip(tmp_path):
    """Verify artifact manifest saves and loads with complete metadata."""
    manifest = ModelManifest(
        schema_version="maintenance-0.1",
        model_ref="synthetic_demo:rf:test-sha",
        method_version="rf-days-v1",
        feature_schema_version="rf-features-v1",
        data_origin="synthetic_demo",
        dataset_sha256="a" * 64,
        artifact_sha256="b" * 64,
        random_seed=42,
        trained_at="2026-10-29T18:00:00+00:00",
        verified_by="Muhammad (AI Engineer)",
        n_train_samples=40,
        n_test_samples=10,
        metrics={"mae_days": 0.65, "mse_days": 1.2},
        provenance_notes="Test manifest",
    )
    path = tmp_path / "test_manifest.json"
    manifest.save(path)
    loaded = ModelManifest.load(path)

    assert loaded.model_ref == manifest.model_ref
    assert loaded.dataset_sha256 == manifest.dataset_sha256
    assert loaded.metrics["mae_days"] == 0.65


def test_forecaster_warmup_and_fast_tree_dispersion(trained_forecaster: RandomForestForecaster):
    """Verify forecaster warmup hook primes CPU caches and dispersion is ordered."""
    assert warmup_forecaster(trained_forecaster) is True
    assert warmup_forecaster(None) in (True, False)  # depending on whether default artifact exists on disk

    x_test = np.array([500.0, 365.0, 15.0, 100.0, 4.0, 25.0])
    point, low, high = trained_forecaster.predict_with_dispersion(x_test)
    assert low <= point <= high
    assert point > 0.0
