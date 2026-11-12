import pytest
from ml_service.app.forecast.backend_adapter import predict_condition_for_snapshot
from ml_service.app.forecast.condition import ConditionRequest
from ml_service.app.schemas import ForecastResult


def test_snapshot_to_alg_contract(canonical_example_snapshot):
    snapshot = canonical_example_snapshot
    result = predict_condition_for_snapshot(snapshot)
    restored = ForecastResult.model_validate_json(result.model_dump_json())
    assert restored.method == "ai" and restored.status == "unavailable"
    assert restored.snapshot_id == snapshot.snapshot_id and restored.snapshot_sha256 == snapshot.content_sha256
    assert restored.binding_id == snapshot.binding_id and restored.recommended_date is None
    assert restored.mandatory_due_date == snapshot.mandatory_due_date


def test_reject_mismatched_evidence(canonical_example_snapshot):
    s = canonical_example_snapshot
    condition = ConditionRequest(data_origin=s.data_origin, equipment_id="other", as_of=s.as_of)
    with pytest.raises(ValueError, match="does not match"):
        predict_condition_for_snapshot(s, condition)


def test_reject_tampered_snapshot(canonical_example_snapshot):
    changed = canonical_example_snapshot.model_copy(update={"content_sha256": "0" * 64})
    with pytest.raises(ValueError, match="hash mismatch"):
        predict_condition_for_snapshot(changed)
