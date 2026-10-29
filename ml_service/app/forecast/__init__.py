"""Forecast package."""
from .client import (
    get_active_forecaster,
    predict_maintenance_ai,
    set_active_forecaster,
)
from .features import FeatureExtractor, FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from .manifest import ModelManifest
from .model import RandomForestForecaster
from .synthetic import (
    compute_snapshot_hash,
    create_demo_operation,
    create_demo_rule,
    create_demo_site,
    generate_synthetic_forecast_dataset,
)

__all__ = [
    "FEATURE_NAMES",
    "FEATURE_SCHEMA_VERSION",
    "FeatureExtractor",
    "ModelManifest",
    "RandomForestForecaster",
    "compute_snapshot_hash",
    "create_demo_operation",
    "create_demo_rule",
    "create_demo_site",
    "generate_synthetic_forecast_dataset",
    "get_active_forecaster",
    "predict_maintenance_ai",
    "set_active_forecaster",
]
