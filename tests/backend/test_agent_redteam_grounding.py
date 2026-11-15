"""Explicit router fault injection; evidence still comes from real authorized PostgreSQL."""
from uuid import uuid4
import json
import pytest
from fastapi import HTTPException
from app.schemas.assistant import ToolSelection,AgentStep
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case,thread,B

@pytest.mark.parametrize('code',('ABSENT-404','НЕТ-007','NODE_404','VALVE/404','404-A'))
def test_empty_model_route_cannot_claim_absence_without_authorized_search(assistant_case,code):
    _,app,client,_,_=assistant_case;seen=[]
    class OmittedRoute:
        def chat(self,messages,schema,tokens):
            if schema is ToolSelection:return ToolSelection(tools=[])
            return AgentStep(answer='',calls=[])
        def text(self,messages,tokens):
            evidence=json.loads(messages[-1]['content'])['verified_results'];seen.extend(evidence)
            assert evidence[0]['условия поиска']['параметры']['asset_code']==code
            assert evidence[0]['результат']['total']==0
            return 'По проверенному коду записи не найдены.'
    app.state.assistant_provider_factory=OmittedRoute
    try:
        chat=thread(client)
        reply=client.post(B+f'/conversations/{chat}/messages',json=dict(content=f'Найди оборудование с кодом «{code}».',idempotency_key=str(uuid4())))
        assert reply.status_code==202,reply.text
        state=client.get(B+'/conversations/'+chat).json();turn=state['turns'][-1]
        assert turn['status']=='completed' and seen and not state['actions'],turn
        assert any(row['tool']=='equipment_find' and row['status']=='completed' and row['result']['total']==0 for row in turn['trace'])
    finally:del app.state.assistant_provider_factory

def test_mandatory_lookup_backend_failure_is_not_an_empty_registry(assistant_case,monkeypatch):
    from app.assistant import read_transport
    _,app,client,_,_=assistant_case
    class OmittedRoute:
        def chat(self,messages,schema,tokens):return ToolSelection(tools=[])
        def text(self,*args):raise AssertionError('Do not invent facts after a failed mandatory read')
    async def unavailable(*args):raise HTTPException(503,'Explicit backend fault')
    monkeypatch.setattr(read_transport,'invoke',unavailable);app.state.assistant_provider_factory=OmittedRoute
    try:
        chat=thread(client)
        reply=client.post(B+f'/conversations/{chat}/messages',json=dict(content='Найди оборудование с кодом ABSENT-404.',idempotency_key=str(uuid4())))
        assert reply.status_code==202,reply.text
        state=client.get(B+'/conversations/'+chat).json();turn=state['turns'][-1]
        assert turn['status']=='completed' and 'не хватает проверенных сведений' in turn['answer'] and not state['actions'],turn
        failed=[row for row in turn['trace'] if row['tool']=='equipment_find']
        assert len(failed)==1 and failed[0]['error_type']=='backend_unavailable'
    finally:del app.state.assistant_provider_factory

@pytest.mark.parametrize('published,unpublished',[(0,0),(1,0),(2,0),(0,1),(1,1)])
def test_regulations_are_not_inferred_from_an_empty_task_calendar(assistant_case,published,unpublished):
    from datetime import date
    from tests.backend.test_management import equipment,config
    _,app,admin,_,ids=assistant_case;client=admin.chief;asset=equipment(admin,ids)
    for index in range(published+unpublished):
        body=config(date(2027,1,1),code='REG-'+str(index),title='Audit monthly operation '+str(index),enabled=index<published,
            pattern=dict(frequency='month',interval=1,anchor_date='2027-01-01',month_days=[15]))
        response=client.post('/api/v1/maintenance/equipment/'+asset['equipment_id']+'/service-configurations',json=body)
        assert response.status_code==201,response.text
    class OmittedRoute:
        def chat(self,messages,schema,tokens):return ToolSelection(tools=[])
        def text(self,*args):raise AssertionError('Regulatory counts must come from the authorized backend')
    app.state.assistant_provider_factory=OmittedRoute
    try:
        chat=thread(client)
        reply=client.post(B+f'/conversations/{chat}/messages',json=dict(content=f"Какие опубликованные операции ТО есть у насоса с кодом {asset['asset_code']}?",idempotency_key=str(uuid4())))
        assert reply.status_code==202,reply.text
        view=client.get(B+'/conversations/'+chat).json();turn=view['turns'][-1]
        assert turn['status']=='completed' and not view['actions'],turn
        assert f'Опубликованных конфигураций обслуживания: **{published}**' in turn['answer']
        assert f'Неопубликованных конфигураций: **{unpublished}**' in turn['answer']
        for index in range(published):assert 'Audit monthly operation '+str(index) in turn['answer']
        assert {t['tool'] for t in turn['trace'] if t['status']=='completed'}=={'equipment_find','regulations_read'}
        assert client.get('/api/v1/assistant/workspace/tasks?period=all&active_only=false').json()['total']==0
    finally:del app.state.assistant_provider_factory

def test_exact_equipment_code_is_not_lost_beyond_name_search_page(assistant_case):
    from tests.backend.test_assistant import equipment_body
    _,_,client,_,ids=assistant_case
    for index in range(30):
        body=equipment_body(ids);body.update(asset_code=f'A-{index:03}',name='Mention ZZZ-TARGET in another name')
        assert client.post('/api/v1/maintenance/equipment',json=body).status_code==201
    body=equipment_body(ids);body.update(asset_code='ZZZ-TARGET',name='Exact target')
    saved=client.post('/api/v1/maintenance/equipment',json=body);assert saved.status_code==201
    search=client.get(B+'/workspace/equipment',params=dict(q='ZZZ-TARGET')).json()
    assert search['total']==31 and len(search['items'])==25 and all(r['asset_code']!='ZZZ-TARGET' for r in search['items'])
    exact=client.get(B+'/workspace/equipment',params=dict(asset_code='ZZZ-TARGET')).json()
    assert exact['total']==1 and exact['items'][0]['equipment_id']==saved.json()['equipment_id']

@pytest.mark.parametrize('code,decoy', [('A_B','AXB'),('A%B','AXXB'),('AB\\CD','ABXCD'),('код-01','код-010'),('LONG'+100*'A','LONG'+100*'A'+'1')])
def test_exact_code_is_literal_and_preserves_long_unicode_values(assistant_case,code,decoy):
    from tests.backend.test_assistant import equipment_body
    from app.assistant.grounding import equipment_code
    _,_,client,_,ids=assistant_case
    for value in (code,decoy):
        body=equipment_body(ids);body.update(asset_code=value)
        response=client.post('/api/v1/maintenance/equipment',json=body);assert response.status_code==201,response.text
    rows=client.get(B+'/workspace/equipment',params=dict(asset_code=code)).json()
    assert rows['total']==1 and rows['items'][0]['asset_code']==code
    assert equipment_code(f'Найди оборудование с кодом «{code}».')==code
