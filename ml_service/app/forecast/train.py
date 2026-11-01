"""Training pipeline for RandomForestForecaster on Dataset B (synthetic_demo)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from sklearn.model_selection import train_test_split

from ml_service.app.core.config import settings
from ml_service.app.forecast.features import FeatureExtractor
from ml_service.app.forecast.manifest import ModelManifest
from ml_service.app.forecast.model import RandomForestForecaster
from ml_service.app.forecast.synthetic import generate_synthetic_forecast_dataset


def run_training_pipeline(
    n_samples: int = 50,
    seed: int = settings.random_seed,
    output_dir: Path | str | None = None,
) -> tuple[RandomForestForecaster, ModelManifest]:
    """Execute reproducible training pipeline and return fitted model and manifest."""
    out_dir = Path(output_dir or settings.artifacts_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate synthetic dataset
    snapshots, targets = generate_synthetic_forecast_dataset(n_samples=n_samples, seed=seed)

    # Compute dataset content hash
    raw_dataset = [s.model_dump(mode="json") for s in snapshots]
    dataset_bytes = json.dumps(raw_dataset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    dataset_sha256 = hashlib.sha256(dataset_bytes).hexdigest()

    # 2. Extract features
    extractor = FeatureExtractor()
    X = extractor.extract_batch(snapshots)
    y = targets

    # Split train/test deterministically
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=seed
    )

    # 3. Train Random Forest
    forecaster = RandomForestForecaster(
        n_estimators=settings.n_estimators,
        max_depth=settings.max_depth,
        random_state=seed,
    )
    forecaster.fit(X_train, y_train)

    # 4. Evaluate metrics
    metrics = forecaster.evaluate(X_test, y_test)

    # 5. Save model artifact
    model_path = out_dir / "rf_model.joblib"
    artifact_sha256 = forecaster.save(model_path)
    model_ref = f"{settings.rf_model_ref_prefix}:{artifact_sha256[:16]}"

    # 6. Create and save manifest
    manifest = ModelManifest(
        schema_version="maintenance-0.1",
        model_ref=model_ref,
        method_version=settings.rf_method_version,
        feature_schema_version=settings.rf_feature_schema_version,
        data_origin="synthetic_demo",
        dataset_sha256=dataset_sha256,
        artifact_sha256=artifact_sha256,
        random_seed=seed,
        trained_at=datetime.now(timezone.utc).isoformat(),
        verified_by="Muhammad (AI Engineer)",
        n_train_samples=len(X_train),
        n_test_samples=len(X_test),
        metrics=metrics,
        provenance_notes="Обучено на Наборе B (synthetic_demo) без использования данных заказчика. Соответствует требованиям P0-08, P0-10, P0-22.",
    )
    manifest_path = out_dir / "artifact_manifest.json"
    manifest.save(manifest_path)

    return forecaster, manifest


if __name__ == "__main__":
    model, man = run_training_pipeline()
    print("=== Training Complete ===")
    print("Model Ref:", man.model_ref)
    print("Artifact SHA-256:", man.artifact_sha256)
    print("Metrics:", man.metrics)
