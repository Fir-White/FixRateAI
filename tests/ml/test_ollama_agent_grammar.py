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
        if 'enum' in props['tool'] and tool not in props['tool']['enum']:continue
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


@pytest.mark.parametrize('name',['equipment_edit','staff_edit','rule_edit','task_assign','component_install'])
def test_actual_write_modes_do_not_advertise_read_only_view(name):
    modes={name:'write','equipment_find':'read'}
    wire=agent_wire_schema(AgentStep,modes)
    assert permits_envelope(wire,name,{'path':{},'body':{}})
    assert not permits_envelope(wire,name,{'path':{},'body':{},'view':{}})
    assert permits_envelope(wire,'equipment_find',{'view':{}})


@pytest.mark.parametrize('name',['equipment_edit','staff_edit','rule_edit','task_assign','component_install'])
def test_unavailable_tools_are_not_in_the_native_grammar(name):
    wire=agent_wire_schema(AgentStep,{'equipment_find':'read'})
    assert not permits_envelope(wire,name,{'body':{}})
