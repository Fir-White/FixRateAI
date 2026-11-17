"""Protected enrollment output across actual API/MCP/DB, without inference."""
import asyncio,json
from copy import deepcopy
from uuid import uuid4
import pytest
from sqlalchemy import text
from app.assistant import workflow as wf,service
from app.assistant.tools import TOOLS,invoke,validate_arguments,fingerprint,protected_result
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case,rpc,thread,proposal,confirm,B,Scripted

PATH='/api/v1/maintenance/management/enrollment'

def create_secret(case):
    _,_,client,_,_=case
    response=client.post(PATH);assert response.status_code==200
    code=response.json()['code'];assert isinstance(code,str) and len(code)>=16
    return code

def absent(secret,value):
    leaked=secret in json.dumps(value,default=str,ensure_ascii=False)
    assert not leaked,'Protected credential entered a tool/model/persistence boundary'

def test_authorized_api_retains_current_code_but_mcp_returns_only_protected_link(assistant_case):
    secret=create_secret(assistant_case);_,_,client,_,_=assistant_case
    direct=client.get(PATH);matches=direct.json()['code']==secret;assert matches
    result=rpc(client,'tools/call',dict(name='enrollment_read',arguments={})).json()['result']
    assert not result['isError'];absent(secret,result)
    safe=json.loads(result['content'][0]['text'])
    assert safe['code_present'] is True and safe['resource']['url']==PATH and safe['resource']['protected'] is True
    assert client.chief.get(PATH).status_code==403

@pytest.mark.parametrize('path',[['code'],['code','anything']])
def test_projection_cannot_extract_code_or_text_parts(assistant_case,path):
    secret=create_secret(assistant_case);client=assistant_case[2]
    result=rpc(client,'tools/call',dict(name='enrollment_read',arguments=dict(view=dict(path=path)))).json()['result']
    assert result['isError'];absent(secret,result)

def test_confirm_create_never_persists_code_in_action_or_conversation(assistant_case):
    engine,_,client,_,_=assistant_case;secret=create_secret(assistant_case);chat=thread(client)
    record=proposal(client,chat,'enrollment_create',{})
    confirmed=confirm(client,record);assert confirmed.status_code==200;absent(secret,confirmed.json())
    replay=confirm(client,record);assert replay.status_code==200;absent(secret,replay.json())
    absent(secret,client.get(B+'/conversations/'+chat).json())
    with engine.connect() as db:
        result=db.scalar(text('SELECT result FROM assistant_actions WHERE action_id=:id'),dict(id=record['action_id']))
    absent(secret,result);assert result['data']['resource']['url']==PATH

def test_legacy_action_serializer_and_resume_scrub_secret_and_old_hash_without_mutating_input():
    secret='TEST-SYNTHETIC-ENROLLMENT-ONLY';old_hash=fingerprint(dict(code=secret))
    row=dict(tool_name='enrollment_create',arguments={},status='succeeded',started_at=None,
             result=dict(data=dict(code=secret)),before_snapshot=dict(preview=dict(code=secret),sha256=old_hash))
    safe=service.public_action(row);absent(secret,safe)
    assert old_hash not in json.dumps(safe) and row['result']['data']['code']==secret
    goal=dict(id='open',tool='enrollment_read',kind='read',status='partial',reason=None,action_id=None)
    state=dict(goals=[goal],evidence=[dict(tool='enrollment_read',result=dict(code=secret),sha256=old_hash)],decomposition_verified=True)
    resumed=wf.resume(state);absent(secret,resumed)
    assert old_hash not in json.dumps(resumed) and state['evidence'][0]['result']['code']==secret
    projected=deepcopy(state);projected['evidence'][0]['result']=dict(text_parts=[secret],source_path=['code'])
    absent(secret,wf.sanitize_workflow(projected))

def test_no_secret_in_second_specialist_model_context_or_persisted_evidence(assistant_case):
    engine,app,client,_,_=assistant_case;secret=create_secret(assistant_case);chat=thread(client)
    goals=[dict(id='secure',title='TEST view enrollment securely',tool='enrollment_read',kind='read'),
           dict(id='catalog',title='TEST inspect authorized catalog',tool='catalog_read',kind='read')]
    provider=Scripted([dict(answer='',calls=[dict(tool='enrollment_read',arguments={},explanation='TEST')]),
                       dict(answer='',calls=[dict(tool='catalog_read',arguments={},explanation='TEST')])],goals=goals)
    app.state.assistant_provider_factory=lambda:provider
    try:
        sent=client.post(B+f'/conversations/{chat}/messages',json=dict(content='TEST ONLY secure enrollment view and authorized catalog',idempotency_key=str(uuid4())))
        assert sent.status_code==202
        absent(secret,provider.messages)
        with engine.connect() as db:
            state=db.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'),dict(id=sent.json()['turn_id']))
        absent(secret,state);assert len(state['evidence'])>=2
    finally:del app.state.assistant_provider_factory

def test_business_codes_are_not_globally_redacted():
    value=dict(code='TO-2',items=[dict(code='PUMP-01')])
    assert protected_result('operation_read',value)==value and wf.safe_evidence(value)==value


