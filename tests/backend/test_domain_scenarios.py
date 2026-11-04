"""Analyst fixtures execute against the same generator as the web calendar."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from app.scheduling import CalendarGenerationRequest,generate_month

ROOT=Path(__file__).resolve().parents[2]
CASES=json.loads((ROOT/'tests/fixtures/domain/maintenance_cases.json').read_text(encoding='utf-8'))['test_fixtures']


SOURCE_OPERATIONS = {
    '1.1': (1, '1.0'), '1.2': (1, '1.0'), '1.3': (1, '1.0'),
    '1.4': (2, '60.0'), '1.5': (1, '48.0'), '1.6': (1, '30.0'),
}
POLICIES = {'day':'calendar-rules-v2:day', 'quarter':'calendar-rules-v2:quarter-end',
            'month':'calendar-rules-v2:anchored-month-interval', 'yearly_count':'calendar-rules-v2:yearly-count'}


def scenario_request(case):
    from uuid import NAMESPACE_URL, uuid5
    request=deepcopy(json.loads((ROOT/'tests/fixtures/scheduling/examples.json').read_text(encoding='utf-8'))['request'])
    values=case['input_data']
    request['query'].update(year=values['year'],month=values['month'])
    request['as_of']=f"{values['year']}-{values['month']:02d}-01T00:00:00+05:00"
    item=request['bindings'][0]
    item['binding']['effective_from']=values['active_from']
    item['equipment']['commissioned_on']=values['active_from']
    operation_id=str(uuid5(NAMESPACE_URL,'qa04:operation:'+case['operation_id']))
    item['operation'].update(operation_version_id=operation_id,code=case['operation_id'],
        maintenance_type='ТО1' if case['operation_id'] in ('1.1','1.2','1.3') else 'ТО2',
        source_ref=case['source_ref'],crew_size=case['expected_workers'],raw_norm_value=case['raw_norm_value'],
        norm_unit=case['norm_unit'],planning_duration_minutes=None,duration_basis=None)
    item['binding']['operation_version_id']=operation_id
    item['rule'].update(kind='calendar_pattern',interval=None,calendar_unit=None,anchor_date=None,basis=None,
        explicit_dates=[],yearly_count=None,pattern=values['pattern'],source_ref=case['policy_ref'])
    item['assumptions']=[case['policy_explanation']]
    return request


@pytest.mark.parametrize('case',CASES,ids=lambda row:row['test_id'])
def test_analyst_calendar_fixture(case):
    request=scenario_request(case)
    operation=request['bindings'][0]['operation']
    assert operation['code']==case['operation_id']
    assert case['policy_id']==POLICIES[case['input_data']['pattern']['frequency']]
    assert case['policy_ref'] and case['policy_explanation'] and case['data_origin']=='synthetic_demo'
    workers,norm=SOURCE_OPERATIONS[case['operation_id']]
    assert (case['expected_workers'],Decimal(case['raw_norm_value']))==(workers,Decimal(norm))
    assert case['norm_unit']=='unconfirmed'
    result=generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(request)))
    assert result.method_version=='calendar-rules-v2'
    assert [str(o.occurrence.occurrence_date) for o in result.bindings[0].occurrences]==case['expected_dates']
    assert all(str(row.operation_version_id)==operation['operation_version_id'] for row in result.calendar.items)
    assert all(row.crew_size==workers and row.raw_norm_value==Decimal(norm) for row in result.calendar.items)
    assert result.bindings[0].is_assumption is case['is_assumption'] is True
    assert all(o.is_assumption for o in result.bindings[0].occurrences)
    assert result.bindings[0].total_person_hours is None
    assert result.bindings[0].total_planning_person_minutes is None


def test_domain_json_examples_share_the_canonical_contracts():
    from app.schemas.maintenance import OperationVersion,RecurrenceRule,Task,Equipment
    from app.schemas.maintenance_api import EquipmentOperationBindingResponse
    for name,model in [('operation_template',OperationVersion),('regulation',RecurrenceRule),('maintenance_task',Task)]:
        model.model_validate_json((ROOT/f'tests/fixtures/domain/{name}.json').read_text(encoding='utf-8'))
    relation=json.loads((ROOT/'tests/fixtures/domain/operation_to_equipment_links.json').read_text(encoding='utf-8'))
    operation=OperationVersion.model_validate_json(json.dumps(relation['operation']))
    rule=RecurrenceRule.model_validate_json(json.dumps(relation['rule']))
    equipment={row['equipment_id']:Equipment.model_validate_json(json.dumps(row)) for row in relation['equipment']}
    for raw in relation['bindings']:
        binding=EquipmentOperationBindingResponse.model_validate_json(json.dumps(raw))
        assert str(binding.equipment_id) in equipment
        assert binding.operation_version_id==operation.operation_version_id and binding.rule_version_id==rule.rule_version_id


def test_qa04_fixtures_cover_all_six_source_operations():
    assert {row['operation_id'] for row in CASES} == {'1.1','1.2','1.3','1.4','1.5','1.6'}


def test_qa04_source_workbook_is_the_reviewed_version():
    import hashlib
    source=json.loads((ROOT/'tests/fixtures/domain/maintenance_cases.json').read_text(encoding='utf-8'))['source_workbook']
    assert hashlib.sha256((ROOT/source['path']).read_bytes()).hexdigest()==source['sha256']


@pytest.mark.parametrize('case',CASES,ids=lambda row:row['test_id'])
def test_qa04_missing_dates_never_manufacture_a_calendar(case):
    data=scenario_request(case)
    data['bindings'][0]['equipment']['commissioned_on']=None
    data['bindings'][0]['binding']['effective_from']=None
    result=generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(data)))
    assert result.bindings[0].status=='needs_input'
    assert result.bindings[0].error_code=='ACTIVATION_DATE_MISSING'
    assert result.calendar.items==[] and result.bindings[0].total_person_hours is None


@pytest.mark.parametrize('case',CASES,ids=lambda row:row['test_id'])
def test_qa04_unconfirmed_policy_never_creates_a_schedule(case):
    data=scenario_request(case);data['bindings'][0]['rule']['confirmed']=False
    result=generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(data)))
    assert result.bindings[0].error_code=='RULE_UNCONFIRMED'
    assert result.calendar.items==[] and result.bindings[0].total_planning_person_minutes is None


@pytest.mark.parametrize('case',CASES,ids=lambda row:row['test_id'])
def test_qa04_overdue_recalculation_keeps_dates_ids_and_norms(case):
    from datetime import date,timedelta
    data=scenario_request(case)
    due=date.fromisoformat(case['expected_dates'][0])
    data['as_of']=due.isoformat()+'T23:59:59+05:00'
    before=generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(data)))
    data['as_of']=(due+timedelta(days=1)).isoformat()+'T00:00:00+05:00'
    after=generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(data)))
    assert before.calendar==after.calendar
    assert not before.bindings[0].occurrences[0].deadline_passed
    assert after.bindings[0].occurrences[0].deadline_passed
    assert all(row.planned_task_id is None and row.status=='draft' for row in after.calendar.items)


@pytest.mark.parametrize('workers,expected',[(1,'unavailable'),(2,'ok')])
def test_qa04_operation_14_needs_two_workers_without_guessing_duration(workers,expected):
    from app.assignment import AssignmentRequest,select_crew
    from tests.backend.test_assignment import payload
    case=next(case for case in CASES if case['operation_id']=='1.4')
    calendar=generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(scenario_request(case))))
    item=calendar.calendar.items[0]
    assert item.crew_size==2 and item.raw_norm_value==Decimal('60')
    assert item.planning_duration_minutes is None and item.norm_unit=='unconfirmed'
    # The separate assignment fixture explicitly confirms 60 minutes; norm 60 does not supply duration.
    data=payload();data.update(crew_size=item.crew_size,workers=payload()['workers'][:workers])
    result=select_crew(AssignmentRequest.model_validate_json(json.dumps(data)))
    assert result.status==expected
    if workers==1: assert result.command is None
    else: assert len(result.command.executor_ids)==2


@pytest.mark.parametrize('case',CASES,ids=lambda row:row['test_id'])
def test_qa04_two_forecasts_preserve_each_operation_and_fallback(case):
    from datetime import date,timedelta
    from uuid import uuid4
    from app.orchestrator import compare_forecasts
    from app.orchestrator.forecast import forecast_result
    from app.schemas.maintenance import ForecastSnapshot,ForecastResult,OrchestrationDecision
    from ml_service.app.forecast.synthetic import compute_snapshot_hash
    data=scenario_request(case)
    request=CalendarGenerationRequest.model_validate_json(json.dumps(data))
    binding=request.bindings[0]
    generated=generate_month(request).bindings[0].occurrences[0].occurrence
    raw=dict(schema_version='maintenance-0.1',data_origin='synthetic_demo',snapshot_id=str(uuid4()),content_sha256='0'*64,
        binding_id=str(binding.binding.binding_id),binding_revision=binding.binding.revision,site=data['site'],
        equipment=data['bindings'][0]['equipment'],operation=data['bindings'][0]['operation'],rule=data['bindings'][0]['rule'],
        as_of=data['as_of'],horizon_end=(date.fromisoformat(case['expected_dates'][0])+timedelta(days=366)).isoformat(),
        earliest_date=str(generated.earliest_date),mandatory_due_date=str(generated.mandatory_due_date),
        runtime_due_at_hours=None,accepted_events=[],runtime_reading=None,feature_schema_version='rf-features-v1')
    snapshot=ForecastSnapshot.model_validate_json(json.dumps(raw))
    snapshot=snapshot.model_copy(update={'content_sha256':compute_snapshot_hash(json.loads(snapshot.model_dump_json()))})
    before=snapshot.model_dump_json()
    algorithmic,ai,decision=compare_forecasts(snapshot,binding,lambda snap:forecast_result(snap,uuid4(),'ai',
        status='unavailable',error='MODEL_NOT_READY',explanation='QA04: explicit missing-model fixture'))
    assert algorithmic.status=='ok' and str(algorithmic.recommended_date)==case['expected_dates'][0]
    assert ai.status=='unavailable' and ai.recommended_date is None and ai.error_code=='MODEL_NOT_READY'
    assert decision.status=='fallback' and decision.selected_date==algorithmic.recommended_date
    assert algorithmic.result_id!=ai.result_id and algorithmic.run_id==ai.run_id==decision.run_id
    for field in ['snapshot_id','snapshot_sha256','binding_id','equipment_id','as_of','mandatory_due_date','data_origin']:
        assert getattr(algorithmic,field)==getattr(ai,field)
    assert decision.algorithmic_result_id==algorithmic.result_id and decision.ai_result_id==ai.result_id
    assert snapshot.model_dump_json()==before
    ForecastResult.model_validate_json(algorithmic.model_dump_json())
    ForecastResult.model_validate_json(ai.model_dump_json())
    OrchestrationDecision.model_validate_json(decision.model_dump_json())
