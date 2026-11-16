"""Local native grammar: intent precedes tools; evidence cannot downgrade it.

Only scripted transport responses are used here. No model inference or tools
are executed, and public/scripted Pydantic compatibility stays independent.
"""
from copy import deepcopy
import json

import pytest

from app.schemas.assistant import GoalSpec,ToolSelection
from app.assistant.workflow import required_blocker
from ml_service.app.providers.ollama import (
    OllamaClient,OllamaConfig,OllamaFailure,agent_wire_schema,decode_agent_wire,
)

MODES={'equipment_find':'read','attachment_read':'read','calendar_evidence':'read',
       'profile_read':'read','equipment_edit':'write'}
OUTCOMES=['current_profile','staff_profile','staff_search','workforce','equipment_inventory','equipment_card',
          'equipment_search','equipment_components','maintenance_catalog','maintenance_definition',
          'reference_catalog','personal_notifications','protected_company_code','calendar_obligations',
          'accepted_history','task_card','task_analysis','file_analysis','norm_readiness','other']
GENERIC={'saved_data','calendar_calculation','manufacturer_document','optimizer_result','file_content','user_decision'}


def objective(outcome='equipment_card',evidence='saved_data',**extra):
    return GoalSpec(id='goal',title='TEST intended business result',outcome=outcome,
        tool='equipment_find',kind='read',required_evidence=evidence,**extra).model_dump(mode='json')


def decode(goal):
    return decode_agent_wire(ToolSelection,json.dumps(dict(tools=[],goals=[goal])),MODES)


def branches():return agent_wire_schema(ToolSelection,MODES)['$defs']['GoalSpec']['anyOf']


def accepts(branch,**values):
    for key,value in values.items():
        field=branch['properties'][key]
        if 'const' in field and field['const']!=value:return False
        if 'enum' in field and value not in field['enum']:return False
    return True


def test_actual_wire_requires_nonnull_outcome_before_tool_in_every_variant():
    offered=set()
    for branch in branches():
        fields=branch['properties'];outcome=fields['outcome']
        assert {'outcome','kind','selector','changes','required_evidence'}<=set(branch['required'])
        assert list(fields).index('outcome')<list(fields).index('tool')
        assert branch['required'].index('outcome')<branch['required'].index('tool')
        assert outcome['type']=='string' and None not in outcome['enum']
        assert 'default' not in outcome and 'anyOf' not in outcome
        offered.update(outcome['enum'])
    assert offered==set(OUTCOMES)


@pytest.mark.parametrize('outcome',OUTCOMES[:-1])
def test_concrete_read_outcome_fixes_evidence_without_restricting_correctable_read_tool(outcome):
    required='calendar_calculation' if outcome=='calendar_obligations' else 'file_content' if outcome=='file_analysis' else 'saved_data'
    eligible=[branch for branch in branches() if accepts(branch,kind='read',outcome=outcome)]
    assert len(eligible)==1
    assert eligible[0]['properties']['required_evidence']['enum']==[required]
    assert set(eligible[0]['properties']['tool']['enum'])=={name for name,mode in MODES.items() if mode=='read'}
    goal=objective(outcome,required)
    assert decode(goal).goals[0].outcome==outcome
    for wrong in GENERIC-{required}:
        with pytest.raises(ValueError):decode({**goal,'required_evidence':wrong})


@pytest.mark.parametrize('evidence',sorted(GENERIC))
def test_other_retains_generic_compatibility_without_certifying_protected_sources(evidence):
    goal=objective('other',evidence)
    assert decode(goal).goals[0].required_evidence==evidence
    if evidence in ('manufacturer_document','user_decision'):
        assert required_blocker(goal) in ('manufacturer_document_not_verified','user_decision_required')


@pytest.mark.parametrize('evidence',['manufacturer_document','user_decision'])
def test_unavailable_primary_source_goals_remain_representable_and_server_blocked(evidence):
    goal=objective('maintenance_definition',evidence)
    goal.update(kind='unavailable',tool='')
    assert decode(goal).goals[0].tool=='' and required_blocker(goal)


