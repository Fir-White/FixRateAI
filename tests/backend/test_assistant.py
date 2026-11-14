"""Real HTTP/PostgreSQL tools, private history and explicit, one-shot approval."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
import pytest
from sqlalchemy import text
from app.schemas.assistant import AgentStep
from app.assistant.tools import TOOLS,available,describe,validate_arguments
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime,login

@pytest.fixture
def assistant_case(managed):
    yield managed
    engine,_,_,_,ids=managed
    with engine.begin() as c:
        p=dict(site=ids['site'])
        c.execute(text('DELETE FROM assistant_attachments WHERE conversation_id IN (SELECT conversation_id FROM assistant_conversations WHERE site_id=:site)'),p)
        c.execute(text('DELETE FROM assistant_actions WHERE conversation_id IN (SELECT conversation_id FROM assistant_conversations WHERE site_id=:site)'),p)
        c.execute(text('DELETE FROM assistant_turns WHERE conversation_id IN (SELECT conversation_id FROM assistant_conversations WHERE site_id=:site)'),p)
        c.execute(text('DELETE FROM assistant_conversations WHERE site_id=:site'),p)

B='/api/v1/assistant'
M=B+'/mcp'

class Scripted:
    response_model='TEST-ONLY-scripted'
    def __init__(self,steps):self.steps=iter(steps);self.messages=[]
    def chat(self,messages,schema,tokens):
        self.messages.append(messages[:])
        if schema.__name__=='ToolSelection':return schema.model_validate(dict(tools=[]))
        step=next(self.steps)
        for call in step['calls']:call['arguments_json']=json.dumps(call.pop('arguments'))
        return schema.model_validate(step)

def rpc(client,name,args=None):
    return client.post(M,json=dict(jsonrpc='2.0',id=1,method=name,params=args or {}),headers={'MCP-Protocol-Version':'2025-06-18','Accept':'application/json, text/event-stream'})

def thread(client,agent='assistant'):
    response=client.post(B+'/conversations',json=dict(agent=agent));assert response.status_code==201,response.text
    return response.json()['conversation_id']

def proposal(client,thread_id,tool,args):
    response=rpc(client,'tools/call',dict(name=tool,arguments=dict(args,conversation_id=thread_id)))
    assert response.status_code==200,response.text
    result=response.json()['result'];assert not result['isError'],result
    return json.loads(result['content'][0]['text'])

def equipment_body(ids):return dict(system_id=str(ids['system']),asset_code='AI-TEST-'+uuid4().hex[:8],name='TEST ONLY assistant asset')

def confirm(client,record,**kw):
    return client.post(B+'/actions/'+record['action_id']+'/confirm',json=dict(payload_sha256=record['payload_sha256'],confirmed=True,**kw))

def test_catalog_is_explicit_and_each_tool_has_real_typed_endpoint(assistant_case):
    _,app,admin,_,_=assistant_case
    known=available(app,'chief_engineer')
    assert len(known)>25
    assert set(known)=={t.name for t in TOOLS if 'chief_engineer' in t.roles}
    for tool in known.values():
        schema=describe(app,tool)
        assert schema['inputSchema']['additionalProperties'] is False
        assert schema['annotations']['readOnlyHint']==(tool.mode=='read')
    personal={'site_switch','session_logout','profile_email','notifications_read_all','notifications_clear','notification_delete','notification_read'}
    assert all(t.mode=='read' or t.name in personal for t in available(app,'director').values())
    assert 'photo_review' not in available(app,'executor','photo')
    assert 'equipment_create' not in available(app,'chief_engineer','photo')

def test_optional_and_missing_required_parameters_follow_current_fastapi_fields(assistant_case):
    from fastapi import HTTPException
    _,app,_,_,_=assistant_case;tools=available(app,'chief_engineer')
    assert validate_arguments(app,tools['equipment_list'],{})==dict(path={},query=dict(limit=25))
    assert validate_arguments(app,tools['equipment_list'],dict(query=dict(limit=25)))['query']==dict(limit=25)
    assert validate_arguments(app,tools['draft_list'],dict(query=dict(import_id=str(uuid4()))))['query']['import_id']
    assert validate_arguments(app,tools['calendar_read'],dict(query=dict(year=2026,month=11)))['query']==dict(year=2026,month=11)
    with pytest.raises(HTTPException) as error:validate_arguments(app,tools['calendar_read'],{})
    assert error.value.status_code==422
    for tool in tools.values():
        try:validate_arguments(app,tool,{})
        except HTTPException as exc:assert exc.status_code==422

def test_mcp_handshake_scoped_reads_and_unknown_tools(assistant_case):
    _,_,admin,_,ids=assistant_case
    assert rpc(admin,'initialize',dict(protocolVersion='2025-06-18',capabilities={},clientInfo=dict(name='TEST',version='1'))) .json()['result']['capabilities']['tools']=={'listChanged':False}
    tools=rpc(admin,'tools/list').json()['result']['tools']
    create=next(t for t in tools if t['name']=='equipment_create')
    assert 'conversation_id' in create['inputSchema']['required']
    assert rpc(admin,'tools/call',dict(name='shell',arguments={})).json()['error']['code']==-32602
    result=rpc(admin,'tools/call',dict(name='catalog_read',arguments={}))
    assert result.status_code==200 and not result.json()['result']['isError']
    assert str(ids['system']) in result.text
    headers={'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-06-18'}
    assert admin.post(M,json=dict(jsonrpc='2.0',method='notifications/initialized'),headers=headers).status_code==202
    assert admin.post(M,content='[1,2]',headers={**headers,'Content-Type':'application/json'}).json()['error']['code']==-32600
    assert admin.post(M,json=dict(jsonrpc='2.0',id=1,method='ping'),headers={**headers,'MCP-Protocol-Version':'invalid'}).status_code==400

def test_proposal_never_writes_business_until_exact_confirmation_and_replay_is_safe(assistant_case):
    engine,_,admin,_,ids=assistant_case;t=thread(admin);body=equipment_body(ids)
    record=proposal(admin,t,'equipment_create',dict(body=body))
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM equipment WHERE asset_code=:code'),dict(code=body['asset_code']))==0
    assert record['status']=='proposed' and record['arguments']['body']['name']==body['name']
    bad=admin.post(B+'/actions/'+record['action_id']+'/confirm',json=dict(payload_sha256='0'*64,confirmed=True))
    assert bad.status_code==409
    response=confirm(admin,record);assert response.status_code==200,response.text
    assert response.json()['status']=='succeeded',response.text
    assert confirm(admin,record).json()==response.json()
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM equipment WHERE asset_code=:code'),dict(code=body['asset_code']))==1
        assert c.scalar(text("SELECT count(*) FROM audit_events WHERE entity_id=:id AND action='confirmed'"),dict(id=record['action_id']))==1

def test_concurrent_confirmation_dispatches_once_and_rejection_is_final(assistant_case):
    engine,_,admin,_,ids=assistant_case;t=thread(admin);body=equipment_body(ids)
    record=proposal(admin,t,'equipment_create',dict(body=body))
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:confirm(admin,record),range(2)))
    assert all(r.status_code==200 for r in responses)
    assert {r.json()['status'] for r in responses}<={'succeeded','executing'}
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM equipment WHERE asset_code=:code'),dict(code=body['asset_code']))==1
    other=proposal(admin,t,'equipment_create',dict(body=equipment_body(ids)))
    assert admin.post(B+'/actions/'+other['action_id']+'/reject').json()['status']=='rejected'
    assert confirm(admin,other).json()['status']=='rejected'

def test_stale_snapshot_expiry_rights_and_cross_owner_protect_changes(assistant_case):
    engine,_,admin,_,ids=assistant_case;t=thread(admin)
    response=admin.post('/api/v1/maintenance/equipment',json=equipment_body(ids));assert response.status_code==201,response.text
    equipment=response.json();eid=equipment['equipment_id']
    record=proposal(admin,t,'equipment_edit',dict(path=dict(equipment_id=eid),body=dict(expected_revision=1,name='AI proposed')))
    changed=admin.patch('/api/v1/maintenance/equipment/'+eid,json=dict(expected_revision=1,name='Human changed'))
    assert changed.status_code==200,changed.text
    assert confirm(admin,record).status_code==409
    assert admin.get(B+'/conversations/'+t).json()['actions'][0]['status']=='stale'
    assert admin.chief.get(B+'/conversations/'+t).status_code==404
    assert confirm(admin.chief,record).status_code==404
    expired=proposal(admin,t,'equipment_create',dict(body=equipment_body(ids)))
    with engine.begin() as c:c.execute(text("UPDATE assistant_actions SET expires_at=now()-interval '1 second' WHERE action_id=:id"),dict(id=expired['action_id']))
    assert confirm(admin,expired).status_code==409
    no_csrf=admin.headers.pop('X-CSRF-Token')
    try:assert confirm(admin,expired).status_code==403
    finally:admin.headers['X-CSRF-Token']=no_csrf

def test_real_chat_runs_tools_and_saves_a_proposal_without_side_effects(assistant_case):
    engine,app,admin,_,ids=assistant_case;t=thread(admin)
    script=Scripted([dict(answer='',calls=[dict(tool='catalog_read',arguments={},explanation='Find systems')]),
                     dict(answer='Предлагаю добавить оборудование.',calls=[dict(tool='equipment_create',arguments=dict(body=equipment_body(ids)),explanation='TEST ONLY requested equipment')])])
    app.state.assistant_provider_factory=lambda:script
    try:
        key=str(uuid4());command=dict(idempotency_key=key,content='TEST ONLY add equipment')
        response=admin.post(B+'/conversations/'+t+'/messages',json=command);assert response.status_code==202,response.text
        value=admin.get(B+'/conversations/'+t).json();turn=value['turns'][0]
        assert turn['status']=='completed',turn
        assert len(value['actions'])==1 and value['actions'][0]['status']=='proposed'
        assert [r['tool'] for r in turn['trace']]==['catalog_read','equipment_create']
        assert 'Подготовлено предложение' in turn['answer']
        assert admin.post(B+'/conversations/'+t+'/messages',json=command).json()['turn_id']==turn['turn_id']
        assert admin.post(B+'/conversations/'+t+'/messages',json=dict(command,content='different')).status_code==409
        assert 'fixrate_session' not in str(script.messages) and 'X-CSRF' not in str(script.messages)
    finally:del app.state.assistant_provider_factory

def test_chat_provider_failure_persists_message_and_no_fabricated_success(assistant_case):
    _,app,admin,_,_=assistant_case;t=thread(admin,'photo')
    class Failure:
        def chat(self,*args):raise RuntimeError('secret MUST NOT be exposed')
    app.state.assistant_provider_factory=Failure
    try:
        response=admin.post(B+'/conversations/'+t+'/messages',json=dict(idempotency_key=str(uuid4()),content='TEST ONLY failure'))
        assert response.status_code==202
        turn=admin.get(B+'/conversations/'+t).json()['turns'][0]
        assert turn['status']=='failed' and turn['error_code']=='ASSISTANT_FAILED'
        assert 'secret' not in json.dumps(turn)
    finally:del app.state.assistant_provider_factory

def test_director_can_chat_but_only_personal_mutations_are_exposed(runtime):
    _,app=runtime
    with closing(login(app,'director')) as client:
        t=thread(client)
        assert client.get(B+'/conversations/'+t).status_code==200
        tools=rpc(client,'tools/list').json()['result']['tools']
        personal={'site_switch','session_logout','profile_email','notifications_read_all','notifications_clear','notification_delete','notification_read'}
        assert tools and all(t['annotations']['readOnlyHint'] or t['name'] in personal for t in tools)
        assert rpc(client,'tools/call',dict(name='equipment_create',arguments={})).json()['error']['code']==-32602

def test_confirmation_rechecks_role_and_never_accepts_a_client_supplied_body(assistant_case):
    engine,_,admin,_,ids=assistant_case;t=thread(admin)
    record=proposal(admin,t,'equipment_create',dict(body=equipment_body(ids)))
    assert confirm(admin,record,body=dict(name='Injected change')).status_code==422
    assert admin.post(B+'/actions/'+record['action_id']+'/confirm',json=dict(payload_sha256=record['payload_sha256'],confirmed=False)).status_code==422
    with engine.begin() as c:c.execute(text("UPDATE site_memberships SET role='technician' WHERE site_id=:site AND user_id=:user"),dict(site=ids['site'],user=ids['user']))
    try:
        assert confirm(admin,record).status_code==404
        assert admin.get(B+'/conversations/'+t).status_code==404
        assert not any(r['conversation_id']==t for r in admin.get(B+'/conversations').json()['items'])
    finally:
        with engine.begin() as c:c.execute(text("UPDATE site_memberships SET role='admin' WHERE site_id=:site AND user_id=:user"),dict(site=ids['site'],user=ids['user']))

def test_unknown_dispatch_result_cannot_be_retried_automatically(assistant_case,monkeypatch):
    from fastapi import HTTPException
    from app.assistant import service
    _,_,admin,_,ids=assistant_case;t=thread(admin);record=proposal(admin,t,'equipment_create',dict(body=equipment_body(ids)));calls=[]
    async def lost_response(*args):calls.append(1);raise HTTPException(502,'Response lost after dispatch')
    monkeypatch.setattr(service,'invoke',lost_response)
    assert confirm(admin,record).json()['status']=='uncertain'
    assert confirm(admin,record).json()['status']=='uncertain'
    assert calls==[1]

def test_history_is_bounded_without_per_turn_queries_and_recovers_interrupted_run(assistant_case):
    from sqlalchemy import event
    engine,_,admin,_,_=assistant_case;t=thread(admin)
    with engine.begin() as c:
        for i in range(31):
            c.execute(text("INSERT INTO assistant_turns(turn_id,conversation_id,request_key,content,status,prompt_version,created_at) VALUES (:id,:thread,:key,:content,:status,'TEST ONLY',now()-interval '10 minutes')"),
                dict(id=uuid4(),thread=t,key=uuid4(),content='TEST ONLY '+str(i),status='running' if i==30 else 'completed'))
    statements=[]
    def capture(conn,cursor,statement,parameters,context,many):
        if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:response=admin.get(B+'/conversations/'+t)
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert response.status_code==200,response.text
    value=response.json();assert value['total']==31 and len(value['turns'])==25
    assert len(statements)<=7
    assert not any(turn['status']=='running' for turn in value['turns'])
    assert len(admin.get(B+'/conversations/'+t+'?offset=25').json()['turns'])==6

def test_internal_scope_pin_rejects_session_context_change(assistant_case):
    from app.assistant.tools import EXPECTED_PRINCIPAL
    _,_,admin,_,ids=assistant_case
    token=EXPECTED_PRINCIPAL.set((ids['user'],uuid4(),'admin'))
    try:assert admin.get('/api/v1/maintenance/management/catalog').status_code==403
    finally:EXPECTED_PRINCIPAL.reset(token)

def test_mcp_rejects_cross_origin_invalid_arguments_and_confirmation_tool(assistant_case):
    _,_,admin,_,_=assistant_case
    response=admin.post(M,json=dict(jsonrpc='2.0',id=1,method='initialize'),headers={'Origin':'https://untrusted.test','Accept':'application/json, text/event-stream'})
    assert response.status_code==403
    assert rpc(admin,'tools/call',dict(name='confirm',arguments={})).json()['error']['code']==-32602
    result=rpc(admin,'tools/call',dict(name='equipment_read',arguments=dict(path=dict(equipment_id='../../secrets'),url='http://untrusted.test'))).json()['result']
    assert result['isError']

def test_assignment_request_survives_multi_name_description_and_continues(assistant_case):
    _,app,admin,_,_=assistant_case;admin=admin.chief;t=thread(admin)
    script=Scripted([
        dict(answer='',calls=[dict(tool='tasks_list',arguments={},explanation='Find nearest maintenance')]),
        dict(answer='',calls=[dict(tool='describe_tool',arguments=dict(name=['assignment_context','assignment_preview']),explanation='Inspect assignment tools')]),
        dict(answer='',calls=[dict(tool='describe_tool',arguments=dict(name='assignment_context'),explanation='Inspect one schema')]),
        dict(answer='Для назначения сначала выберите задание с подтверждёнными условиями.',calls=[]),
    ])
    app.state.assistant_provider_factory=lambda:script
    try:
        response=admin.post(B+'/conversations/'+t+'/messages',json=dict(idempotency_key=str(uuid4()),content='Помоги распределить работников на ближайшее ТО'))
        assert response.status_code==202
        view=admin.get(B+'/conversations/'+t).json();turn=view['turns'][0]
        assert turn['status']=='completed' and turn['error_code'] is None
        assert [s['status'] for s in turn['trace']]==['completed','denied','completed']
        assert not view['actions']
    finally:del app.state.assistant_provider_factory
