"""RandomForest Forecaster with tree dispersion uncertainty estimation."""
from __future__ import annotations

import hashlib
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from ml_service.app.core.config import settings


class RandomForestForecaster:
    """RandomForestRegressor predicting days until required maintenance."""

    def __init__(
        self,
        n_estimators: int = settings.n_estimators,
        max_depth: int = settings.max_depth,
        random_state: int = settings.random_seed,
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.random_state = random_state
        self.model: RandomForestRegressor | None = None
        self._artifact_sha256: str | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RandomForestForecaster":
        """Train the random forest regressor on feature matrix X and targets y."""
        self.model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            random_state=self.random_state,
        )
        self.model.fit(X, y)
        self._artifact_sha256 = None
        return self

    @property
    def is_fitted(self) -> bool:
        return self.model is not None

    def predict_with_dispersion(
        self,
        x: np.ndarray,
        p_lower: float = settings.percentile_lower,
        p_upper: float = settings.percentile_upper,
    ) -> tuple[float, float, float]:
        """Predict expected days and 10th/90th tree dispersion bounds.

        Args:
            x: 1D feature array of shape (6,)
            p_lower: lower percentile (e.g. 10.0)
            p_upper: upper percentile (e.g. 90.0)

        Returns:
            (point_prediction_days, lower_bound_days, upper_bound_days)
        """
        if not self.is_fitted:
            raise RuntimeError("Model is not fitted yet.")

        x_2d = x.reshape(1, -1) if x.ndim == 1 else x
        # High-performance tree dispersion: direct Cython tree_.predict traversal bypasses per-tree sklearn overhead
        try:
            x_f32 = np.ascontiguousarray(x_2d, dtype=np.float32)
            tree_predictions = np.fromiter(
                (tree.tree_.predict(x_f32)[0, 0] for tree in self.model.estimators_),
                dtype=np.float64,
                count=len(self.model.estimators_),
            )
        except (AttributeError, IndexError):
            tree_predictions = np.array([tree.predict(x_2d)[0] for tree in self.model.estimators_])

        point_pred = float(np.mean(tree_predictions))
        lower_bound = float(np.percentile(tree_predictions, p_lower))
        upper_bound = float(np.percentile(tree_predictions, p_upper))

        # Enforce ordering lower <= point <= upper within integer tolerance
        lower_bound = min(lower_bound, point_pred)
        upper_bound = max(upper_bound, point_pred)

        return point_pred, lower_bound, upper_bound

    def warmup(self) -> None:
        """Run a dry-run prediction to prime memory and CPU caches."""
        if self.is_fitted:
            dummy = np.zeros(6, dtype=np.float64)
            self.predict_with_dispersion(dummy)

    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray) -> dict[str, float]:
        """Evaluate model performance on test set."""
        if not self.is_fitted:
            raise RuntimeError("Model is not fitted yet.")
        preds = self.model.predict(X_test)
        mae = float(mean_absolute_error(y_test, preds))
        mse = float(mean_squared_error(y_test, preds))
        late_ratio = float(np.mean(preds > y_test))
        return {
            "mae_days": mae,
            "mse_days": mse,
            "late_prediction_ratio": late_ratio,
            "n_test_samples": float(len(y_test)),
        }

    def save(self, filepath: Path | str) -> str:
        """Serialize model to disk and return its SHA-256 hash."""
        if not self.is_fitted:
            raise RuntimeError("Cannot save an unfitted model.")
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, path)

        with open(path, "rb") as f:
            self._artifact_sha256 = hashlib.sha256(f.read()).hexdigest()
        return self._artifact_sha256

    def load(self, filepath: Path | str) -> "RandomForestForecaster":
        """Load serialized model from disk and compute its SHA-256 hash."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        self.model = joblib.load(path)
        with open(path, "rb") as f:
            self._artifact_sha256 = hashlib.sha256(f.read()).hexdigest()
        return self

    @classmethod
    def from_file(cls, filepath: Path | str) -> "RandomForestForecaster":
        """Instantiate and load model from file."""
        return cls().load(filepath)

    @property
    def artifact_sha256(self) -> str | None:
        return self._artifact_sha256
