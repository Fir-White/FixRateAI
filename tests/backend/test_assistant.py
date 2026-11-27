"""Real HTTP/PostgreSQL tools, private history and explicit, one-shot approval."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
from copy import deepcopy
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
        c.execute(text('DELETE FROM assistant_model_preferences WHERE site_id=:site'),p)
        c.execute(text('DELETE FROM assistant_attachments WHERE conversation_id IN (SELECT conversation_id FROM assistant_conversations WHERE site_id=:site)'),p)
        c.execute(text('DELETE FROM assistant_actions WHERE conversation_id IN (SELECT conversation_id FROM assistant_conversations WHERE site_id=:site)'),p)
        c.execute(text('DELETE FROM assistant_turns WHERE conversation_id IN (SELECT conversation_id FROM assistant_conversations WHERE site_id=:site)'),p)
        c.execute(text('DELETE FROM assistant_conversations WHERE site_id=:site'),p)

B='/api/v1/assistant'
M=B+'/mcp'

def test_stop_is_scoped_idempotent_and_prevents_late_proposals(assistant_case):
    engine,app,admin,_,ids=assistant_case;chat=thread(admin);turn=uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO assistant_turns(turn_id,conversation_id,request_key,content,status,prompt_version) VALUES (:turn,:chat,:key,'TEST','running','TEST')"),dict(turn=turn,chat=chat,key=uuid4()))
    url=B+f'/conversations/{chat}/turns/{turn}/stop'
    assert admin.chief.post(url).status_code==404
    assert admin.post(url).json()['stopped'] is True
    assert admin.post(url).json()['stopped'] is False
    saved=admin.get(B+'/conversations/'+chat).json()['turns'][0]
    assert saved['status']=='failed' and saved['error_code']=='ASSISTANT_STOPPED'
    from app.assistant.service import propose,conversation
    from fastapi import HTTPException
    import asyncio
    with app.state.factory() as session:
        principal=admin.app_principal if hasattr(admin,'app_principal') else None
        # The proposal guard checks the locked turn before any downstream request.
        with pytest.raises(HTTPException) as exc:
            asyncio.run(propose(app,session,principal,{},available(app,'chief_engineer')['equipment_create'],{},'TEST',{},turn))
        assert exc.value.status_code==409

def test_delete_conversation_removes_owned_files_and_blocks_executing_action(assistant_case):
    from app.storage import safe_storage_path
    engine,app,admin,_,ids=assistant_case;chat=thread(admin)
    response=admin.post(B+f'/conversations/{chat}/attachments',files={'file':('TEST.xlsx',b'PK TEST','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert response.status_code==201
    file_id=response.json()['attachment_id']
    with engine.connect() as c:key=c.scalar(text('SELECT storage_key FROM assistant_attachments WHERE attachment_id=:id'),dict(id=file_id))
    path=safe_storage_path(app.state.settings.photo_storage_root,key);assert path.exists()
    record=proposal(admin,chat,'equipment_create',dict(body=equipment_body(ids)))
    with engine.begin() as c:c.execute(text("UPDATE assistant_actions SET status='executing' WHERE action_id=:id"),dict(id=record['action_id']))
    assert admin.chief.delete(B+'/conversations/'+chat).status_code==404
    assert admin.delete(B+'/conversations/'+chat).status_code==409 and path.exists()
    with engine.begin() as c:c.execute(text("UPDATE assistant_actions SET status='rejected' WHERE action_id=:id"),dict(id=record['action_id']))
    assert admin.delete(B+'/conversations/'+chat).json()['deleted']
    assert admin.get(B+'/conversations/'+chat).status_code==404 and not path.exists()
    assert admin.get(B+'/attachments/'+file_id).status_code==404

def test_rename_and_pin_are_private_and_pinned_chats_precede_newer_chats(assistant_case):
    engine,_,admin,_,_=assistant_case
    old,new=thread(admin),thread(admin)
    url=B+'/conversations/'+old
    with engine.begin() as conn:
        conn.execute(text("UPDATE assistant_conversations SET updated_at=now()-interval '1 day' WHERE conversation_id=:id"),dict(id=old))
    assert admin.chief.patch(url,json={'pinned':True}).status_code==404
    assert admin.patch(url,json={'title':'  '}).status_code==422
    assert admin.patch(url,json={}).status_code==422
    assert admin.patch(url,json={'pinned':None}).status_code==422
    result=admin.patch(url,json={'title':'  Контроль приборов  ','pinned':True})
    assert result.status_code==200
    saved=result.json()
    assert saved['title']=='Контроль приборов' and saved['pinned_at']
    assert admin.patch(url,json={'pinned':True}).json()['pinned_at']==saved['pinned_at']
    items=admin.get(B+'/conversations').json()['items']
    assert [row['conversation_id'] for row in items[:2]]==[old,new]
    assert admin.patch(url,json={'pinned':False}).json()['pinned_at'] is None
    assert admin.get(url).json()['conversation']['title']=='Контроль приборов'
    assert admin.get(B+'/conversations').json()['items'][0]['conversation_id']==new

@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_chat_mutation_rechecks_membership_after_initial_authentication(assistant_case, method):
    from sqlalchemy import event
    engine,_,admin,_,ids=assistant_case
    chat=thread(admin)
    params=dict(site=ids['site'],user=ids['user'])
    changed=False

    def change_role_after_first_auth(conn,cursor,statement,parameters,context,many):
        nonlocal changed
        if not changed and 'FROM fixrate_sessions x JOIN users u' in statement and 'FOR SHARE' not in statement:
            changed=True
            with engine.begin() as writer:
                writer.execute(text("UPDATE site_memberships SET role='technician' WHERE site_id=:site AND user_id=:user"),params)

    event.listen(engine,'after_cursor_execute',change_role_after_first_auth)
    try:
        options=dict(json={'title':'STILL PRIVATE'}) if method=='PATCH' else {}
        response=admin.request(method,B+'/conversations/'+chat,**options)
        assert changed and response.status_code==403
    finally:
        event.remove(engine,'after_cursor_execute',change_role_after_first_auth)
        with engine.begin() as writer:
            writer.execute(text("UPDATE site_memberships SET role='admin' WHERE site_id=:site AND user_id=:user"),params)
    data=admin.get(B+'/conversations/'+chat).json()
    assert data['conversation']['title']=='Новый диалог'

@pytest.mark.parametrize('question',['ГОТОВ!','Да','Согласна.','Подтверждаю','назначай его'])
def test_short_followup_keeps_conversation_context(question):
    from app.assistant.service import needs_history
    assert needs_history(question)

def test_independent_identity_question_does_not_reuse_history():
    from app.assistant.service import needs_history
    assert not needs_history('Ты кто по жизни?')

def test_short_task_choice_uses_prior_assignment_question():
    from app.assistant.service import needs_history
    assert needs_history('контроль приборов','Укажите конкретное задание, на которое назначить Морозова.')
    assert not needs_history('контроль приборов','Назначение проверено.')
    from app.assistant.service import selection_matches_title
    assert selection_matches_title('контроль приборов','Контроль параметров показаний приборов')
    assert not selection_matches_title('контроль приборов','Проверка управляющего модуля')
    from app.assistant.service import matching_tasks
    tasks=[dict(summary='Контроль приборов',scheduledStart='2026-11-16T09:00:00+05:00'),dict(summary='Контроль приборов',scheduledStart='2026-12-16T09:00:00+05:00')]
    assert matching_tasks(tasks,'контроль приборов','Назначь на ближайшее ТО')==tasks[:1]
    assert len(matching_tasks(tasks,'контроль приборов','Назначь на ТО'))==2
    assert len(matching_tasks([tasks[0],tasks[0]],'контроль приборов','ближайшее ТО'))==2

def test_failed_assignment_offers_real_task_ids_and_resolves_only_displayed_choice():
    from app.assistant.service import task_choice_prompt,chosen_task_id
    identity=str(uuid4());unlisted=str(uuid4())
    records=[dict(tool='tasks_find',result=dict(items=[dict(id=identity,summary='Контроль приборов',equipmentName='ИТП',mandatoryDueDate='2026-11-16',state='draft')],total=51)),dict(tool='task_read',status_code=422,error='Нужен параметр')]
    answer=task_choice_prompt(records)
    assert identity in answer and 'Контроль приборов' in answer and 'Выберите задание' in answer
    assert chosen_task_id('1',answer)==identity and chosen_task_id(identity,answer)==identity
    assert chosen_task_id(unlisted,answer) is None and chosen_task_id('2',answer) is None
    assert chosen_task_id('1',f'1. Заголовок (ID: {unlisted}) — работа (ID: {identity})')==identity
    assert task_choice_prompt(records[:1]) is None

def test_short_confirmation_includes_prior_question_and_does_not_create_action(assistant_case):
    engine,app,admin,_,_=assistant_case;t=thread(admin)
    class Provider:
        def __init__(self):self.context=None
        def chat(self,messages,schema,tokens):
            assert schema.__name__=='ToolSelection'
            self.context=json.loads(messages[-1]['content'])
            return schema(tools=[],goals=[dict(id='assignment',title='Уточнить график и подготовить отдельное назначение',tool='')])
    model=Provider();app.state.assistant_provider_factory=lambda:model
    try:
        with engine.begin() as c:
            c.execute(text("INSERT INTO assistant_turns(turn_id,conversation_id,request_key,content,answer,status,prompt_version,created_at) VALUES (:id,:thread,:key,:content,:answer,'completed','TEST',now()-interval '1 minute')"),dict(id=uuid4(),thread=t,key=uuid4(),content='Назначь сотрудника',answer='Готовы подтвердить график?'))
        response=admin.post(B+'/conversations/'+t+'/messages',json=dict(idempotency_key=str(uuid4()),content='ГОТОВ!'))
        assert response.status_code==202
        result=admin.get(B+'/conversations/'+t).json()
        assert model.context['question']=='ГОТОВ!'
        previous=model.context['context']['history'][0]
        assert previous['content']=='Назначь сотрудника' and previous['answer']=='Готовы подтвердить график?'
        turn=result['turns'][-1]
        assert result['actions']==[] and turn['workflow']['outcome']=='blocked'
        assert turn['workflow']['goals'][0]['status']=='blocked' and 'Незавершённые пункты' in turn['answer']
    finally:del app.state.assistant_provider_factory

def test_progress_facts_are_bounded_and_do_not_claim_full_page():
    from app.assistant.service import progress_fact
    assert progress_fact('tasks_find',{'total':30,'items':[{},{}]})=={'total':30,'shown':2}
    assert progress_fact('tasks_find',{'total':0,'items':[]})=={'total':0,'shown':0}
    assert progress_fact('tasks_find',{'total':'30','items':[]}) is None
    assert progress_fact('assignment_preview',{'command':None})=={'ready':False}
    assert progress_fact('assignment_preview',{'command':{'private':'not persisted'}})=={'ready':True}
    assert progress_fact('staff_read',{'private':'not persisted'}) is None

def test_unknown_search_parameters_give_specific_safe_feedback(assistant_case):
    from fastapi import HTTPException
    _,app,_,_,_=assistant_case
    with pytest.raises(HTTPException) as exc:validate_arguments(app,available(app,'chief_engineer')['tasks_find'],{'query':{'invalid_key':True}})
    assert exc.value.status_code==422 and 'invalid_key' in exc.value.detail and 'period' in exc.value.detail

def test_readable_evidence_translates_only_known_fields_and_keeps_original():
    from app.assistant.service import readable_evidence
    source={'tool':'tasks_find','source_arguments':{'query':{'period':'upcoming','active_only':True}},'result':{'items':[{'equipment_id':'7222c0b4-80fb-48db-82e7-f5ddc20d6f10','name':'draft','status':'draft','dataOrigin':'synthetic_demo'}]}}
    result=readable_evidence(source)
    assert result['источник']!='tasks_find' and result['условия поиска']['параметры']['период']=='предстоящие'
    item=result['результат']['items'][0]
    assert 'equipment_id' not in item and item['name']=='draft' and item['статус']=='черновик'
    assert item['происхождение данных']=='демонстрационные данные' and source['result']['items'][0]['status']=='draft'

class Scripted:
    response_model='TEST-ONLY-scripted'
    def __init__(self,steps,goals=None):
        # Test setup supplies a semantic plan; production never infers a plan
        # from a scripted call list. The default is this fixture's terminal call.
        steps=deepcopy(steps)
        terminal=next((call['tool'] for step in reversed(steps) for call in reversed(step['calls']) if call['tool']!='describe_tool'),'')
        self.goals=goals if goals is not None else [dict(id='requested-outcome',title='TEST requested outcome',tool=terminal)]
        self.steps=iter(steps);self.messages=[]
    def chat(self,messages,schema,tokens):
        self.messages.append(messages[:])
        if schema.__name__=='ToolSelection':return schema.model_validate(dict(tools=[],goals=self.goals))
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
    personal={'site_switch','session_logout','profile_email','notifications_read_all','notifications_clear','notification_delete','notification_read','chat_model_select'}
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
        assert {r['tool'] for r in turn['trace']}=={'catalog_read','equipment_create'}
        assert turn['workflow']['outcome']=='awaiting_confirmation'
        assert turn['workflow']['goals'][0]['action_id']==value['actions'][0]['action_id']
        with engine.connect() as c:
            assert c.scalar(text('SELECT count(*) FROM equipment WHERE asset_code=:code'),dict(code=value['actions'][0]['arguments']['body']['asset_code']))==0
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

def test_live_progress_is_durable_and_legacy_profiles_use_unified_role_tools(assistant_case):
    engine,app,admin,_,ids=assistant_case;t=thread(admin,'photo');observed=[]
    class Observed(Scripted):
        def chat(self,messages,schema,tokens):
            with engine.connect() as c:
                trace=c.scalar(text('SELECT trace FROM assistant_turns WHERE conversation_id=:id'),dict(id=t))
            observed.append(trace)
            return super().chat(messages,schema,tokens)
    script=Observed([dict(answer='',calls=[dict(tool='catalog_read',arguments={},explanation='TEST ONLY read')]),
        dict(answer='TEST ONLY proposal',calls=[dict(tool='equipment_create',arguments=dict(body=equipment_body(ids)),explanation='TEST ONLY create')])])
    app.state.assistant_provider_factory=lambda:script
    try:
        r=admin.post(B+'/conversations/'+t+'/messages',json=dict(idempotency_key=str(uuid4()),content='TEST ONLY create equipment using unified legacy chat'))
        assert r.status_code==202
        view=admin.get(B+'/conversations/'+t).json();turn=view['turns'][0]
        assert observed[0][-1]['tool']=='__planning' and observed[0][-1]['status']=='running'
        assert any(item['tool']=='catalog_read' and item['status']=='completed' for item in observed[-1])
        assert observed[-1][-1]['tool']=='__responding'
        assert all(s.get('at') for s in turn['trace']) and all(not s['tool'].startswith('__') for s in turn['trace'])
        assert view['actions'][0]['tool_name']=='equipment_create' and view['actions'][0]['status']=='proposed'
        assert confirm(admin,view['actions'][0]).json()['status']=='succeeded'
    finally:del app.state.assistant_provider_factory

def test_director_can_chat_but_only_personal_mutations_are_exposed(runtime):
    _,app=runtime
    with closing(login(app,'director')) as client:
        t=thread(client)
        assert client.get(B+'/conversations/'+t).status_code==200
        tools=rpc(client,'tools/list').json()['result']['tools']
        personal={'site_switch','session_logout','profile_email','notifications_read_all','notifications_clear','notification_delete','notification_read','chat_model_select'}
        assert tools and all(t['annotations']['readOnlyHint'] or t['name'] in personal for t in tools)
        assert rpc(client,'tools/call',dict(name='equipment_create',arguments={})).json()['error']['code']==-32602

def test_director_can_rename_and_pin_own_chat_without_granting_operational_writes(assistant_case):
    _,app,admin,_,_=assistant_case
    own=thread(admin)
    with closing(login(app,'director')) as client:
        chat=thread(client)
        try:
            response=client.patch(B+'/conversations/'+chat,json={'title':'Мой личный чат','pinned':True})
            assert response.status_code==200
            assert response.json()['title']=='Мой личный чат' and response.json()['pinned_at']
            assert client.patch(B+'/conversations/'+own,json={'pinned':True}).status_code==404
            assert client.patch('/api/v1/maintenance/operations/'+str(uuid4()),json={'title':'Нельзя менять'}).status_code==403
        finally:
            assert client.delete(B+'/conversations/'+chat).status_code==200

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
    ],goals=[dict(id='assignment',title='Подготовить проверенное назначение после выбора задания',tool='task_assign')])
    app.state.assistant_provider_factory=lambda:script
    try:
        response=admin.post(B+'/conversations/'+t+'/messages',json=dict(idempotency_key=str(uuid4()),content='Помоги распределить работников на ближайшее ТО'))
        assert response.status_code==202
        view=admin.get(B+'/conversations/'+t).json();turn=view['turns'][0]
        assert turn['status']=='completed' and turn['error_code'] is None
        assert any(s['tool']=='tasks_list' and s['status']=='completed' for s in turn['trace'])
        assert any(s['tool']=='describe_tool' and s['status']=='denied' for s in turn['trace'])
        assert len(script.messages)>=5  # planning, read, invalid description, repair, honest stop
        assert turn['workflow']['goals'][0]['status']=='partial' and turn['workflow']['outcome']=='partial'
        assert not view['actions'] and 'Незавершённые пункты' in turn['answer']
    finally:del app.state.assistant_provider_factory

@pytest.mark.parametrize('boundary',['steps','repeat','calls','empty','deadline','final_failure'])
def test_bounded_search_finishes_with_an_honest_answer_and_no_writes(assistant_case,monkeypatch,boundary):
    import time
    from app.assistant import service
    from ml_service.app.providers.ollama import OllamaFailure
    engine,app,admin,_,ids=assistant_case;t=thread(admin)
    if boundary=='calls':monkeypatch.setattr(service,'MAX_TOOL_CALLS',1)
    class Bounded:
        response_model='TEST-ONLY-bounded'
        def __init__(self):self.steps=0;self.context=None
        def chat(self,messages,schema,tokens):
            if schema.__name__=='ToolSelection':
                self.context=json.loads(messages[-1]['content'])
                if boundary=='deadline':self.deadline=time.monotonic()+5
                return schema(tools=[],goals=[dict(id='worker',title='Проверить конкретного работника перед сравнением результативности',tool='staff_read')])
            assert schema.__name__=='AgentStep'  # no generative final may certify an unfinished objective
            self.steps+=1
            if boundary=='final_failure' and self.steps>1:raise OllamaFailure('OLLAMA_TIMEOUT')
            if boundary=='empty':return schema(answer='  ',calls=[])
            args={} if boundary in ('repeat','final_failure','calls') else dict(query=dict(offset=self.steps*25))
            calls=[dict(tool='staff_find',arguments_json=json.dumps(args),explanation='TEST ONLY scoped prerequisite read')]
            if boundary=='calls':calls.append(dict(tool='catalog_read',arguments_json='{}',explanation='TEST ONLY second read'))
            return schema(answer='TEST ONLY intermediate, not a final result',calls=calls)
    model=Bounded();app.state.assistant_provider_factory=lambda:model
    try:
        with engine.connect() as c:before=c.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site'),dict(site=ids['site']))
        r=admin.post(B+'/conversations/'+t+'/messages',json=dict(idempotency_key=str(uuid4()),content='Кто самый результативный работник?'))
        assert r.status_code==202
        view=admin.get(B+'/conversations/'+t).json();turn=view['turns'][0]
        if boundary=='final_failure':
            # The last required execution inference failed; saved facts survive.
            assert turn['status']=='failed' and turn['error_code']=='OLLAMA_TIMEOUT'
        else:assert turn['status']=='completed' and turn['error_code'] is None
        assert 'предел шагов' not in turn['answer'].casefold() and 'intermediate' not in turn['answer']
        assert model.context['question']=='Кто самый результативный работник?'
        assert all(item['content']!=model.context['question'] for item in model.context['context']['history'])
        assert view['actions']==[]
        assert turn['workflow']['outcome'] in ('partial','blocked') and 'Незавершённые пункты' in turn['answer']
        with engine.connect() as c:
            state=c.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'),dict(id=turn['turn_id']))
        expected_reads=dict(steps=6,repeat=2,calls=1,empty=0,deadline=0,final_failure=1)[boundary]
        assert len(state['evidence'])==expected_reads
        assert state['metrics']['tool_calls']==expected_reads
        assert model.steps<=6
        assert all(proof['tool']=='staff_find' for proof in state['evidence'])
        if state['evidence']:
            source=state['evidence'][0]['arguments']
            assert source['query'].get('offset',0)==(25 if boundary=='steps' else 0)
        with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site'),dict(site=ids['site']))==before
    finally:del app.state.assistant_provider_factory

def test_timeout_after_reading_keeps_findings_and_explains_incomplete_check(assistant_case):
    from ml_service.app.providers.ollama import OllamaFailure
    engine,app,admin,_,_=assistant_case;t=thread(admin)
    class Interrupted:
        def __init__(self):self.steps=0
        def chat(self,messages,schema,tokens):
            if schema.__name__=='ToolSelection':return schema(tools=[],goals=[dict(id='equipment',title='Проверить карточку выбранного оборудования',tool='equipment_read')])
            self.steps+=1
            if self.steps>1:raise OllamaFailure('OLLAMA_TIMEOUT')
            return schema(answer='',calls=[dict(tool='catalog_read',arguments_json='{}',explanation='TEST ONLY read')])
    app.state.assistant_provider_factory=Interrupted
    try:
        r=admin.post(B+'/conversations/'+t+'/messages',json=dict(idempotency_key=str(uuid4()),content='Проверь оборудование'))
        assert r.status_code==202
        turn=admin.get(B+'/conversations/'+t).json()['turns'][0]
        assert turn['status']=='failed' and turn['error_code']=='OLLAMA_TIMEOUT'
        assert turn['workflow']['outcome']=='partial' and turn['workflow']['goals'][0]['status']=='partial'
        assert 'Незавершённые пункты' in turn['answer']
        assert turn['trace'][0]['tool']=='catalog_read'
        with engine.connect() as c:
            state=c.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'),dict(id=turn['turn_id']))
        assert state['evidence'][0]['tool']=='catalog_read' and state['evidence'][0]['result']
    finally:del app.state.assistant_provider_factory