def test_own_legacy_explanation_and_goal_response_mask_exact_known_code_only():
    secret='SYNTHETIC-ENROLLMENT-CODE-ONLY'
    row=dict(tool_name='enrollment_create',arguments={},status='succeeded',started_at=None,before_snapshot=None,
             result=dict(data=dict(code=secret)),explanation='Код '+secret+'; операция TO-2')
    safe=service.public_action(row);absent(secret,safe)
    assert 'TO-2' in safe['explanation'] and secret in row['explanation']
    state=dict(goals=[dict(id='source',tool='enrollment_read',status='partial',reason=None,response='Код '+secret+'; TO-2')],
               evidence=[dict(tool='enrollment_read',result=dict(code=secret),sha256=fingerprint(dict(code=secret)))])
    safe=wf.sanitize_workflow(state);absent(secret,safe)
    assert 'TO-2' in safe['goals'][0]['response'] and secret in state['goals'][0]['response']


def test_owned_legacy_answer_is_masked_in_public_history_and_next_model_context(assistant_case):
    engine,app,client,_,ids=assistant_case;secret=create_secret(assistant_case);chat=thread(client);legacy=uuid4()
    with engine.begin() as db:
        db.execute(text("INSERT INTO assistant_turns(turn_id,conversation_id,request_key,content,status,prompt_version,answer) VALUES (:turn,:chat,:key,'TEST legacy','completed','TEST',:answer)"),
                   dict(turn=legacy,chat=chat,key=uuid4(),answer='Код компании '+secret+'; операция TO-2'))
        db.execute(text("INSERT INTO assistant_actions(action_id,conversation_id,turn_id,tool_name,arguments,payload_sha256,explanation,status,expires_at,result) VALUES (:action,:chat,:turn,'enrollment_create','{}',:sha,:explanation,'succeeded',now()+interval '15 minutes',CAST(:result AS jsonb))"),
                   dict(action=uuid4(),chat=chat,turn=legacy,sha='0'*64,explanation='Создан код '+secret,result=json.dumps(dict(data=dict(code=secret)))))
    before=client.get(B+'/conversations/'+chat);assert before.status_code==200;absent(secret,before.json())
    assert 'TO-2' in before.json()['turns'][0]['answer']
    class HistoricalReply:
        def __init__(self):self.messages=[]
        def chat(self,messages,schema,tokens):
            self.messages.append(deepcopy(messages))
            return schema(tools=[],goals=[dict(id='reply',title='TEST continue owned conversation',tool='',kind='conversation',required_evidence='conversation')])
        def text(self,messages,tokens):
            self.messages.append(deepcopy(messages))
            return 'TEST ONLY safe continuation'
    provider=HistoricalReply()
    app.state.assistant_provider_factory=lambda:provider
    try:
        sent=client.post(B+f'/conversations/{chat}/messages',json=dict(content='Продолжи: TEST inspect the authorized catalog',idempotency_key=str(uuid4())))
        assert sent.status_code==202;absent(secret,provider.messages)
        assert len(provider.messages)==2
        second=json.dumps(provider.messages[1],ensure_ascii=False)
        assert 'TO-2' in second and '[защищённый код]' in second
        absent(secret,provider.messages[1])
        absent(secret,client.get(B+'/conversations/'+chat).json())
        with engine.connect() as db:stored=db.scalar(text('SELECT answer FROM assistant_turns WHERE turn_id=:turn'),dict(turn=legacy))
        unchanged=secret in stored;assert unchanged,'Read sanitization must not rewrite historical database rows'
    finally:del app.state.assistant_provider_factory


def test_known_values_query_is_bounded_and_scoped_to_owned_conversation(assistant_case):
    from types import SimpleNamespace
    from app.assistant.tools import conversation_enrollment_values
    engine,_,client,_,ids=assistant_case;secret=create_secret(assistant_case);chat=thread(client)
    principal=SimpleNamespace(user_id=ids['user'],site_id=ids['site'],role='admin')
    with engine.begin() as db:
        db.execute(text("INSERT INTO assistant_actions(action_id,conversation_id,tool_name,arguments,payload_sha256,explanation,status,expires_at,result) VALUES (:action,:chat,'enrollment_create','{}',:sha,'TEST','succeeded',now()+interval '15 minutes',CAST(:result AS jsonb))"),
                   dict(action=uuid4(),chat=chat,sha='0'*64,result=json.dumps(dict(data=dict(code=secret)))))
        db.execute(text("UPDATE assistant_actions SET created_at=now()-interval '1 hour' WHERE conversation_id=:chat"),dict(chat=chat))
        db.execute(text("INSERT INTO assistant_actions(action_id,conversation_id,tool_name,arguments,payload_sha256,explanation,status,expires_at) SELECT gen_random_uuid(),:chat,'enrollment_create','{}',:sha,'TEST incomplete proposal','proposed',now()+interval '15 minutes' FROM generate_series(1,70)"),dict(chat=chat,sha='0'*64))
    from sqlalchemy import event
    statements=[]
    def before(conn,cursor,statement,parameters,context,many):
        if 'assistant_enrollment_private_values' in statement:statements.append(statement)
    event.listen(engine,'before_cursor_execute',before)
    try:
        with engine.connect() as db:
            known=conversation_enrollment_values(db,principal,chat)
            foreign=conversation_enrollment_values(db,SimpleNamespace(user_id=uuid4(),site_id=ids['site'],role='admin'),chat)
        included=secret in known;assert included and not foreign
    finally:event.remove(engine,'before_cursor_execute',before)
    assert len(statements)==2 and all('LIMIT 64' in sql and 'c.user_id' in sql and 'c.site_id' in sql and 'c.role' in sql for sql in statements)
