"""Forecasting client providing pure Python inference function predict_maintenance_ai."""
from __future__ import annotations

import time
from datetime import date, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
import numpy as np

from ml_service.app.core.config import settings
from ml_service.app.forecast.features import FeatureExtractor
from ml_service.app.forecast.model import RandomForestForecaster
from ml_service.app.schemas import (
    ForecastResult,
    ForecastSnapshot,
    Uncertainty,
)

# Global in-memory cache for singleton model and feature extractor
_EXTRACTOR = FeatureExtractor()
_FORECASTER: RandomForestForecaster | None = None
_DEFAULT_MODEL_REF = f"{settings.rf_model_ref_prefix}:model-sha-v1"


def set_active_forecaster(forecaster: RandomForestForecaster | None) -> None:
    """Set or unset the active forecaster model."""
    global _FORECASTER
    _FORECASTER = forecaster


def get_active_forecaster() -> RandomForestForecaster | None:
    """Get the active forecaster model."""
    return _FORECASTER


def load_default_forecaster() -> RandomForestForecaster | None:
    """Load default trained RandomForest artifact from disk into memory cache."""
    global _FORECASTER
    artifact_file = settings.artifacts_path / "rf_model.joblib"
    if artifact_file.exists():
        _FORECASTER = RandomForestForecaster.from_file(artifact_file)
        return _FORECASTER
    return None


def predict_maintenance_ai(
    snapshot: ForecastSnapshot,
    forecaster: RandomForestForecaster | None = None,
    model_ref: str | None = None,
    *,
    use_active_model: bool = True,
) -> ForecastResult:
    """Pure Python inference function predicting next maintenance date from a ForecastSnapshot.

    Guarantees:
    - Never raises unhandled exceptions to the caller; returns terminal ForecastResult with status.
    - If customer origin without history or model absent: returns status='unavailable'.
    - If synthetic_demo and model fitted: returns status='ok' with tree_dispersion uncertainty.
    """
    start_time = time.perf_counter()
    active_model = forecaster if forecaster is not None else (_FORECASTER if use_active_model else None)
    effective_model_ref = model_ref or (
        f"{settings.rf_model_ref_prefix}:{active_model.artifact_sha256[:16]}"
        if (active_model and active_model.artifact_sha256)
        else _DEFAULT_MODEL_REF
    )

    site_tz = ZoneInfo(snapshot.site.timezone)
    as_of_local = snapshot.as_of.astimezone(site_tz)
    as_of_date = as_of_local.date()

    # Check overdue relative to as_of
    is_overdue = False
    if snapshot.mandatory_due_date and as_of_date > snapshot.mandatory_due_date:
        is_overdue = True

    # 1. Customer data without model / history -> unavailable
    if snapshot.data_origin == "customer" or active_model is None or not active_model.is_fitted:
        elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        error_code = ("INSUFFICIENT_HISTORY" if not snapshot.accepted_events else "MODEL_NOT_READY") if snapshot.data_origin == "customer" else "MODEL_NOT_READY"
        explanation = (
            "Пригодная модель для данных заказчика не подтверждена; алгоритмический срок не подменяется AI."
            if snapshot.data_origin == "customer"
            else "Модель не загружена; алгоритмический результат не подставлен вместо AI."
        )
        return ForecastResult(
            schema_version="maintenance-0.1",
            data_origin=snapshot.data_origin,
            result_id=uuid4(),
            run_id=uuid4(),
            snapshot_id=snapshot.snapshot_id,
            snapshot_sha256=snapshot.content_sha256,
            equipment_id=snapshot.equipment.equipment_id,
            binding_id=snapshot.binding_id,
            as_of=snapshot.as_of,
            method="ai",
            method_version=settings.rf_method_version,
            model_ref=None,
            status="unavailable",
            recommended_date=None,
            mandatory_due_date=snapshot.mandatory_due_date,
            runtime_due_at_hours=snapshot.runtime_due_at_hours,
            overdue=is_overdue,
            uncertainty=Uncertainty(
                kind="unknown",
                lower_date=None,
                upper_date=None,
                calibrated=False,
                note="Разброс деревьев на синтетике; достоверность на заказчике не оценена.",
            ),
            explanation=explanation,
            warnings=["SYNTHETIC_DATA"] if snapshot.data_origin == "synthetic_demo" else ["CUSTOMER_UNCONFIRMED"],
            error_code=error_code,
            elapsed_ms=elapsed_ms,
        )

    # 2. Synthetic demo with fitted model -> compute prediction
    try:
        features = _EXTRACTOR.extract_features(snapshot)
        point_days, lower_days, upper_days = active_model.predict_with_dispersion(features)

        # Compute recommended calendar dates
        rec_delta = max(1, int(round(point_days)))
        low_delta = max(1, int(round(lower_days)))
        up_delta = max(low_delta, int(round(upper_days)))

        recommended_date = as_of_date + timedelta(days=rec_delta)
        lower_date = as_of_date + timedelta(days=low_delta)
        upper_date = as_of_date + timedelta(days=up_delta)

        # Enforce consistency lower_date <= recommended_date <= upper_date
        if lower_date > recommended_date:
            lower_date = recommended_date
        if upper_date < recommended_date:
            upper_date = recommended_date

        elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))

        return ForecastResult(
            schema_version="maintenance-0.1",
            data_origin="synthetic_demo",
            result_id=uuid4(),
            run_id=uuid4(),
            snapshot_id=snapshot.snapshot_id,
            snapshot_sha256=snapshot.content_sha256,
            equipment_id=snapshot.equipment.equipment_id,
            binding_id=snapshot.binding_id,
            as_of=snapshot.as_of,
            method="ai",
            method_version=settings.rf_method_version,
            model_ref=effective_model_ref,
            status="ok",
            recommended_date=recommended_date,
            mandatory_due_date=snapshot.mandatory_due_date,
            runtime_due_at_hours=snapshot.runtime_due_at_hours,
            overdue=is_overdue,
            uncertainty=Uncertainty(
                kind="tree_dispersion",
                lower_date=lower_date,
                upper_date=upper_date,
                calibrated=False,
                note="Разброс деревьев на синтетике; достоверность на заказчике не оценена.",
            ),
            explanation="Учебный прогноз по синтетическим признакам.",
            warnings=["SYNTHETIC_DATA"],
            error_code=None,
            elapsed_ms=elapsed_ms,
        )

    except Exception as exc:
        # Graceful failure: return valid terminal ForecastResult with status='failed'
        elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        return ForecastResult(
            schema_version="maintenance-0.1",
            data_origin=snapshot.data_origin,
            result_id=uuid4(),
            run_id=uuid4(),
            snapshot_id=snapshot.snapshot_id,
            snapshot_sha256=snapshot.content_sha256,
            equipment_id=snapshot.equipment.equipment_id,
            binding_id=snapshot.binding_id,
            as_of=snapshot.as_of,
            method="ai",
            method_version=settings.rf_method_version,
            model_ref=None,
            status="failed",
            recommended_date=None,
            mandatory_due_date=snapshot.mandatory_due_date,
            runtime_due_at_hours=snapshot.runtime_due_at_hours,
            overdue=is_overdue,
            uncertainty=Uncertainty(
                kind="unknown",
                lower_date=None,
                upper_date=None,
                calibrated=False,
                note="Аварийное завершение вычисления AI-прогноза.",
            ),
            explanation=f"Ошибка инференса: {type(exc).__name__}",
            warnings=["COMPUTATION_ERROR"],
            error_code="AI_INFERENCE_FAILED",
            elapsed_ms=elapsed_ms,
        )
