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
