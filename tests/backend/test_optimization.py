"""Real CP-SAT and the same hard validator as manual placement."""
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from threading import Event
from uuid import uuid4
import pytest
from ortools.sat.python import cp_model
from app.scheduling.optimization import calculate,Cancelled
from app.schemas.draft_plans import WorkOccurrence,WorkSegment,DraftPolicy
from app.assignment.schemas import Worker
from tests.backend.test_draft_plans import pure_case,moment


def case(count=4,crew=1,continuous=False):
    root,_,people,policy=pure_case()
    root=root.model_copy(update={'interpretation':'CONTINUOUS_WORK' if continuous else 'ALLOWED_WINDOW','total_person_hours':Decimal(3*count),'crew_size':crew})
    segments=[WorkSegment(segment_id=uuid4(),occurrence_id=root.occurrence_id,equipment_ids=root.equipment_ids,person_hours='3') for _ in range(count)]
    if continuous:
        for previous,current in zip(segments,segments[1:]): current.depends_on_segment_ids=[previous.segment_id]
    return dict(options=dict(time_limit_seconds=15,grid_minutes=60),source_snapshot=dict(source={'timezone':'UTC'},input=dict(import_id=str(root.import_id),starts_on='2027-01-01',ends_on='2027-01-10',row_numbers=[8],policy=policy.model_dump(mode='json'))),
        occurrences=[root.model_dump(mode='json')],segments=[s.model_dump(mode='json') for s in segments],resources=dict(as_of=moment(1).isoformat(),workers=[w.model_dump(mode='json') for w in people],equipment_bookings={},equipment_unknown=[]))


def test_optimizer_improves_balance_without_making_work_or_fractional_crews():
    payload=case();result=calculate(payload)
    baseline=result['result']['baseline'];optimized=result['result']['optimized']
    assert baseline['validation']['status']=='valid' and optimized['validation']['status']=='valid'
    assert optimized['coverage_status']=='FEASIBLE' and optimized['solver_status'] in ('OPTIMAL','FEASIBLE')
    assert Decimal(optimized['metrics']['total_person_hours'])==12
    assert optimized['metrics']['peak_daily_utilization']<baseline['metrics']['peak_daily_utilization']
    assert {s['segment_id'] for s in result['optimized_segments']}=={s['segment_id'] for s in payload['segments']}
    assert all(len(s['worker_ids'])==1 for s in result['optimized_segments'])
    assert not result['result']['ready_for_real_plan']


def test_continuous_group_keeps_adjacent_parts_and_one_complete_crew():
    payload=case(2,crew=2,continuous=True);result=calculate(payload)
    variant=result['result']['optimized'];assert variant and variant['validation']['status']=='valid'
    pieces={s['segment_id']:s for s in result['optimized_segments']}
    first,second=[pieces[s['segment_id']] for s in payload['segments']]
    assert first['end_at']==second['start_at'] and set(first['worker_ids'])==set(second['worker_ids']) and len(first['worker_ids'])==2
    assert sum(Decimal(s['person_hours']) for s in pieces.values())==6


def test_locks_remain_exact_and_replan_flag_preserves_existing_placements():
    payload=case(1);segment=payload['segments'][0]
    segment.update(start_at=moment(2,8).isoformat(),end_at=moment(2,11).isoformat(),worker_ids=[payload['resources']['workers'][0]['worker_id']],locked=True)
    payload['options']['replan_existing']=True
    result=calculate(payload)
    assert datetime.fromisoformat(result['optimized_segments'][0]['start_at'])==datetime.fromisoformat(segment['start_at'])
    assert result['optimized_segments'][0]['worker_ids']==segment['worker_ids'] and result['optimized_segments'][0]['locked']
    segment['locked']=False;payload['options']['replan_existing']=False
    result=calculate(payload)
    assert datetime.fromisoformat(result['optimized_segments'][0]['start_at'])==datetime.fromisoformat(segment['start_at']) and result['optimized_segments'][0]['worker_ids']==segment['worker_ids']


def test_missing_roster_capacity_and_qualifications_do_not_turn_into_success():
    payload=case(1);payload['resources']['workers']=[]
    result=calculate(payload);variant=result['result']['optimized']
    assert result['result']['diagnostic_counts']['NO_CANDIDATE']==1
    assert variant is not None and variant['coverage_status']=='INFEASIBLE' and variant['metrics']['covered_occurrences']==0
    payload=case(1);payload['source_snapshot']['input']['policy'].update(capacity_confirmed=False,capacity_status='provisional')
    result=calculate(payload)
    assert result['result']['completion_reason']=='needs_input' and result['result']['optimized'] is None
    payload=case(1);payload['occurrences'][0]['qualifications_confirmed']=False
    assert calculate(payload)['result']['completion_reason']=='needs_input'


def test_unknown_resources_prevent_false_impossibility_proof_and_metrics():
    payload=case(1)
    for worker in payload['resources']['workers']: worker['booking_data_complete']=False
    result=calculate(payload);variant=result['result']['optimized']
    assert not result['result']['model_complete'] and not variant['optimality_proven']
    assert variant['coverage_status']=='UNKNOWN' and variant['metrics']['staff_utilization'] is None


def test_cancelled_calculation_never_returns_applicable_results():
    cancel=Event();cancel.set()
    with pytest.raises(Cancelled): calculate(case(),cancel)


def test_insufficient_skills_cannot_be_filled_by_a_smaller_team():
    payload=case(1,crew=2);skill=str(uuid4());payload['occurrences'][0]['qualification_ids']=[skill]
    payload['resources']['workers'][0]['qualifications']=[dict(skill_id=skill,verified_at=moment(1).isoformat(),valid_until='2027-12-31',validity_required=True)]
    result=calculate(payload);variant=result['result']['optimized']
    assert variant['metrics']['covered_occurrences']==0 and all(not s['worker_ids'] for s in result['optimized_segments'])


def test_model_limits_never_claim_optimality_or_global_infeasibility(monkeypatch):
    import app.scheduling.optimization as module
    monkeypatch.setattr(module,'MAX_CHOICES_PER_GROUP',2)
    result=calculate(case(1));variant=result['result']['optimized']
    assert not result['result']['model_complete'] and result['result']['completion_reason']=='model_limit'
    assert variant is None or not variant['optimality_proven']
