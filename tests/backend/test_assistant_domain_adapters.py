"""Server preparation must follow typed business outcomes, not wording routes."""
from app.assistant.domain_adapters import next_step
from app.assistant.workflow import create_plan
from app.schemas.assistant import ToolSelection,GoalSpec
from ml_service.app.providers.ollama import agent_wire_schema
from types import SimpleNamespace
from uuid import uuid4
import pytest


def objective(tool,**values):
    return {**dict(id='g',title='Requested outcome',tool=tool,depends_on=[],selector={},changes={}),**values}


def test_exact_code_is_resolved_before_preparing_requested_change():
    goal=objective('equipment_edit',selector=dict(equipment_code='P-01'),changes=dict(name='Exact name'))
    state=dict(evidence=[])
    first=next_step(goal,state).calls[0]
    assert first.tool=='equipment_find' and first.arguments==dict(query=dict(asset_code='P-01'))
    identity=str(uuid4())
    state['evidence']=[dict(goal_id='g',tool='equipment_find',arguments=first.arguments,
                           result=dict(items=[dict(equipment_id=identity,asset_code='P-01')],total=1))]
    second=next_step(goal,state).calls[0]
    assert second.tool=='equipment_edit'
    assert second.arguments==dict(path=dict(equipment_id=identity),body=dict(name='Exact name'))
    assert 'expected_revision' not in second.arguments['body']  # execution obtains it fresh


@pytest.mark.parametrize('target',['calendar_evidence','equipment_service_history'])
def test_history_and_calendar_keep_their_own_explicit_period(target):
    identity=str(uuid4())
    goal=objective(target,selector=dict(equipment_id=identity,starts_on='2026-01-01',ends_on='2026-12-31'))
    call=next_step(goal,dict(evidence=[])).calls[0]
    assert call.tool==target and call.arguments['query']==dict(starts_on='2026-01-01',ends_on='2026-12-31')
    goal['selector'].pop('ends_on')
    assert next_step(goal,dict(evidence=[])) is None


def test_missing_resource_and_change_values_are_never_invented():
    assert next_step(objective('equipment_edit'),dict(evidence=[])) is None
    assert next_step(objective('equipment_edit',selector=dict(equipment_id=str(uuid4()))),dict(evidence=[])) is None


def test_equipment_identity_cannot_cross_undeclared_dependencies():
    identity=str(uuid4())
    proof=dict(goal_id='other',tool='equipment_read',arguments=dict(path=dict(equipment_id=identity)),result={})
    goal=objective('regulations_read')
    assert next_step(goal,dict(evidence=[proof])) is None
    goal['depends_on']=['other']
    assert next_step(goal,dict(evidence=[proof])).calls[0].arguments['path']['equipment_id']==identity


def test_named_equipment_context_reuses_identity_but_still_reads_fresh_business_data():
    identity=str(uuid4());scope=dict(user_id='actor',site_id='site',role='engineer',conversation_id='chat')
    proof=dict(goal_id='first',tool='equipment_find',complete=True,retained=True,scope=scope,
               result=dict(items=[dict(equipment_id=identity,asset_code='НС-01')]))
    state=dict(request='Проверь календарь и историю НС-01.',scope=scope,evidence=[proof])
    goal=objective('equipment_service_history',title='История НС-01 за 2026 год',
                   selector=dict(starts_on='2026-01-01',ends_on='2026-12-31'))
    call=next_step(goal,state).calls[0]
    assert call.tool=='equipment_service_history'
    assert call.arguments==dict(path=dict(equipment_id=identity),query=dict(starts_on='2026-01-01',ends_on='2026-12-31'))


@pytest.mark.parametrize('fault',['scope','incomplete','discarded','ambiguous','title','request','substring','nested','wrong_tool'])
def test_equipment_context_never_guesses_or_crosses_scope(fault):
    from copy import deepcopy
    scope=dict(user_id='actor',site_id='site',role='engineer',conversation_id='chat')
    row=dict(equipment_id=str(uuid4()),asset_code='P-01')
    proof=dict(goal_id='first',tool='equipment_find',complete=True,retained=True,scope=deepcopy(scope),result=dict(items=[row]))
    state=dict(request='Read P-01.',scope=scope,evidence=[proof])
    goal=objective('regulations_read',title='Regulations P-01')
    if fault=='scope':proof['scope']['role']='other'
    elif fault=='incomplete':proof['complete']=False
    elif fault=='discarded':proof['retained']=False
    elif fault=='ambiguous':proof['result']['items'].append(dict(equipment_id=str(uuid4()),asset_code='P-01'))
    elif fault=='title':goal['title']='Other equipment'
    elif fault=='request':state['request']='Read something else'
    elif fault=='substring':row['asset_code']='P-0'
    elif fault=='nested':proof['result']=dict(properties=dict(items=[row]))
    elif fault=='wrong_tool':proof['tool']='attachment_read'
    assert next_step(goal,state) is None


