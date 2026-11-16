"""Real HTTP/PG attachment selection, private ownership, multimodal input and retries."""
import base64,copy,io,json,re
from pathlib import Path
from uuid import uuid4
import pytest
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tests.backend.test_assistant import assistant_case,managed,runtime,thread,B
from tests.backend.test_assistant_capabilities import upload


class InspectingModel:
    response_model='TEST-ONLY-file-agent'
    def __init__(self,on_route=None):self.calls=[];self.on_route=on_route
    def chat(self,messages,schema,tokens):
        self.calls.append((schema.__name__,copy.deepcopy(messages)))
        if schema.__name__=='ToolSelection':
            if self.on_route:self.on_route()
            return schema.model_validate(dict(tools=[]))
        return schema.model_validate(dict(answer='TEST ONLY: selected attachment inspected',calls=[]))


def png(color='red'):
    blob=io.BytesIO();Image.new('RGBA',(1800,100),color).save(blob,format='PNG');return blob.getvalue()


def image(client,chat,name='TEST.png',color='red'):
    return upload(client,chat,png(color),name,'image/png')


def send(client,chat,files,content='',key=None):
    return client.post(B+f'/conversations/{chat}/messages',json=dict(content=content,attachment_ids=files,idempotency_key=str(key or uuid4())))


def test_file_only_turn_delivers_pixels_records_selection_and_retries_once(assistant_case):
    engine,app,admin,_,_=assistant_case;chat=thread(admin);file=image(admin,chat)
    provider=InspectingModel();app.state.assistant_provider_factory=lambda:provider
    key=uuid4();response=send(admin,chat,[file['attachment_id']],key=key)
    assert response.status_code==202,response.text
    loaded=admin.get(B+'/conversations/'+chat).json()
    assert loaded['pending_attachments']==[]
    assert loaded['turns'][0]['status']=='completed'
    assert loaded['turns'][0]['attachments']==[file]
    route=next(messages for schema,messages in provider.calls if schema=='ToolSelection')
    assert all(not m.get('images') for m in route)
    messages=next(messages for schema,messages in provider.calls if schema=='AgentStep')
    pixels=next(m['images'] for m in messages if m.get('images'))
    assert len(pixels)==1
    with Image.open(io.BytesIO(base64.b64decode(pixels[0]))) as decoded:
        assert decoded.format=='JPEG' and decoded.mode=='RGB'
        assert max(decoded.size)<=1280 and not decoded.getexif()
    count=len(provider.calls)
    duplicate=send(admin,chat,[file['attachment_id']],key=key)
    assert duplicate.status_code==202 and duplicate.json()['turn_id']==response.json()['turn_id']
    assert len(provider.calls)==count
    assert send(admin,chat,[],content='changed',key=key).status_code==409
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM assistant_turns WHERE conversation_id=:id'),dict(id=chat))==1


def test_only_selected_files_are_shared_and_old_images_are_not_resent(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin)
    selected=image(admin,chat,'selected.png','red');pending=image(admin,chat,'pending.png','blue')
    provider=InspectingModel();app.state.assistant_provider_factory=lambda:provider
    assert send(admin,chat,[selected['attachment_id']]).status_code==202
    route=provider.calls[0][1]
    context=json.loads(route[0]['content'].rsplit('Контекст сервера:\n',1)[1])
    assert [f['attachment_id'] for f in context['message_attachments']]==[selected['attachment_id']]
    assert pending['attachment_id'] not in json.dumps(context)
    loaded=admin.get(B+'/conversations/'+chat).json()
    assert loaded['pending_attachments']==[pending]
    provider.calls.clear()
    assert send(admin,chat,[],content='TEST ONLY new text question').status_code==202
    assert all(not m.get('images') for _,messages in provider.calls for m in messages)
    loaded=admin.get(B+'/conversations/'+chat).json()
    assert loaded['turns'][-1]['attachments']==[] and loaded['pending_attachments']==[pending]


def test_message_files_cannot_cross_conversation_or_owner_and_blank_is_rejected(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin);other=thread(admin);file=image(admin,chat)
    chief_chat=thread(admin.chief);provider=InspectingModel();app.state.assistant_provider_factory=lambda:provider
    assert send(admin,other,[file['attachment_id']]).status_code==404
    assert send(admin.chief,chief_chat,[file['attachment_id']]).status_code==404
    assert send(admin,chat,[]).status_code==422
    assert send(admin,chat,[file['attachment_id'],file['attachment_id']]).status_code==422
    assert provider.calls==[]


def test_legacy_text_client_still_includes_staged_file_and_can_retry(assistant_case):
    _,app,admin,_,_=assistant_case;chat=thread(admin);file=image(admin,chat)
    provider=InspectingModel();app.state.assistant_provider_factory=lambda:provider
    body=dict(content='TEST ONLY legacy request',idempotency_key=str(uuid4()))
    first=admin.post(B+f'/conversations/{chat}/messages',json=body)
    assert first.status_code==202,first.text
    again=admin.post(B+f'/conversations/{chat}/messages',json=body)
    assert again.status_code==202 and again.json()['turn_id']==first.json()['turn_id']
    assert admin.get(B+'/conversations/'+chat).json()['turns'][0]['attachments']==[file]


