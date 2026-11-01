"""ML Service configuration and constants."""
from pathlib import Path
from pydantic import BaseModel, Field

ML_SERVICE_DIR = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ML_SERVICE_DIR / "var" / "artifacts"


class MLConfig(BaseModel):
    # Forecasting settings
    rf_method_version: str = "rf-days-v1"
    rf_feature_schema_version: str = "rf-features-v1"
    rf_model_ref_prefix: str = "synthetic_demo:rf"
    random_seed: int = 42
    n_estimators: int = 100
    max_depth: int = 6
    min_samples_split: int = 2
    
    # Uncertainty settings (10th and 90th percentiles for tree dispersion)
    percentile_lower: float = 10.0
    percentile_upper: float = 90.0

    # CV / CLIP settings
    clip_model_name: str = "openai/clip-vit-base-patch32"
    clip_revision: str = "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"
    clip_fallback_model_name: str = "openai/clip-vit-base-patch16"
    prompt_set_version: str = "demo-clean-pairs-v1"
    image_max_bytes: int = 10_485_760
    image_max_pixels: int = 20_000_000
    laplacian_variance_threshold: float = 100.0
    brightness_min: float = 15.0
    brightness_max: float = 245.0
    clip_delta_threshold: float = 0.25

    # Storage paths
    artifacts_path: Path = Field(default=ARTIFACTS_DIR)


settings = MLConfig()