def test_inventory_is_server_prepared_and_preserves_requested_scope():
    call=next_step(objective('inventory_read',selector=dict(current_only=True)),dict(evidence=[])).calls[0]
    assert call.arguments==dict(query=dict(current_only=True))


def test_a_search_cannot_certify_a_requested_change():
    tools=dict(equipment_find=SimpleNamespace(mode='read'))
    plan=create_plan(ToolSelection(tools=[],goals=[GoalSpec(id='rename',title='Rename requested equipment',tool='equipment_find')]),'Rename',tools,{})
    assert plan['goals'][0]['status']=='blocked'
    assert plan['goals'][0]['reason']=='plan_outcome_tool_mismatch'


def test_local_planner_grammar_requires_outcomes_and_separates_read_and_change():
    schema=agent_wire_schema(ToolSelection,dict(equipment_find='read',equipment_edit='write'))
    variants=schema['$defs']['GoalSpec']['anyOf']
    write=next(v for v in variants if v['properties']['kind']['const']=='change')
    assert write['properties']['tool']['enum']==['equipment_edit']
    assert {'kind','selector','changes','tool'}<=set(write['required'])
    assert 'goals' in schema['required']
    assert set(schema['$defs']['GoalSelector']['required'])==set(schema['$defs']['GoalSelector']['properties'])


def test_valid_nested_status_properties_do_not_crash_evidence_memory():
    from app.assistant.evidence_cache import _complete
    assert _complete(dict(properties=dict(status=dict(inspection='current'))))


def test_requested_patch_is_compiled_from_changes_despite_read_annotation():
    read=SimpleNamespace(mode='read',method='GET',before=None)
    write=SimpleNamespace(mode='write',method='PATCH',before='equipment_read')
    tools=dict(equipment_read=read,equipment_edit=write)
    selection=ToolSelection(tools=[],goals=[GoalSpec(id='rename',title='Prepare requested rename',kind='read',tool='equipment_read',changes=dict(name='Exact'))])
    state=create_plan(selection,'Rename the selected equipment to Exact',tools,{})
    assert state['goals'][0]['tool']=='equipment_edit' and state['goals'][0]['kind']=='change'
    assert state['goals'][0]['status']=='planned' and state['goals'][0]['changes']==dict(name='Exact')
    denied=create_plan(selection,'Read the equipment card; do not rename anything',tools,{})
    assert denied['goals'][0]['status']=='blocked'


def test_secondary_workflow_annotation_cannot_override_registered_operation():
    tools=dict(calendar_evidence=SimpleNamespace(mode='read'))
    selection=ToolSelection(tools=[],goals=[GoalSpec(id='calendar',title='Explain recurrence',tool='calendar_evidence',workflow_kind='calendar')])
    state=create_plan(selection,'Explain recurrence',tools,{})
    assert state['goals'][0]['tool']=='calendar_evidence'
    assert state['goals'][0]['workflow_kind'] is None


def test_refusal_prose_cannot_complete_a_misclassified_mutation_as_conversation():
    state=create_plan(ToolSelection(tools=[],goals=[GoalSpec(id='rename',title='Discuss the request',tool='',kind='conversation')]),
                      'Rename equipment after my separate confirmation',{}, {})
    assert state['goals'][0]['status']=='blocked'
    assert state['goals'][0]['reason']=='plan_outcome_tool_mismatch'


@pytest.mark.parametrize('required',['manufacturer_document','user_decision','optimizer_result','calendar_calculation','file_content'])
def test_plan_repair_preserves_each_named_objective_and_its_evidence_requirement(required):
    from app.assistant.workflow import preserve_constraints
    from copy import deepcopy
    prior=dict(goals=[dict(id='g',title='Original equipment P-01',depends_on=[],selector=dict(equipment_code='P-01'),required_evidence=required,requires_full_list=True,response_style='analysis')])
    replacement=dict(goals=[dict(id='g',title='Easier different goal',depends_on=[],selector=dict(equipment_code='P-02'),required_evidence='saved_data',requires_full_list=False,response_style='facts')])
    assert preserve_constraints(prior,replacement)
    goal=replacement['goals'][0]
    assert goal['required_evidence']==required and goal['title']==prior['goals'][0]['title']
    assert goal['selector']['equipment_code']=='P-01' and goal['requires_full_list'] and goal['response_style']=='analysis'
    removed=deepcopy(replacement);removed['goals'][0]['id']='replacement-id'
    assert not preserve_constraints(prior,removed)


