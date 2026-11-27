"""Combined malformed optional projection + envelope failures; genuine authorized API."""
import asyncio
import pytest
from fastapi import HTTPException
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case,equipment_body
from tests.backend.test_assistant_p0 import headers
from app.assistant.tools import available
from app.assistant.read_transport import read

@pytest.mark.parametrize('args',[
    {'query':None}, {'path':None},
    {'query':None,'view':{'path':['items','name']}},
    {'view':{'path':['systems','invented','regulations']},'limit':50},
    {'query':None,'path':None,'view':{'path':['unknown'],'limit':100}},
])
def test_bounded_repair_reads_real_equipment_without_relaxing_backend(assistant_case,args):
    _,app,client,_,ids=assistant_case
    reply=client.post('/api/v1/maintenance/equipment',json=equipment_body(ids));assert reply.status_code==201
    tool=available(app,'chief_engineer')['equipment_list'];trace=[]
    checked,value=asyncio.run(read(app,tool,args,headers(client),trace))
    assert reply.json()['equipment_id'] in str(value)
    assert 2<=len(trace)<=3 and trace[0]['status']=='denied' and trace[-1]['status']=='completed'
    assert checked['query']=={'limit':25} and checked['path']=={}

@pytest.mark.parametrize('args',[
    {'query':{'site_id':'00000000-0000-0000-0000-000000000001'},'view':{'path':['unknown']}},
    {'query':{'q':'x','invented':True}}, {'path':{'equipment_id':'not-a-uuid'}},
    {'body':{'ignored':'no'}}, {'query':[]},
])
def test_recovery_does_not_drop_selectors_or_unknown_fields(assistant_case,args):
    _,app,client,_,_=assistant_case;trace=[]
    tool=available(app,'chief_engineer')['equipment_read' if 'path' in args else 'equipment_list']
    with pytest.raises(HTTPException):asyncio.run(read(app,tool,args,headers(client),trace))
    assert len(trace)<=2 and all(row['status']=='denied' for row in trace)
