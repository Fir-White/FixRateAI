"""Bridge condition evidence to the canonical maintenance-0.1 forecast DTO."""
from __future__ import annotations

import json
from uuid import uuid4
from zoneinfo import ZoneInfo
from .condition import ConditionRequest, Evidence, assess_condition
from .synthetic import compute_snapshot_hash
from ml_service.app.schemas import ForecastSnapshot, ForecastResult, Uncertainty


def predict_condition_for_snapshot(snapshot: ForecastSnapshot, condition: ConditionRequest | None = None) -> ForecastResult:
    """Return a backend/ALG-compatible AI result without copying the regulatory date.

    Supplemental observations must be for the same equipment, origin and cutoff. The
    current DTO has no fields for measurements or remarks; they are supplied separately.
    """
    if compute_snapshot_hash(json.loads(snapshot.model_dump_json())) != snapshot.content_sha256:
        raise ValueError("forecast snapshot hash mismatch")
    if condition is None:
        condition = ConditionRequest(
            data_origin=snapshot.data_origin, equipment_id=str(snapshot.equipment.equipment_id),
            as_of=snapshot.as_of,
            maintenance_history=[Evidence(observed_at=e.performed_at, description=str(e.service_event_id))
                                 for e in snapshot.accepted_events],
            runtime_hours=float(snapshot.runtime_reading.value_hours) if snapshot.runtime_reading else None,
        )
    if (condition.equipment_id != str(snapshot.equipment.equipment_id)
            or condition.data_origin != snapshot.data_origin or condition.as_of != snapshot.as_of):
        raise ValueError("condition evidence does not match forecast snapshot")
    recommendation = assess_condition(condition)
    # No customer-trained model exists. Do not translate a heuristic to an AI date.
    local_date = snapshot.as_of.astimezone(ZoneInfo(snapshot.site.timezone)).date()
    return ForecastResult(
        schema_version="maintenance-0.1", data_origin=snapshot.data_origin,
        result_id=uuid4(), run_id=uuid4(), snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot.content_sha256, equipment_id=snapshot.equipment.equipment_id,
        binding_id=snapshot.binding_id, as_of=snapshot.as_of, method="ai",
        method_version="condition-evidence-v1", model_ref=None, status="unavailable",
        recommended_date=None, mandatory_due_date=snapshot.mandatory_due_date,
        runtime_due_at_hours=snapshot.runtime_due_at_hours,
        overdue=bool(snapshot.mandatory_due_date and local_date > snapshot.mandatory_due_date),
        uncertainty=Uncertainty(kind="unknown", lower_date=None, upper_date=None, calibrated=False,
                                note=recommendation.uncertainty),
        explanation=recommendation.rationale,
        warnings=[f"EVIDENCE_PRIORITY_{recommendation.risk_level.upper()}",
                  "EVIDENCE_COMPLETENESS_ONLY", *(["SYNTHETIC_DATA"] if snapshot.data_origin == "synthetic_demo" else [])],
        error_code=recommendation.error, elapsed_ms=0,
    )