@pytest.mark.parametrize('full,book_complete',[(False,True),(True,False),(False,False)])
def test_one_sheet_or_partial_book_cannot_complete_whole_workbook_analysis(full,book_complete):
    from app.assistant.workflow import record_result
    state=create_plan(ToolSelection(tools=[],goals=[GoalSpec(id='file',title='Analyze all sheets',tool='attachment_read',response_style='analysis')]),
                      'Analyze the whole file',dict(attachment_read=SimpleNamespace(mode='read',method='GET',before=None)),{})
    goal=state['goals'][0]
    proof=record_result(state,goal,'attachment_read',dict(query=dict(full_book=full)),dict(items=[],total=0,workbook=dict(status='read',complete=book_complete)))
    assert not proof['complete'] and goal['status']!='completed'
    assert 'full_workbook_not_verified' in proof['limitations']


def test_read_capability_repair_retains_component_outcome_and_canonical_source():
    from app.assistant.workflow import preserve_constraints
    tools={name:SimpleNamespace(mode='read') for name in ('equipment_service_history','components_read')}
    prior=dict(goals=[objective('',kind='unavailable',outcome='equipment_components',required_evidence='saved_data',selector=dict(equipment_id=str(uuid4())))])
    revised=create_plan(ToolSelection(tools=[],goals=[GoalSpec(id='g',title='History',tool='equipment_service_history',outcome='other',kind='read')]),'Read components',tools,{})
    assert preserve_constraints(prior,revised,tools)
    goal=revised['goals'][0]
    assert goal['outcome']=='equipment_components' and goal['tool']=='components_read'
    assert goal['selector']['equipment_id']==prior['goals'][0]['selector']['equipment_id'] and goal['mode']=='read'


@pytest.mark.parametrize('replacement_tool',['equipment_read','equipment_edit'])
def test_plan_repair_cannot_replace_original_patch_values_or_turn_change_into_read(replacement_tool):
    from app.assistant.workflow import preserve_constraints
    tools=dict(equipment_read=SimpleNamespace(mode='read'),equipment_edit=SimpleNamespace(mode='write'))
    prior=dict(goals=[objective('equipment_edit',kind='change',changes=dict(name='Original exact value'),required_evidence='saved_data')])
    revised=dict(goals=[objective(replacement_tool,kind='read',changes=dict(name='Different',description='Unrequested'),status='planned')])
    assert preserve_constraints(prior,revised,tools)
    goal=revised['goals'][0]
    assert goal['kind']=='change' and goal['changes']==dict(name='Original exact value')
    if replacement_tool=='equipment_read':assert goal['status']=='blocked' and goal['reason']=='plan_outcome_tool_mismatch'


def test_plan_repair_cannot_replace_a_declared_business_workflow():
    from app.assistant.workflow import preserve_constraints
    prior=dict(goals=[objective('publication_prepare',workflow_kind='prepare_approval')])
    revised=dict(goals=[objective('draft_read',workflow_kind=None)])
    assert not preserve_constraints(prior,revised,{})


def test_schema_validation_error_hands_control_to_the_scoped_model_instead_of_repeating_invalid_adapter():
    goal=objective('staff_edit',changes=dict(employment_end_date='2028-04-05'),selector=dict(user_id=str(uuid4())),reason='tool_error_422')
    assert next_step(goal,dict(evidence=[])) is None


def test_read_only_plan_cannot_complete_an_explicit_start_request():
    tools=dict(task_read=SimpleNamespace(mode='read'))
    state=create_plan(ToolSelection(tools=[],goals=[GoalSpec(id='g',title='Read assigned task',tool='task_read',outcome='task_card',kind='read')]),
        'Start only my assigned task. Do not submit or accept a report.',tools,{})
    assert state['goals'][0]['status']=='blocked' and state['goals'][0]['reason']=='plan_outcome_tool_mismatch'


def test_explicit_primary_document_verification_is_not_lost_when_planner_omits_it():
    tools=dict(equipment_read=SimpleNamespace(mode='read'))
    selection=ToolSelection(tools=[],goals=[GoalSpec(id='g',title='Read saved equipment',tool='equipment_read')])
    state=create_plan(selection,'Read equipment and verify the manufacturer recommendation against its manual.',tools,{})
    assert len(state['goals'])==2 and state['goals'][0]['id']=='g'
    assert state['goals'][1]['required_evidence']=='manufacturer_document' and state['goals'][1]['status']=='blocked'


@pytest.mark.parametrize('question',[
    'Show the saved manufacturer field.',
    'Do not verify the manufacturer manual. Show saved data only.',
    'Не проверяй паспорт производителя. Покажи карточку.',
])
def test_primary_document_safeguard_does_not_invent_a_read_or_negated_document_request(question):
    from app.assistant.intents import primary_document_requested
    assert not primary_document_requested(question)


