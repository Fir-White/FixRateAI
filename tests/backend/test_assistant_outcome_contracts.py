"""A successful wrong source never settles a typed business read objective."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.assistant.domain_adapters import next_step
from app.assistant.outcome_contracts import READ_EVIDENCE, READ_TARGETS, normalize_goal, resolve_read_contract, validate_result
from app.schemas.assistant import GoalSpec, GoalSelector, ReadOutcome
from typing import get_args


USER, EQUIPMENT, OPERATION, TASK = (str(uuid4()) for _ in range(4))
TOOLS={name:SimpleNamespace(mode='read') for name in READ_TARGETS.values()}
TOOLS['staff_edit']=SimpleNamespace(mode='write')


def goal(outcome, tool, **changes):
    return {**dict(id='requested', title='Requested user result', outcome=outcome, tool=tool,
                  kind='read', selector={}, changes={}, depends_on=[]), **changes}


def staff():
    return dict(user_id=USER, full_name='Selected employee', email='employee@example.test',
                role='executor', revision=2, membership_is_active=True, account_is_active=False,
                is_active=False, employed_from='2025-01-02', employed_until=None)


def component():
    return dict(component_id=str(uuid4()), equipment_id=EQUIPMENT, position_code='bearing-1', name='Bearing',
                installed_on='2025-01-01', usage_unit='cycle', initial_usage='100.000', current_usage='125.000',
                resource_limit='800.000', resource_basis='Saved confirmed source', remaining_usage='675.000',
                resource_state='available', revision=2, readings=[])


def operation():
    return dict(operation_id=OPERATION, code='OP-1', title='Saved inspection', instructions='Inspect actual bearings',
                crew_size=2, raw_norm_value='2.000', norm_unit='person_hour', planning_duration_minutes=60,
                checklist=[dict(text='Inspect')], status='approved')


def test_enum_ordered_before_tool_and_legacy_none_is_compatible():
    fields=list(GoalSpec.model_fields)
    assert fields.index('outcome') < fields.index('tool')
    assert set(get_args(ReadOutcome)) == set(READ_TARGETS) | {'other'}
    old=GoalSpec(id='old', title='Old scripted objective', tool='equipment_read')
    assert old.outcome is None
    selector=GoalSelector(operation_id=OPERATION, task_id=TASK, search='literal@example.test')
    assert selector.model_dump(mode='json')['operation_id'] == OPERATION


@pytest.mark.parametrize('outcome,wrong', [
    ('staff_profile','profile_read'), ('equipment_components','equipment_read'),
    ('maintenance_catalog','equipment_service_history'), ('maintenance_definition','task_read'),
    ('protected_company_code','attachment_read'),
])
def test_typed_read_result_rectifies_wrong_tool_without_title_keywords(outcome, wrong):
    original=goal(outcome,wrong,title='No domain words whatsoever', required_evidence=None)
    copied=deepcopy(original)
    fixed=normalize_goal(original,TOOLS)
    assert fixed['tool']==READ_TARGETS[outcome]
    assert fixed['required_evidence']==READ_EVIDENCE[outcome]
    assert original==copied
    assert fixed['outcome_contract']['status']=='applied'


@pytest.mark.parametrize('required',['file_content','optimizer_result','calendar_calculation'])
def test_read_contract_cannot_erase_a_stronger_declared_evidence_requirement(required):
    original=goal('staff_profile','profile_read',required_evidence=required)
    fixed=normalize_goal(original,TOOLS)
    assert fixed['status']=='blocked' and fixed['reason']=='read_outcome_evidence_mismatch'
    assert fixed['required_evidence']==required


def test_typed_file_analysis_always_requires_the_complete_workbook():
    fixed=normalize_goal(goal('file_analysis','attachment_read'),{'attachment_read':SimpleNamespace(mode='read')})
    assert fixed['response_style']=='analysis' and fixed['requires_full_list'] is True
    assert validate_result(fixed,'attachment_read',dict(attachment=dict(attachment_id=USER),items=[]))==(False,'read_outcome_result_shape_mismatch')
    assert validate_result(fixed,'attachment_read',dict(workbook=dict(status='read',complete=True)))==(True,None)


@pytest.mark.parametrize('changes', [dict(kind='change'),dict(kind='conversation'),dict(kind='unavailable'),
    dict(mode='write'),dict(changes=dict(role='engineer')),dict(workflow_kind='approve'),
    dict(required_evidence='manufacturer_document'),dict(required_evidence='user_decision'),dict(tool='staff_edit')])
def test_read_contract_never_downgrades_a_mutation_or_real_blocker(changes):
    original=goal('staff_profile','profile_read',**{key:value for key,value in changes.items() if key!='tool'})
    if 'tool' in changes:original['tool']=changes['tool']
    result=normalize_goal(original,TOOLS)
    assert result['tool']==original['tool'] and result['kind']==original['kind']
    assert result['outcome_contract']['status']=='preserved'


def test_missing_authorized_canonical_source_never_falls_back_to_wrong_profile():
    result=normalize_goal(goal('staff_profile','profile_read'),{'profile_read':TOOLS['profile_read']})
    assert result['status']=='blocked' and result['reason']=='read_outcome_source_not_authorized'


def test_known_forbidden_write_is_not_downgraded_to_a_read_by_filtered_catalog():
    original=goal('staff_profile','staff_edit')
    result=normalize_goal(original,{'staff_read':TOOLS['staff_read']})
    assert result['tool']=='staff_edit' and result['outcome_contract']['status']=='preserved'


def test_backward_none_and_other_do_not_change_scripted_routing():
    for outcome in (None,'other'):
        original=goal(outcome,'equipment_read')
        assert normalize_goal(original,TOOLS)==original
    assert next_step(goal(None,'staff_read',selector=dict(user_id=USER)),dict(evidence=[])) is None


@pytest.mark.parametrize('outcome,tool,value', [
    ('staff_profile','profile_read',dict(userId=USER,name='Actor',role='admin')),
    ('equipment_components','equipment_read',dict(equipment_id=EQUIPMENT,name='Pump')),
    ('maintenance_catalog','equipment_service_history',dict(items=[],total=0,complete=True)),
    ('maintenance_definition','task_read',dict(task=dict(id=TASK,summary='Work',state='draft',revision=1))),
])
def test_wrong_source_shapes_cannot_claim_typed_goal_completion(outcome,tool,value):
    assert validate_result(goal(outcome,READ_TARGETS[outcome]),tool,value)==(False,'read_outcome_source_mismatch')


@pytest.mark.parametrize('outcome,value', [
    ('staff_profile',staff()), ('equipment_components',[component()]),
    ('maintenance_definition',operation()), ('maintenance_catalog',[operation()]),
])
def test_real_authoritative_shapes_are_accepted(outcome,value):
    assert validate_result(goal(outcome,READ_TARGETS[outcome]),READ_TARGETS[outcome],value)==(True,None)


@pytest.mark.parametrize('field', ['user_id','full_name','role','membership_is_active','account_is_active',
                                   'is_active','employed_from','employed_until'])
def test_staff_profile_requires_complete_membership_and_account_facts(field):
    value=staff();value.pop(field)
    assert not validate_result(goal('staff_profile','staff_read'),'staff_read',value)[0]


@pytest.mark.parametrize('field', ['component_id','equipment_id','usage_unit','initial_usage','current_usage',
                                   'resource_limit','remaining_usage','resource_basis','readings'])
def test_component_resource_fields_are_not_replaceable_by_equipment_metadata(field):
    value=component();value.pop(field)
    assert not validate_result(goal('equipment_components','components_read'),'components_read',[value])[0]


@pytest.mark.parametrize('field', ['operation_id','instructions','crew_size','raw_norm_value','norm_unit','planning_duration_minutes'])
def test_operation_definition_requires_actual_saved_norm_and_instruction_fields(field):
    value=operation();value.pop(field)
    assert not validate_result(goal('maintenance_definition','operation_read'),'operation_read',value)[0]


def test_explicit_unknown_resource_and_norm_are_valid_facts_not_invented_values():
    part=component();part.update(resource_limit=None,resource_basis=None,remaining_usage=None,resource_state='unknown')
    assert validate_result(goal('equipment_components','components_read'),'components_read',[part])[0]
    definition=operation();definition.update(crew_size=None,raw_norm_value=None,norm_unit='unconfirmed',planning_duration_minutes=None)
    assert validate_result(goal('maintenance_definition','operation_read'),'operation_read',definition)[0]


@pytest.mark.parametrize('outcome',['staff_search','equipment_search','equipment_components','maintenance_catalog','personal_notifications'])
def test_authoritative_empty_complete_lists_are_legitimate(outcome):
    assert validate_result(goal(outcome,READ_TARGETS[outcome]),READ_TARGETS[outcome],[])[0]
    assert validate_result(goal(outcome,READ_TARGETS[outcome]),READ_TARGETS[outcome],dict(items=[],total=0,complete=True))[0]
    assert not validate_result(goal(outcome,READ_TARGETS[outcome]),READ_TARGETS[outcome],dict(items=[],total=1,complete=False))[0]


def test_enrollment_contract_accepts_only_the_protected_same_origin_handoff():
    value=dict(code_present=True,protected_output=True,resource=dict(protected=True,url='/api/v1/maintenance/management/enrollment'))
    subject=goal('protected_company_code','enrollment_read')
    assert validate_result(subject,'enrollment_read',value)[0]
    for bad in (dict(code='PRIVATE'),{**value,'code':'PRIVATE'},
                {**value,'code_sha256':'a'*64},{**value,'resource':dict(protected=True,url='https://external.test/code')}):
        assert not validate_result(subject,'enrollment_read',bad)[0]


@pytest.mark.parametrize('outcome,selector,wanted', [
    ('staff_profile',dict(user_id=USER),dict(path=dict(user_id=USER))),
    ('staff_search',dict(search='exact@example.test'),dict(query=dict(q='exact@example.test'))),
    ('maintenance_catalog',{},{}),
    ('maintenance_definition',dict(operation_id=OPERATION),dict(path=dict(operation_id=OPERATION))),
    ('equipment_components',dict(equipment_id=EQUIPMENT),dict(path=dict(equipment_id=EQUIPMENT))),
    ('task_card',dict(task_id=TASK),dict(path=dict(task_id=TASK))),
])
def test_typed_selectors_prepare_correct_server_calls_without_an_extra_model(outcome,selector,wanted):
    subject=goal(outcome,READ_TARGETS[outcome],selector=selector)
    call=next_step(subject,dict(evidence=[])).calls[0]
    assert call.tool==READ_TARGETS[outcome] and call.arguments==wanted


def test_component_exact_code_resolution_never_selects_first_or_conflicting_unit():
    subject=goal('equipment_components','components_read',selector=dict(equipment_code='P-01'))
    state=dict(evidence=[])
    first=next_step(subject,state).calls[0]
    assert first.tool=='equipment_find' and first.arguments==dict(query=dict(asset_code='P-01'))
    state['evidence']=[dict(goal_id='requested',tool='equipment_find',arguments=first.arguments,
        result=dict(items=[dict(equipment_id=EQUIPMENT,asset_code='P-01')],total=1))]
    assert next_step(subject,state).calls[0].arguments==dict(path=dict(equipment_id=EQUIPMENT))
    subject['selector']['equipment_id']=str(uuid4())
    assert next_step(subject,state) is None
