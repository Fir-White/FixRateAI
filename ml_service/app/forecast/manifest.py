"""Model artifact manifest tracking data provenance, hashes, and evaluation metrics."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field


class ModelManifest(BaseModel):
    """Manifest describing a trained model artifact and its provenance."""
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: str = "maintenance-0.1"
    model_ref: str
    method_version: str
    feature_schema_version: str
    data_origin: str = "synthetic_demo"
    dataset_sha256: str
    artifact_sha256: str
    random_seed: int = 42
    trained_at: str
    verified_by: str = "Muhammad (AI Engineer)"
    n_train_samples: int
    n_test_samples: int
    metrics: dict[str, float]
    provenance_notes: str

    def save(self, filepath: Path | str) -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: Path | str) -> "ModelManifest":
        path = Path(filepath)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)