@pytest.mark.parametrize('revision',[None,3])
def test_typed_task_start_prepares_the_existing_confirmation_transport_without_model_repetition(revision):
    identity=str(uuid4());goal=objective('task_start',outcome='other',selector=dict(task_id=identity),changes=dict(expected_revision=revision))
    step=next_step(goal,dict(request='Start task '+identity,evidence=[]))
    assert step.calls[0].tool=='task_start' and step.calls[0].arguments==dict(path=dict(task_id=identity),body={} if revision is None else dict(expected_revision=3))


@pytest.mark.parametrize('required',['conversation','manufacturer_document','user_decision'])
def test_literal_typed_staff_patch_is_bound_without_weakening_real_source_requirements(required):
    identity=str(uuid4());tools=dict(staff_edit=SimpleNamespace(mode='write'))
    selection=ToolSelection(tools=[],goals=[GoalSpec(id='g',title='Selected staff change',tool='',kind='conversation',outcome='other',
        selector=dict(user_id=identity),changes=dict(employed_until='2028-04-05'),required_evidence=required)])
    state=create_plan(selection,'Change only employment end date for user_id='+identity,tools,{})
    goal=state['goals'][0]
    assert goal['tool']=='staff_edit' and goal['kind']=='change' and goal['changes']==dict(employed_until='2028-04-05')
    if required=='conversation':assert goal['required_evidence']=='saved_data' and goal['status']=='planned'
    else:assert goal['required_evidence']==required and goal['status']=='blocked'


def test_task_assign_adapter_resolves_nearest_task_and_prepares_assignment():
    goal=objective('task_assign',title='Назначить самого малозагруженного работника на ближайшее ТО',outcome='other')
    state=dict(request='привет, назначь самого малозагруженного работника на ближайшее ТО',evidence=[])
    step1=next_step(goal,state).calls[0]
    assert step1.tool=='tasks_find' and step1.arguments==dict(query=dict(period='upcoming'))
    state['evidence'].append(dict(goal_id='g',tool='tasks_find',arguments=step1.arguments,result=dict(items=[],total=0)))
    step2=next_step(goal,state).calls[0]
    assert step2.tool=='tasks_find' and step2.arguments==dict(query=dict(period='all'))
    task_id=str(uuid4());worker_id=str(uuid4())
    state['evidence'].append(dict(goal_id='g',tool='tasks_find',arguments=step2.arguments,result=dict(items=[dict(id=task_id,state='draft')],total=1)))
    step3=next_step(goal,state).calls[0]
    assert step3.tool=='assignment_prepare' and step3.arguments==dict(path=dict(task_id=task_id),body=dict(one_person_only=True))
    command=dict(expected_revision=1,executor_ids=[worker_id],start_at='2026-11-18T09:00:00+05:00',end_at='2026-11-18T10:00:00+05:00')
    state['evidence'].append(dict(goal_id='g',tool='assignment_prepare',arguments=step3.arguments,result=dict(status='ok',command=command)))
    step4=next_step(goal,state).calls[0]
    assert step4.tool=='task_assign'
    assert step4.arguments['path']==dict(task_id=task_id)
    assert step4.arguments['body']['executor_ids']==[worker_id]
    assert step4.arguments['body']['expected_revision']==1


def test_task_assign_adapter_stops_when_prepare_needs_input():
    goal=objective('task_assign',title='Назначить одного работника',outcome='other')
    task_id=str(uuid4())
    state=dict(request='назначь одного работника на ближайшее ТО',evidence=[
        dict(goal_id='g',tool='tasks_find',arguments=dict(query=dict(period='upcoming')),result=dict(items=[dict(id=task_id,state='draft')],total=1)),
        dict(goal_id='g',tool='assignment_prepare',arguments=dict(path=dict(task_id=task_id),body=dict(one_person_only=True)),result=dict(status='needs_input',explanation='Нужно 2 исполнителей')),
    ])
    assert next_step(goal,state) is None


def test_tasks_find_adapter_uses_upcoming_or_all_period():
    goal=objective('tasks_find',title='Ближайшие ТО',outcome='other',selector=dict(search='ближайшие'))
    step1=next_step(goal,dict(request='какие ТО будут в ближайшее время?',evidence=[])).calls[0]
    assert step1.tool=='tasks_find' and step1.arguments==dict(query=dict(period='upcoming'))
    step2=next_step(goal,dict(request='покажи все просроченные ТО',evidence=[])).calls[0]
    assert step2.tool=='tasks_find' and step2.arguments==dict(query=dict(period='all'))
