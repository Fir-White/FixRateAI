import json
import time
from pathlib import Path
from ml_service.app.forecast.api import invoke
from ml_service.app.forecast.condition import ConditionRequest, assess_condition


def payload(**updates):
    data = {"data_origin": "synthetic_demo", "equipment_id": "DEMO-1", "as_of": "2026-10-30T12:00:00Z"}
    data.update(updates)
    return json.dumps(data)


def test_empty_data_does_not_create_date():
    result = invoke(payload())
    assert result.status == "insufficient_data" and result.suggested_date is None
    assert not result.data_quality.sufficient


def test_condition_evidence_does_not_claim_trained_model():
    evidence = {"observed_at": "2026-10-29T12:00:00Z", "description": "DEMO", "severity": "critical"}
    req = ConditionRequest.model_validate_json(payload(maintenance_history=[evidence], remarks=[evidence],
        runtime_hours=50, measurements=[{"observed_at": evidence["observed_at"], "name": "pressure", "value": 2, "unit": "bar"}]))
    result = assess_condition(req)
    assert result.status == "unavailable" and result.risk_level == "high" and result.suggested_date is None
    assert result.data_quality.sufficient and result.error == "MODEL_NOT_READY"


def test_bad_json_future_evidence_and_bad_response():
    assert invoke("{").error == "INVALID_INPUT"
    assert invoke(payload(remarks=[{"observed_at": "2027-01-01T00:00:00Z", "description": "future"}])).error == "INVALID_INPUT"
    assert invoke(payload(), provider=lambda _: "not json").error == "INVALID_RESPONSE"


def test_timeout_is_reported():
    def slow(_):
        time.sleep(0.05)
    assert invoke(payload(), provider=slow, timeout_seconds=0.001).error == "TIMEOUT"


def test_documented_demo_example():
    examples = json.loads((Path(__file__).resolve().parents[2] / "docs/ml/forecast_examples.json").read_text(encoding="utf-8"))
    assert invoke(json.dumps(examples["condition_request"])).model_dump(mode="json") == examples["condition_response"]
