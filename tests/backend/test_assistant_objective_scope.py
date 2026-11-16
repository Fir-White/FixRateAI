"""An authorized successful source must still match the requested resource."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.assistant.objective_scope import objective_scope
from app.assistant.workflow import create_plan,record_result
from app.schemas.assistant import ToolSelection,GoalSpec
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed,join
from tests.backend.test_assistant import assistant_case,thread


ACTOR=str(uuid4());OTHER=str(uuid4());UNIT=str(uuid4())
SCOPE=dict(user_id=ACTOR,site_id='site',role='admin',conversation_id='chat')


def test_self_profile_cannot_certify_requested_employee_even_if_http_succeeded():
    goal=dict(selector=dict(user_id=OTHER))
    assert objective_scope(dict(scope=SCOPE),goal,'profile_read',{},dict(userId=ACTOR))=='requested_user_mismatch'
    assert objective_scope(dict(scope=SCOPE),goal,'staff_read',dict(path=dict(user_id=OTHER)),dict(user_id=OTHER)) is None


def test_model_guessed_actor_cannot_substitute_for_a_requested_crew_or_named_employee():
    goal=dict(id='g',outcome='staff_profile',selector=dict(user_id=ACTOR))
    value=dict(user_id=ACTOR,full_name='Test chief',email='chief@example.test')
    state=dict(scope=SCOPE,request='Show the Quartz crew and its members')
    assert objective_scope(state,goal,'staff_read',dict(path=dict(user_id=ACTOR)),value)=='requested_user_reference_unverified'
    state['request']='Show saved employee chief@example.test'
    assert objective_scope(state,goal,'staff_read',dict(path=dict(user_id=ACTOR)),value) is None


@pytest.mark.parametrize('field',['equipment_id','operation_id','task_id'])
def test_model_arguments_cannot_silently_replace_the_declared_target(field):
    tool={'equipment_id':'equipment_read','operation_id':'operation_read','task_id':'task_read'}[field]
    assert objective_scope(dict(scope=SCOPE),dict(selector={field:UNIT}),tool,dict(path={field:OTHER}),{})=='requested_resource_mismatch'


def test_history_of_arbitrary_first_equipment_does_not_prove_a_site_catalog_goal():
    proof=dict(tool='equipment_find',complete=True,retained=True,scope=SCOPE,
        arguments=dict(query={}),result=dict(items=[dict(equipment_id=UNIT,asset_code='PUMP-01')],total=1))
    state=dict(scope=SCOPE,request='List all saved maintenance operation codes and titles.',evidence=[proof])
    goal=dict(selector={},depends_on=[])
    args=dict(path=dict(equipment_id=UNIT),query=dict(starts_on='2026-01-01',ends_on='2026-12-31'))
    value=dict(equipment_id=UNIT,starts_on='2026-01-01',ends_on='2026-12-31')
    assert objective_scope(state,goal,'equipment_service_history',args,value)=='history_equipment_reference_unverified'
    state['request']='Check actual accepted history of PUMP-01 during2026.'
    assert objective_scope(state,goal,'equipment_service_history',args,value) is None
    state['request']='History of equipment '+UNIT
    assert objective_scope(state,goal,'equipment_service_history',args,value) is None


def test_the_calendar_period_cannot_be_replaced_by_a_different_valid_year():
    goal=dict(selector=dict(starts_on='2026-01-01',ends_on='2026-12-31'))
    args=dict(path=dict(equipment_id=UNIT),query=dict(starts_on='2027-01-01',ends_on='2027-12-31'))
    assert objective_scope(dict(scope=SCOPE),goal,'calendar_evidence',args,{})=='requested_period_mismatch'


def test_profile_selection_remaps_only_with_actual_staff_read_permission():
    tools={name:SimpleNamespace(mode='read') for name in ('profile_read','staff_read')}
    selection=ToolSelection(tools=[],goals=[GoalSpec(id='staff',title='Read selected employee '+OTHER,
        tool='profile_read',kind='read',selector=dict(user_id=ACTOR))])
    state=create_plan(selection,'Show employee '+OTHER,tools,SCOPE)
    goal=state['goals'][0]
    assert goal['tool']=='staff_read' and goal['outcome']=='staff_profile' and goal['selector']['user_id']==OTHER
    denied=create_plan(selection,'Show employee '+OTHER,{'profile_read':tools['profile_read']},SCOPE)
    assert denied['goals'][0]['status']=='blocked'


@pytest.mark.parametrize('selected',[ACTOR,OTHER])
def test_current_profile_contract_never_silently_becomes_another_staff_subject(selected):
    tools={name:SimpleNamespace(mode='read') for name in ('profile_read','staff_read')}
    selection=ToolSelection(tools=[],goals=[GoalSpec(id='self',title='Employee '+OTHER,
        outcome='current_profile',tool='profile_read',kind='read',selector=dict(user_id=selected))])
    state=create_plan(selection,'Show employee '+OTHER,tools,SCOPE)
    assert state['goals'][0]['status']=='blocked'
    assert state['goals'][0]['outcome']=='current_profile' and state['goals'][0]['tool']=='profile_read'


def test_a_capped_notification_array_does_not_claim_absence_of_older_messages():
    state=create_plan(ToolSelection(tools=[],goals=[GoalSpec(id='notice',title='All notifications',tool='notifications_list')]),
        'Show all notifications',{'notifications_list':SimpleNamespace(mode='read')},SCOPE)
    proof=record_result(state,state['goals'][0],'notifications_list',{},[dict(id=str(i)) for i in range(100)])
    assert not proof['complete'] and state['goals'][0]['status']=='partial'


def test_actual_http_employee_profile_never_substitutes_the_signed_in_account(assistant_case):
    from tests.backend.test_assistant_orchestrator import Planner,goal,send
    _,app,client,_,_=assistant_case
    identity,_=join(assistant_case)
    app.state.assistant_provider_factory=lambda:Planner([dict(goal('person','profile_read'),
        kind='read',selector=dict(user_id=str(identity)),title='Read employee '+str(identity))],[])
    try:
        view=send(client,thread(client),'Show the saved profile of employee '+str(identity))
        turn=view['turns'][-1]
        assert turn['status']=='completed' and turn['workflow']['outcome']=='completed'
        assert turn['workflow']['goals'][0]['tool']=='staff_read'
        assert 'Исполнитель' in turn['answer'] and 'Test chief' not in turn['answer']
        assert not view['actions']
    finally:del app.state.assistant_provider_factory


def test_actual_email_lookup_resolves_the_employee_instead_of_a_model_guessed_actor(assistant_case):
    from tests.backend.test_assistant_orchestrator import Planner,goal,send
    _,app,client,_,_=assistant_case
    identity,address=join(assistant_case)
    actor=client.get('/api/v1/maintenance/users/me').json()['userId']
    app.state.assistant_provider_factory=lambda:Planner([dict(goal('person',''),
        outcome='staff_profile',kind='unavailable',selector=dict(search=address,user_id=actor))],[])
    try:
        view=send(client,thread(client),'Show the saved employee with exact email '+address+'. Read only.')
        turn=view['turns'][-1];goal=turn['workflow']['goals'][0]
        assert turn['status']=='completed' and goal['status']=='completed'
        assert goal['tool']=='staff_read' and goal['selector']['user_id']==str(identity)
        assert address in turn['answer'] and 'Test chief' not in turn['answer'] and not view['actions']
    finally:del app.state.assistant_provider_factory


@pytest.mark.parametrize('complete,retained,foreign,ambiguous',[(False,True,False,False),(True,False,False,False),(True,True,True,False),(True,True,False,True)])
def test_incomplete_foreign_or_ambiguous_staff_resolution_cannot_certify_a_profile(complete,retained,foreign,ambiguous):
    email='worker@example.test';rows=[dict(user_id=OTHER,email=email)]
    if ambiguous:rows.append(dict(user_id=UNIT,email=email))
    state=dict(request='Show '+email,scope=SCOPE,evidence=[dict(goal_id='g',tool='staff_find',
        complete=complete,retained=retained,scope={} if foreign else SCOPE,
        arguments=dict(query=dict(q=email)),result=dict(items=rows,total=len(rows)))])
    goal=dict(id='g',selector=dict(search=email,user_id=OTHER),depends_on=[])
    assert objective_scope(state,goal,'staff_read',dict(path=dict(user_id=OTHER)),dict(user_id=OTHER))=='requested_staff_search_not_verified'


def test_actual_capability_repair_cannot_complete_components_from_another_read_source(assistant_case):
    from tests.backend.test_assistant_orchestrator import equipment,send
    _,app,client,_,ids=assistant_case
    unit=equipment(client,ids)
    selections=iter([
        dict(id='parts',title='Installed components',tool='',kind='unavailable',outcome='equipment_components',
            required_evidence='saved_data',selector=dict(equipment_id=unit['equipment_id'],starts_on='2026-01-01',ends_on='2026-12-31')),
        dict(id='easier',title='Accepted history',tool='equipment_service_history',kind='read',outcome='other',
            selector=dict(equipment_id=unit['equipment_id'],starts_on='2026-01-01',ends_on='2026-12-31')),
    ])
    class Repair:
        response_model='TEST-ONLY-scripted-capability-repair'
        def chat(self,messages,schema,tokens):
            assert schema.__name__=='ToolSelection','Canonical server adapter should execute without another model step'
            return schema.model_validate(dict(tools=[],goals=[next(selections)]))
    app.state.assistant_provider_factory=Repair
    try:
        view=send(client,thread(client),'Show installed components of equipment '+unit['equipment_id']+'. Read only.')
        turn=view['turns'][-1];goal=turn['workflow']['goals'][0]
        assert turn['status']=='completed' and goal['status']=='completed'
        assert goal['id']=='parts' and goal['outcome']=='equipment_components' and goal['tool']=='components_read'
        assert not view['actions']
        assert client.get('/api/v1/maintenance/equipment/'+unit['equipment_id']+'/components').json()==[]
    finally:del app.state.assistant_provider_factory
