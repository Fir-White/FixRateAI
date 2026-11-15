"""Faults in derived forecast fields cannot overrule canonical snapshots or unknown norms."""
from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from app.orchestrator.decision import decide
from app.orchestrator.forecast import algorithmic_forecast,bounded_ai
from app.schemas.maintenance import Uncertainty
from tests.fixtures.forecast_audit import inputs,ai_value,rehash

@pytest.mark.parametrize('as_of,claimed,expected',[
    ('2026-11-01T08:00:00+05:00',True,False),
    ('2026-11-10T08:00:00+05:00',True,False),
    ('2026-11-11T08:00:00+05:00',False,True),
    ('2026-11-09T20:00:00Z',True,False),
    ('2026-11-10T20:00:00Z',False,True),
])
def test_provider_overdue_is_recomputed_at_object_local_day(as_of,claimed,expected):
    snapshot,_=inputs('customer');snapshot=rehash(snapshot,as_of=as_of)
    result=bounded_ai(snapshot,uuid4(),lambda s:ai_value(s).model_copy(update={'overdue':claimed}))
    assert result.status=='ok' and result.overdue is expected

@pytest.mark.parametrize('lower,upper,calibrated',[
    ('2026-11-05','2026-11-05',True),('2026-11-04','2026-11-06',True),
    (None,None,True),('2026-11-05','2026-11-05',False),('2026-11-01','2026-11-09',True),
])
def test_unknown_kind_never_proves_an_early_customer_date(lower,upper,calibrated):
    snapshot,binding=inputs('customer');algorithmic=algorithmic_forecast(snapshot,binding,uuid4())
    uncertainty=Uncertainty(kind='unknown',lower_date=date.fromisoformat(lower) if lower else None,
        upper_date=date.fromisoformat(upper) if upper else None,calibrated=calibrated,note='TEST ONLY untrusted claim')
    result=bounded_ai(snapshot,algorithmic.run_id,lambda s:ai_value(s,'2026-11-05').model_copy(update={'uncertainty':uncertainty}))
    decision=decide(snapshot,algorithmic,result)
    assert decision.status=='fallback' and decision.selected_date==date(2026,11,10)

@pytest.mark.parametrize('forged_day',[2,5,7,8,9])
def test_in_window_algorithmic_tampering_is_not_a_fallback_source(forged_day):
    from app.orchestrator.forecast import forecast_result
    snapshot,binding=inputs();algorithmic=algorithmic_forecast(snapshot,binding,uuid4())
    changed=algorithmic.model_copy(update={'recommended_date':date(2026,11,forged_day)})
    unavailable=bounded_ai(snapshot,algorithmic.run_id,lambda s:forecast_result(s,uuid4(),'ai',status='unavailable',error='MODEL_NOT_READY',explanation='TEST ONLY unavailable'))
    result=decide(snapshot,changed,unavailable)
    assert result.status=='fallback' and result.selected_date==date(2026,11,10)
    assert 'ALGORITHMIC_DATE_MISMATCH' in result.reasons[0]

@pytest.mark.parametrize('invalid',[None,'2026-11-05',5,datetime(2026,11,5,tzinfo=timezone.utc)])
def test_invalid_algorithmic_date_is_manual_review_not_a_crash(invalid):
    snapshot,binding=inputs();algorithmic=algorithmic_forecast(snapshot,binding,uuid4())
    ai=bounded_ai(snapshot,algorithmic.run_id,ai_value)
    result=decide(snapshot,algorithmic.model_copy(update={'recommended_date':invalid}),ai)
    assert result.status=='manual_review' and result.selected_date is None

def test_provider_cannot_invent_runtime_threshold_or_own_timing():
    snapshot,_=inputs();assert snapshot.runtime_due_at_hours is None
    result=bounded_ai(snapshot,uuid4(),lambda s:ai_value(s).model_copy(update={'runtime_due_at_hours':Decimal('999'),'elapsed_ms':999999}))
    assert result.status=='ok' and result.runtime_due_at_hours is None and result.elapsed_ms!=999999

@pytest.mark.parametrize('norm,unit,duration,expected_hours,expected_minutes',[
    (None,'unconfirmed',None,None,None),('2','unconfirmed',60,None,0),
    ('2','person_hour',None,0,None),('2','person_hour',60,0,0),('2','elapsed_hour',60,0,0),
])
def test_empty_month_distinguishes_known_zero_from_unknown(norm,unit,duration,expected_hours,expected_minutes):
    from tests.backend.test_schedule_audit import request,run,FIVE_PER_YEAR,OPERATIONS
    payload=request(FIVE_PER_YEAR,OPERATIONS['1.4'],month=11)
    payload['bindings'][0]['operation'].update(raw_norm_value=norm,norm_unit=unit,planning_duration_minutes=duration,
        duration_basis='TEST ONLY explicit synthetic duration' if duration is not None else None)
    result=run(payload).bindings[0]
    assert result.occurrences==[] and result.status=='ok'
    assert result.total_person_hours==expected_hours and result.total_planning_person_minutes==expected_minutes