def test_role_change_during_routing_prevents_image_dispatch(assistant_case):
    engine,app,admin,_,ids=assistant_case;chat=thread(admin);file=image(admin,chat)
    def change_role():
        with engine.begin() as c:c.execute(text("UPDATE site_memberships SET role='engineer' WHERE site_id=:site AND user_id=:user"),dict(site=ids['site'],user=ids['user']))
    provider=InspectingModel(change_role);app.state.assistant_provider_factory=lambda:provider
    try:
        assert send(admin,chat,[file['attachment_id']]).status_code==202
        assert [schema for schema,_ in provider.calls]==['ToolSelection']
        assert all(not m.get('images') for _,messages in provider.calls for m in messages)
        with engine.connect() as c:assert c.scalar(text('SELECT status FROM assistant_turns WHERE conversation_id=:id'),dict(id=chat))=='failed'
    finally:
        with engine.begin() as c:c.execute(text("UPDATE site_memberships SET role='admin' WHERE site_id=:site AND user_id=:user"),dict(site=ids['site'],user=ids['user']))


def test_image_limit_is_checked_before_creating_a_turn(assistant_case):
    engine,app,admin,_,_=assistant_case;chat=thread(admin)
    files=[image(admin,chat,f'TEST-{i}.png')['attachment_id'] for i in range(5)]
    provider=InspectingModel();app.state.assistant_provider_factory=lambda:provider
    assert send(admin,chat,files).status_code==422 and provider.calls==[]
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM assistant_turns WHERE conversation_id=:id'),dict(id=chat))==0


def test_upgrade_from_020_preserves_history_and_does_not_resend_historical_files(runtime):
    from app.db.session import make_engine
    from app.manage import migrate,migration_checksum,seed_demo
    runtime_engine,_=runtime
    assert runtime_engine.url.database.startswith('fixrate_test_')
    name='fixrate_test_message_upgrade_'+uuid4().hex
    with runtime_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as c:c.exec_driver_sql('CREATE DATABASE '+name)
    engine=make_engine(runtime_engine.url.set(database=name));root=Path(__file__).resolve().parents[2]
    try:
        old=[p for p in sorted((root/'database/migrations').glob('*.sql')) if int(p.name[:3])<=20]
        with engine.begin() as c:
            for path in old:c.connection.driver_connection.execute(re.sub(r'(?m)^\s*(?:BEGIN|COMMIT);\s*$','',path.read_text(encoding='utf-8-sig')))
            c.exec_driver_sql('CREATE TABLE fixrate_schema_migrations (filename text PRIMARY KEY,sha256 char(64) NOT NULL,applied_at timestamptz NOT NULL DEFAULT now())')
            for path in old:c.execute(text('INSERT INTO fixrate_schema_migrations(filename,sha256) VALUES (:name,:hash)'),dict(name=path.name,hash=migration_checksum(path)))
        seed_demo(engine,'TEST ONLY isolated upgrade password')
        first,other,turn,old_file,pending,foreign=[uuid4() for _ in range(6)]
        with engine.begin() as c:
            site,user=c.execute(text("SELECT site_id,user_id FROM site_memberships WHERE role='admin' LIMIT 1")).one()
            for identity in (first,other):
                c.execute(text("INSERT INTO assistant_conversations(conversation_id,site_id,user_id,role,title,agent) VALUES (:id,:site,:user,'admin','TEST ONLY old history','assistant')"),dict(id=identity,site=site,user=user))
            c.execute(text("INSERT INTO assistant_turns(turn_id,conversation_id,request_key,content,status,prompt_version,created_at) VALUES (:id,:chat,:key,'TEST ONLY original message','completed','legacy','2026-10-01T12:00:00Z')"),dict(id=turn,chat=first,key=uuid4()))
            for identity,chat,clock in ((old_file,first,'11:00'),(pending,first,'13:00'),(foreign,other,'11:00')):
                c.execute(text('''INSERT INTO assistant_attachments(attachment_id,conversation_id,original_name,mime_type,size_bytes,sha256,storage_key,created_at)
                    VALUES (:id,:chat,:name,'application/octet-stream',1,:sha,:key,CAST(:at AS timestamptz))'''),dict(id=identity,chat=chat,name=str(identity)+'.xlsx',sha='a'*64,key='TEST/'+str(identity),at='2026-10-01T'+clock+':00Z'))
        with engine.connect() as c:
            original_columns={table:list(c.scalars(text('SELECT column_name FROM information_schema.columns WHERE table_schema=\'public\' AND table_name=:table ORDER BY ordinal_position'),dict(table=table))) for table in ('assistant_conversations','assistant_turns','assistant_attachments')}
        def snapshot():
            with engine.connect() as c:
                # Freeze every original column before migration. Additive nullable
                # columns must not change the hash of the preserved old history.
                return {table:c.scalar(text(f"SELECT md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text,'[]')) FROM (SELECT "+','.join('"'+name.replace('"','""')+'"' for name in columns)+f" FROM {table}) t")) for table,columns in original_columns.items()}
        before=snapshot();migrate(engine);migrate(engine);assert snapshot()==before
        with engine.connect() as c:
            assert c.execute(text('SELECT model_selection,deadline_at FROM assistant_turns WHERE turn_id=:id'),dict(id=turn)).one()==(None,None)
            rows=c.execute(text('SELECT turn_id,attachment_id,conversation_id,inferred_legacy FROM assistant_turn_attachments')).all()
            assert rows==[(turn,old_file,first,True)]
        with pytest.raises(IntegrityError),engine.begin() as c:
            c.execute(text('INSERT INTO assistant_turn_attachments(turn_id,attachment_id,conversation_id,position) VALUES (:turn,:file,:chat,1)'),dict(turn=turn,file=foreign,chat=first))
    finally:
        engine.dispose()
        with runtime_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as c:c.exec_driver_sql('DROP DATABASE '+name)
