from datetime import date
import json
import time
from uuid import uuid4

import pytest

from app.orchestrator import compare_forecasts, decide
from app.orchestrator.forecast import bounded_ai, algorithmic_forecast
from ml_service.app.forecast.synthetic import compute_snapshot_hash
from scripts.verify_orchestration import inputs, ai_value, scenarios, verify


@pytest.mark.parametrize('name,provider,status,selected',scenarios())
def test_forecast_safety_scenarios(name,provider,status,selected):
    snapshot,item=inputs()
    before=snapshot.model_dump_json()
    a,b,d=compare_forecasts(snapshot,item,provider,timeout_seconds=0.005 if name=='timeout' else 1)
    assert snapshot.model_dump_json()==before
    assert a.method=='algorithmic' and a.method_version=='calendar-rules-v2'
    assert a.result_id!=b.result_id and a.snapshot_sha256==b.snapshot_sha256==snapshot.content_sha256
    assert d.status==status and str(d.selected_date)==selected
    assert d.selected_date<=snapshot.mandatory_due_date


def test_report_scenarios_are_executable():
    assert len(verify())==12


@pytest.mark.parametrize('kind', ['daily','quarter','annual'])
def test_algorithmic_forecast_really_uses_calendar_rules(kind):
    snapshot,item=inputs()
    if kind=='daily': rule=item.rule.model_copy(update=dict(calendar_unit='day',interval=1,allowed_lead_days=0))
    elif kind=='quarter': rule=item.rule.model_copy(update=dict(interval=3,anchor_date=date(2026,8,10)))
    else: rule=item.rule.model_copy(update=dict(kind='explicit_dates',interval=None,calendar_unit=None,anchor_date=None,basis=None,
        explicit_dates=[date(2026,m,10) for m in (1,3,5,8,11)],yearly_count=5))
    item=item.model_copy(update={'rule':rule})
    snapshot=snapshot.model_copy(update={'rule':rule})
    result=algorithmic_forecast(snapshot,item,uuid4())
    assert result.status=='ok' and result.recommended_date==date(2026,11,10)


def test_unconfirmed_rule_cannot_be_rescued_by_ai():
    snapshot,item=inputs()
    rule=item.rule.model_copy(update={'confirmed':False})
    item=item.model_copy(update={'rule':rule})
    snapshot=snapshot.model_copy(update={'rule':rule})
    snapshot=snapshot.model_copy(update={'content_sha256':compute_snapshot_hash(json.loads(snapshot.model_dump_json()))})
    a,b,d=compare_forecasts(snapshot,item,lambda s:ai_value(s))
    assert a.status=='needs_input' and d.status=='needs_input' and d.selected_date is None


def test_mixed_result_identity_requires_manual_review():
    snapshot,item=inputs()
    a,b,_=compare_forecasts(snapshot,item,lambda s:ai_value(s))
    for field,value in [('snapshot_id',uuid4()),('snapshot_sha256','1'*64),('run_id',uuid4()),('binding_id',uuid4())]:
        result=decide(snapshot,a,b.model_copy(update={field:value}))
        assert result.status=='manual_review' and result.selected_date is None


def test_tampered_snapshot_hash_is_rejected():
    snapshot,item=inputs()
    with pytest.raises(ValueError,match='hash'):
        compare_forecasts(snapshot.model_copy(update={'content_sha256':'1'*64}),item,lambda s:ai_value(s))


def test_algorithm_does_not_use_equipment_or_history_outside_the_shared_snapshot():
    snapshot,item=inputs()
    changed=item.model_copy(update={'equipment':item.equipment.model_copy(update={'revision':2})})
    assert algorithmic_forecast(snapshot,changed,uuid4()).error_code=='BINDING_MISMATCH'


@pytest.mark.parametrize('valid',[True,False])
def test_customer_early_move_requires_the_prediction_to_be_inside_calibrated_bounds(valid):
    snapshot,item=inputs('customer')
    def provider(value):
        answer=ai_value(value,'2026-11-05',calibrated=True)
        if not valid:
            answer=answer.model_copy(update={'uncertainty':answer.uncertainty.model_copy(update={
                'lower_date':date(2026,11,6),'upper_date':date(2026,11,7)})})
        return answer
    _,_,decision=compare_forecasts(snapshot,item,provider)
    assert decision.status==('selected' if valid else 'fallback')
    assert decision.selected_date==date(2026,11,5 if valid else 10)


def test_worker_capacity_is_bounded_and_recovers_after_timeouts():
    from threading import Event
    gate=Event()
    snapshot,_=inputs()
    def blocked(s):
        gate.wait(0.3)
        return ai_value(s)
    # Allow the short report timeout fixture to release its slot first.
    time.sleep(0.06)
    try:
        assert bounded_ai(snapshot,uuid4(),blocked,timeout_seconds=0.005).error_code=='TIMEOUT'
        assert bounded_ai(snapshot,uuid4(),blocked,timeout_seconds=0.005).error_code=='TIMEOUT'
        assert bounded_ai(snapshot,uuid4(),blocked,timeout_seconds=0.005).error_code=='AI_BUSY'
    finally: gate.set()
    time.sleep(0.02)
    assert bounded_ai(snapshot,uuid4(),lambda s:ai_value(s)).status=='ok'


@pytest.mark.parametrize('origin,kind,calibrated,expected',[
    ('customer','unknown',False,'fallback'),
    ('customer','tree_dispersion',False,'fallback'),
    ('synthetic_demo','unknown',False,'fallback'),
    ('synthetic_demo','tree_dispersion',False,'selected'),
    ('customer','deterministic',True,'selected'),
])
def test_qa04_uncertainty_follows_explicit_policy_without_invented_confidence_threshold(origin,kind,calibrated,expected):
    from app.schemas.maintenance import Uncertainty
    from app.orchestrator.decision import POLICY_VERSION
    snapshot,item=inputs(origin)
    def provider(value):
        candidate=ai_value(value,'2026-11-05',calibrated=calibrated)
        return candidate.model_copy(update={'uncertainty':Uncertainty(kind=kind,
            lower_date=None if kind=='unknown' else date(2026,11,5),
            upper_date=None if kind=='unknown' else date(2026,11,5),calibrated=calibrated,
            note='QA04 uncertainty fixture; no empirical confidence score')})
    algorithmic,ai,decision=compare_forecasts(snapshot,item,provider)
    assert decision.policy_version==POLICY_VERSION=='maintenance-orchestrator-v1'
    assert decision.status==expected
    assert decision.selected_date==(date(2026,11,10) if expected=='fallback' else date(2026,11,5))
    assert ai.recommended_date==date(2026,11,5) and algorithmic.recommended_date==date(2026,11,10)
    if expected=='fallback': assert 'AI_EARLY_UNSUPPORTED' in decision.reasons[0]
