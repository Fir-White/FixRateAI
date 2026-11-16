"""Real PostgreSQL/ASGI reads; failures below are explicit fault injection, not data stubs."""
import asyncio,json
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from tests.backend.test_assistant import assistant_case,thread,B,equipment_body
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime
from app.assistant.tools import available,describe,validate_arguments,invoke
from app.assistant.read_transport import read,safe_arguments

def headers(client):return {'cookie':'; '.join(f'{k}={v}' for k,v in client.cookies.items()),'x-csrf-token':client.headers['X-CSRF-Token']}

def test_view_schema_reproduction_and_real_recovery(assistant_case):
    _,app,client,_,ids=assistant_case;tool=available(app,'chief_engineer')['registry_read']
    assert client.post('/api/v1/maintenance/equipment',json=equipment_body(ids)).status_code==201
    schema=describe(app,tool)['inputSchema']
    assert schema['properties']['view']['properties']['limit']['maximum']==25
    valid=dict(view=dict(path=['items'],offset=0,limit=25))
    assert validate_arguments(app,tool,valid)['view']['limit']==25
    invalid=dict(view=dict(path=['items'],offset=0,limit=100))
    with pytest.raises(HTTPException) as error:validate_arguments(app,tool,invalid)
    assert error.value.detail==dict(code='INVALID_VIEW',issues=[dict(field='view.limit',type='less_than_equal')])
    trace=[];args,result=asyncio.run(read(app,tool,invalid,headers(client),trace))
    expected=client.get('/api/v1/maintenance/registry').json()
    assert result['total']==len(expected['items']) and result['items']==expected['items'][:25]
    assert args['view']['limit']==25 and len(trace)==2 and trace[-1]['retry_count']==1
    print(json.dumps(dict(tool=tool.name,arguments=invalid,expected_schema=schema,error=error.value.detail,trace=trace),ensure_ascii=False))

def test_misplaced_pagination_is_repaired_without_dropping_filters(assistant_case):
    _,app,client,_,_=assistant_case;tool=available(app,'chief_engineer')['registry_read'];trace=[]
    args,result=asyncio.run(read(app,tool,dict(query=dict(limit=25,offset=0),view=dict(path=['items'])),headers(client),trace))
    assert args['query']=={} and args['view']['path']==['items'] and result['total']>=0
    trace=[]
    args,root=asyncio.run(read(app,tool,dict(view=dict(path=['objects'],offset=0,limit=25)),headers(client),trace))
    assert args['view']['path']==[] and 'systems' in root and len(trace)==2
    with pytest.raises(HTTPException):asyncio.run(read(app,tool,dict(query=dict(site_id=str(uuid4()))),headers(client),[]))

def test_no_retry_for_denied_or_backend_error_or_write(assistant_case,monkeypatch):
    _,app,client,_,_=assistant_case;tool=available(app,'chief_engineer')['registry_read']
    from app.assistant import read_transport
    for code in (403,503):
        calls=[];trace=[]
        async def fault(*args):calls.append(1);raise HTTPException(code,'injected failure')
        monkeypatch.setattr(read_transport,'invoke',fault)
        with pytest.raises(HTTPException):asyncio.run(read(app,tool,{},headers(client),trace))
        assert calls==[1] and trace[0]['retry_count']==0
    with pytest.raises(ValueError):asyncio.run(read(app,available(app,'chief_engineer')['task_assign'],{},headers(client),[]))

def test_trace_redacts_credentials_and_arbitrary_strings():
    data=safe_arguments(dict(query=dict(q='secret in search',password='SECRET',token='TOKEN'),body=dict(api_key='KEY'),path=dict(task_id=str(uuid4()))))
    assert all(s not in json.dumps(data) for s in ('secret in search','SECRET','TOKEN','KEY'))
    from app.assistant.inventory_report import requested
    assert requested('Проанализируй все доступные объекты и оборудование')
    assert not requested('Проанализируй все оборудование в Excel')

def test_report_backend_failure_is_not_empty_data(assistant_case,monkeypatch):
    _,app,client,_,_=assistant_case
    from app.assistant import read_transport
    from app.assistant.inventory_report import report
    async def unavailable(*args):raise HTTPException(503,'injected unavailable')
    monkeypatch.setattr(read_transport,'invoke',unavailable)
    trace=[]
    answer=asyncio.run(report(app,available(app,'chief_engineer')['inventory_read'],headers(client),trace,lambda:None))
    assert 'backend недоступен' in answer and 'Реестр оборудования пуст' not in answer and len(trace)==1

