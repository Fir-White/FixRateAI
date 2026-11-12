"""Load only a trusted artifact matching the supported runtime and manifest."""
import hashlib
from pathlib import Path
from ml_service.app.core.config import settings
from .features import FEATURE_NAMES
from .manifest import ModelManifest
from .model import RandomForestForecaster


def load_verified_forecaster(directory=None):
    directory=Path(directory) if directory is not None else settings.artifacts_path
    manifest=ModelManifest.load(directory / "artifact_manifest.json")
    artifact=directory / "rf_model.joblib"
    checksum=hashlib.sha256(artifact.read_bytes()).hexdigest()
    expected_ref=f"{settings.rf_model_ref_prefix}:{checksum[:16]}"
    if (manifest.schema_version != "maintenance-0.1" or manifest.method_version != settings.rf_method_version
            or manifest.feature_schema_version != settings.rf_feature_schema_version
            or manifest.data_origin != "synthetic_demo" or manifest.model_ref != expected_ref
            or manifest.artifact_sha256 != checksum):
        raise ValueError("RF manifest is incompatible with the runtime")
    model=RandomForestForecaster.from_file(artifact)
    if not model.is_fitted or model.model.n_features_in_ != len(FEATURE_NAMES):
        raise ValueError("RF feature count is incompatible with the runtime")
    return model
