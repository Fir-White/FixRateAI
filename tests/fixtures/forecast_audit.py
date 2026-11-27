"""Validated contract fixtures for the legacy forecast audit, without a CLI dependency.

The customer origin flag exercises policy branches only: these are synthetic
test inputs, not a customer data set or evidence of model quality.
"""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from uuid import uuid4

from app.orchestrator.forecast import forecast_result
from app.schemas.maintenance import ForecastSnapshot, Uncertainty
from app.scheduling.schemas import SchedulingBinding
from ml_service.app.forecast.synthetic import compute_snapshot_hash

ROOT = Path(__file__).resolve().parents[2]


def rehash(snapshot, **changes):
    payload = json.loads(snapshot.model_dump_json())
    payload.update(changes)
    # JSON serialization validates date/time, origin and current optional fields.
    validated = ForecastSnapshot.model_validate_json(json.dumps(payload))
    payload = json.loads(validated.model_dump_json())
    payload['content_sha256'] = compute_snapshot_hash(payload)
    return ForecastSnapshot.model_validate_json(json.dumps(payload))


def inputs(origin='synthetic_demo'):
    request = deepcopy(json.loads((ROOT/'tests/fixtures/scheduling/examples.json').read_text(encoding='utf-8'))['request'])
    row = request['bindings'][0]
    for entity in ('binding', 'equipment', 'operation', 'rule'):
        row[entity]['data_origin'] = origin
    request['site']['data_origin'] = origin
    row['rule'].update(calendar_unit='month', interval=1, anchor_date='2026-11-10', allowed_lead_days=9,
                       source_text='TEST ONLY: explicit monthly policy anchored on November 10')
    item = SchedulingBinding.model_validate_json(json.dumps(row))
    snapshot = ForecastSnapshot.model_validate_json(json.dumps(dict(
        schema_version=request['schema_version'], data_origin=origin, snapshot_id=str(uuid4()),
        content_sha256='0'*64, binding_id=str(item.binding.binding_id), binding_revision=item.binding.revision,
        site=request['site'], equipment=row['equipment'], operation=row['operation'], rule=row['rule'],
        as_of='2026-11-01T08:00:00+05:00', horizon_end='2027-11-01', earliest_date='2026-11-01',
        mandatory_due_date='2026-11-10', runtime_due_at_hours=None, accepted_events=[], runtime_reading=None,
        feature_schema_version='rf-features-v1')))
    return rehash(snapshot), item


def ai_value(snapshot, day='2026-11-10', *, calibrated=False):
    value = forecast_result(snapshot, uuid4(), 'ai', status='ok', day=date.fromisoformat(day),
                            explanation='TEST ONLY provider result', model_ref='synthetic_demo:audit-fixture-v2')
    uncertainty = Uncertainty(kind='deterministic' if calibrated else 'tree_dispersion',
        lower_date=value.recommended_date, upper_date=value.recommended_date, calibrated=calibrated,
        note='Contract fixture only; no real calibration or model quality claim')
    return value.model_copy(update={'uncertainty': uncertainty})