def test_llm_view_schema_matches_backend_validation(assistant_case):
    from app.schemas.assistant import ResultView
    _,app,_,_,_=assistant_case
    for name in ('registry_read','overview_read','regulations_read','calendar_read','staff_calendar'):
        tool=available(app,'chief_engineer')[name];schema=describe(app,tool)['inputSchema']['properties']['view']
        assert schema==ResultView.model_json_schema()
        assert schema['additionalProperties'] is False and schema['properties']['offset']['minimum']==0 and schema['properties']['limit']['maximum']==25
        for view,valid in (({'path':[],'offset':0,'limit':25},True),({'limit':100},False),({'limit':25,'offset':0,'unknown':1},False),({'path':'objects'},False)):
            try:ResultView.model_validate(view);accepted=True
            except ValueError:accepted=False
            assert accepted==valid

def test_inventory_honors_each_site_membership(assistant_case):
    engine,_,client,_,ids=assistant_case;site=uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO sites(site_id,name) VALUES (:id,'ZZ P0 restricted')"),dict(id=site))
        c.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:user,'executor')"),dict(site=site,user=ids['user']))
    try:
        first=client.get(B+'/workspace/inventory').json();second=client.get(B+'/workspace/inventory?site_offset=1').json()
        assert first['site_total']==2 and second['site']['status']=='access_denied' and second['total'] is None
    finally:
        with engine.begin() as c:
            c.execute(text('DELETE FROM site_memberships WHERE site_id=:id'),dict(id=site))
            c.execute(text('DELETE FROM sites WHERE site_id=:id'),dict(id=site))

def test_inventory_page_budget_and_full_count(assistant_case):
    from sqlalchemy import event
    engine,app,client,_,ids=assistant_case
    for _ in range(30):assert client.post('/api/v1/maintenance/equipment',json=equipment_body(ids)).status_code==201
    statements=[]
    def capture(conn,cursor,statement,parameters,context,many):
        if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:response=client.get(B+'/workspace/inventory')
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert response.status_code==200 and response.json()['total']==30 and len(response.json()['items'])==25
    assert len(statements)<=40,statements
    assert len(client.get(B+'/workspace/inventory?offset=25').json()['items'])==5
    from app.assistant.inventory_report import report
    trace=[];answer=asyncio.run(report(app,available(app,'chief_engineer')['inventory_read'],headers(client),trace,lambda:None))
    assert len(trace)==2 and 'Единиц оборудования: 30' in answer
    assert all(item['asset_code'] in answer for item in client.get('/api/v1/maintenance/registry').json()['items'])

def test_inventory_matches_postgres_and_chat_never_needs_workbooks(assistant_case):
    engine,app,client,_,ids=assistant_case
    from tests.backend.test_management import config
    from datetime import date
    created=client.post('/api/v1/maintenance/equipment',json=equipment_body(ids));assert created.status_code==201
    eq=created.json()
    configured=client.chief.post('/api/v1/maintenance/equipment/'+eq['equipment_id']+'/service-configurations',json=config(date.today()))
    assert configured.status_code==201,configured.text
    response=client.get(B+'/workspace/inventory');assert response.status_code==200,response.text
    inventory=response.json();registry=client.get('/api/v1/maintenance/registry').json()
    assert inventory['total']==len(registry['items'])
    assert {r['id'] for r in inventory['items']}=={r['equipment_id'] for r in registry['items'][:25]}
    for item,source in zip(inventory['items'],registry['items']):
        assert item['operations']==len(source['services'])
    from tests.backend.test_assistant import Scripted
    model=Scripted([dict(answer='',calls=[dict(tool='inventory_read',arguments={},explanation='TEST request authorized registry facts')])],
                   goals=[dict(id='inventory',title='Проверить весь доступный реестр и регламенты',tool='inventory_read',requires_full_list=True)])
    app.state.assistant_provider_factory=lambda:model
    try:
        chat=thread(client)
        sent=client.post(B+f'/conversations/{chat}/messages',json=dict(content='Проанализируй все доступные объекты и оборудование. Покажи, какие системы требуют технического обслуживания, сколько операций предусмотрено регламентами и по каким объектам не хватает данных для планирования.',idempotency_key=str(uuid4())))
        assert sent.status_code==202
        view=client.get(B+'/conversations/'+chat).json();turn=view['turns'][-1]
        assert turn['status']=='completed' and 'Excel' not in turn['answer'] and not view['actions']
        assert all(item['name'] in turn['answer'] for item in inventory['items'])
        assert any(t['tool']=='inventory_read' and t['status']=='completed' for t in turn['trace'])
        print(json.dumps(dict(success_trace=turn['trace'],answer=turn['answer']),ensure_ascii=False))
    finally:del app.state.assistant_provider_factory

def test_empty_registry_is_distinct_from_access_denied(assistant_case):
    _,app,client,_,_=assistant_case
    data=client.get(B+'/workspace/inventory').json()
    assert data['site']['status']=='ok' and data['total']==0
    from tests.backend.test_runtime_integration import login
    from contextlib import closing
    with closing(login(app,'executor')) as executor:
        data=executor.get(B+'/workspace/inventory').json()
        assert data['site']['status']=='access_denied' and data['total'] is None
