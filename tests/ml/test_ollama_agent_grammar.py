"""Independent set/const envelope oracle, not a general JSON Schema validator or inference."""
import json
import pytest
from app.schemas.assistant import AgentStep
from ml_service.app.providers.ollama import agent_wire_schema,decode_agent_wire


def permits_envelope(wire,tool,arguments):
    call=wire['$defs']['AgentCall']
    for branch in call.get('anyOf',[call]):
        props=branch['properties']
        if props['tool'].get('const',tool)!=tool:continue
        envelope=props['arguments_json']
        if envelope['type']=='object' and set(arguments)<=set(envelope['properties']) and set(envelope.get('required',()))<=set(arguments):return True
    return False


@pytest.mark.parametrize('arguments',[
    {'name':''},
    {'name':'equipment_find'},
    {'path':{},'name':''},
    {'query':{},'name':'x'},
    {'body':{},'name':''},
])
def test_helper_name_cannot_enter_an_ordinary_tool_envelope(arguments):
    value=dict(answer='',calls=[dict(tool='equipment_find',explanation='TEST ONLY schema boundary',arguments_json=arguments)])
    assert not permits_envelope(agent_wire_schema(AgentStep),'equipment_find',arguments),'Helper metadata must be excluded by grammar, not dropped from a real query'


@pytest.mark.parametrize('name',['equipment_find','staff_read','regulations_read','task_read','component_install'])
def test_describe_tool_retains_its_own_name_envelope(name):
    value=dict(answer='',calls=[dict(tool='describe_tool',explanation='TEST ONLY schema boundary',arguments_json=dict(name=name))])
    wire=agent_wire_schema(AgentStep)
    assert permits_envelope(wire,'describe_tool',{'name':name})
    assert decode_agent_wire(AgentStep,json.dumps(value)).calls[0].arguments=={'name':name}