@pytest.mark.parametrize('kind,evidence,tool',[
    ('change','saved_data','equipment_edit'),
    ('change','optimizer_result','equipment_edit'),
    ('conversation','conversation',''),
])
def test_write_and_conversation_use_other_and_never_claim_a_read_contract(kind,evidence,tool):
    goal=objective();goal.update(kind=kind,required_evidence=evidence,tool=tool,outcome='other')
    assert decode(goal).goals[0].outcome=='other'
    with pytest.raises(ValueError):decode({**goal,'outcome':'equipment_card'})


@pytest.mark.parametrize('change',[
    dict(outcome=None),dict(outcome='invented_contract'),dict(required_evidence=None),
    dict(required_evidence='conversation'),dict(tool='equipment_edit'),
])
def test_actual_wire_decoder_rejects_null_unknown_or_inconsistent_goal_contract(change):
    with pytest.raises(ValueError):decode({**objective(),**change})


def test_missing_outcome_is_rejected_only_at_actual_local_wire_boundary():
    goal=objective();goal.pop('outcome')
    assert ToolSelection.model_validate(dict(tools=[],goals=[goal])).goals[0].outcome is None
    assert decode_agent_wire(ToolSelection,json.dumps(dict(tools=[],goals=[goal]))).goals[0].outcome is None
    with pytest.raises(ValueError):decode(goal)
    assert agent_wire_schema(ToolSelection)==ToolSelection.model_json_schema()


def test_new_selector_fields_remain_required_in_local_wire_and_nullable_in_scripted_schema():
    wire=agent_wire_schema(ToolSelection,MODES)
    selector=wire['$defs']['GoalSelector']
    assert {'operation_id','task_id','search'}<=set(selector['required'])
    assert set(selector['required'])==set(selector['properties'])
    assert objective()['selector']['operation_id'] is None


def test_wire_extracts_referenced_pydantic_enum_instead_of_duplicating_an_outcome_list():
    native=ToolSelection.model_json_schema()
    native['$defs']['GoalSpec']['properties']['outcome']={
        'anyOf':[{'$ref':'#/$defs/ReadOutcome'},{'type':'null'}],'default':None}
    native['$defs']['ReadOutcome']={'type':'string','enum':[*OUTCOMES,'future_database_read']}
    class Schema:
        @classmethod
        def model_json_schema(cls):return deepcopy(native)
    Schema.__name__='ToolSelection'
    wire=agent_wire_schema(Schema,MODES)
    offered={item for branch in wire['$defs']['GoalSpec']['anyOf'] for item in branch['properties']['outcome']['enum']}
    assert offered==set(OUTCOMES)|{'future_database_read'}


def scripted_client(monkeypatch,values):
    client=OllamaClient(OllamaConfig('http://127.0.0.1:11434','qwen3.5:4b-q4_K_M','sha256:'+'a'*64))
    client.set_tool_modes(MODES);requests=[];values=iter(values)
    def request(path,payload=None):
        requests.append((path,deepcopy(payload)))
        if path=='/api/tags':return dict(models=[dict(name=client.config.model,digest=client.config.digest)])
        return dict(model=client.config.model,done=True,done_reason='stop',message=dict(content=json.dumps(next(values))))
    monkeypatch.setattr(client,'request',request)
    return client,requests


def test_actual_client_retries_missing_outcome_without_leaking_invalid_output(monkeypatch,caplog):
    bad=objective();bad.pop('outcome');bad['title']='SYNTHETIC-PRIVATE-INVALID-OUTPUT'
    client,requests=scripted_client(monkeypatch,[dict(tools=[],goals=[bad])]*2)
    with pytest.raises(OllamaFailure) as error:client.chat([],ToolSelection,2000)
    assert error.value.diagnostic['attempt']==2
    assert [path for path,_ in requests]==['/api/tags','/api/chat','/api/chat']
    assert 'SYNTHETIC-PRIVATE' not in caplog.text
    assert 'SYNTHETIC-PRIVATE' not in json.dumps(requests[-1][1])


def test_actual_client_can_return_wrong_read_tool_for_server_rectification_but_correct_evidence(monkeypatch):
    goal=objective('protected_company_code');goal['tool']='attachment_read'
    client,requests=scripted_client(monkeypatch,[dict(tools=[],goals=[goal])])
    result=client.chat([],ToolSelection,2000)
    assert result.goals[0].outcome=='protected_company_code' and result.goals[0].tool=='attachment_read'
    assert requests[-1][1]['format']['$defs']['GoalSpec']['anyOf']
