"""Real PostgreSQL/API preferences; explicitly fixture-based external catalog responses."""
from uuid import uuid4
from contextlib import closing
import pytest
from sqlalchemy import text
from app.assistant import model_catalog,model_preferences,service
from app.schemas.assistant import ToolSelection
from tests.backend.test_assistant import assistant_case,thread,proposal,confirm,B
from tests.backend.test_management import managed,join
from tests.backend.test_runtime_integration import runtime

@pytest.fixture
def models_case(assistant_case,monkeypatch):
    engine,app,client,login,ids=assistant_case
    monkeypatch.setenv('ASSISTANT_PROVIDER','ollama')
    monkeypatch.setenv('OLLAMA_CHAT_MODEL','fixture-a:latest')
    monkeypatch.setenv('OLLAMA_CHAT_DIGEST','sha256:'+'a'*64)
    monkeypatch.setenv('AITUNNEL_API_KEY','catalog-secret-fixture')
    app.state.assistant_model_catalog=model_catalog.CatalogCache()
    calls=[]
    def catalogs(url,*,key='',body=None):
        calls.append((url,key,body))
        if url.endswith('/api/tags'):return dict(models=[dict(name='fixture-'+n+':latest',digest=n*64) for n in ('a','b')]+[dict(name='fixture-embed:latest',digest='e'*64),dict(name='remote:cloud',digest='c'*64,remote_host='https://ollama.com')])
        if url.endswith('/api/show'):return dict(capabilities=['embedding'] if body['model']=='fixture-embed:latest' else ['completion'])
        if url.endswith('/v1/models'):return dict(data=[dict(id=n,owned_by='fixture') for n in ('fixture-qwen','fixture-gpt','fixture-image')]+[dict(id='preset-test',owned_by='preset')])
        if url.endswith('/public/aitunnel/models'):return dict(chat={'fixture-qwen':{},'fixture-gpt':{}},images={'fixture-image':{}})
        raise AssertionError('Unexpected catalog URL')
    monkeypatch.setattr(model_catalog,'request_json',catalogs)
    yield dict(engine=engine,app=app,client=client,login=login,ids=ids,calls=calls,fixture=assistant_case)

def choose(case,provider='aitunnel',model='fixture-qwen',revision=0,client=None):
    return (client or case['client']).post(B+'/model-preference',json=dict(provider=provider,model=model,expected_revision=revision))

def test_actual_catalog_shape_filters_non_chat_and_remote_and_never_returns_key(models_case):
    c=models_case;r=c['client'].get(B+'/models');assert r.status_code==200,r.text
    groups={p['id']:p for p in r.json()['providers']}
    assert [m['id'] for m in groups['aitunnel']['models']]==['fixture-gpt','fixture-qwen','preset-test']
    assert {m['id'] for m in groups['ollama']['models']}=={'fixture-a:latest','fixture-b:latest','fixture-embed:latest'}
    assert 'catalog-secret-fixture' not in r.text and 'Authorization' not in r.text
    assert r.headers['cache-control']=='private, no-store'
    assert [p['status'] for p in groups.values()]==['ready','ready']

def test_model_selection_is_durable_and_capabilities_use_the_selection(models_case):
    c=models_case;before=c['client'].get(B+'/model-preference').json();assert before['revision']==0 and before['selection']['provider']=='ollama'
    saved=choose(c);assert saved.status_code==200,saved.text
    assert saved.json()==dict(selection=dict(provider='aitunnel',model='fixture-qwen'),revision=1,is_default=False,available=True)
    reread=c['client'].get(B+'/model-preference').json();assert reread==saved.json()
    caps=c['client'].get(B+'/capabilities').json();assert caps['model_ref']=='aitunnel:fixture-qwen' and caps['model_preference']==reread
    with c['engine'].connect() as db:
        row=db.execute(text('SELECT provider,model,digest,revision FROM assistant_model_preferences WHERE user_id=:id'),dict(id=c['ids']['user'])).one()
    assert tuple(row)==('aitunnel','fixture-qwen',None,1)

@pytest.mark.parametrize('role',['director','chief_engineer','engineer','dispatcher','admin','executor'])
def test_each_role_can_change_only_its_own_chat_preference(models_case,role):
    c=models_case;identity,email=join(c['fixture'],role)
    with closing(c['login'](email)) as actor:
        response=choose(c,client=actor);assert response.status_code==200,response.text
        assert actor.get(B+'/model-preference').json()['revision']==1
    assert c['client'].get(B+'/model-preference').json()['revision']==0
    with c['engine'].connect() as db:
        assert str(db.scalar(text('SELECT user_id FROM assistant_model_preferences WHERE site_id=:site'),dict(site=c['ids']['site'])))==str(identity)

def test_csrf_and_unauthenticated_catalog_are_rejected_before_discovery(models_case):
    from fastapi.testclient import TestClient
    c=models_case
    with closing(TestClient(c['app'])) as guest:
        assert guest.get(B+'/models').status_code==401
    c['client'].headers.pop('X-CSRF-Token')
    assert choose(c).status_code==403
    assert not c['calls']

@pytest.mark.parametrize('payload',[
    dict(provider='other',model='fixture-qwen',expected_revision=0),
    dict(provider='aitunnel',model='https://evil.test/model',expected_revision=0),
    dict(provider='aitunnel',model='fixture-qwen',expected_revision=0,user_id=str(uuid4())),
    dict(provider='aitunnel',model='fixture-qwen',expected_revision=-1),
    dict(provider='aitunnel',model='missing-model',expected_revision=0),
])
def test_invalid_preferences_do_not_write(models_case,payload):
    c=models_case;r=c['client'].post(B+'/model-preference',json=payload);assert r.status_code==422,r.text
    assert c['client'].get(B+'/model-preference').json()['revision']==0

def test_local_selection_pins_real_catalog_digest_and_rejects_embedding_model(models_case):
    c=models_case;r=choose(c,'ollama','fixture-b:latest');assert r.status_code==200,r.text
    assert r.json()['selection']['digest']=='sha256:'+'b'*64
    rejected=choose(c,'ollama','fixture-embed:latest',1);assert rejected.status_code==422
    assert c['client'].get(B+'/model-preference').json()==r.json()

def test_revision_conflict_does_not_replace_saved_model(models_case):
    c=models_case;assert choose(c).status_code==200
    conflict=choose(c,'ollama','fixture-b:latest',0);assert conflict.status_code==409
    assert c['client'].get(B+'/model-preference').json()['selection']['model']=='fixture-qwen'

def test_provider_failure_is_not_an_empty_catalog_or_fallback(models_case,monkeypatch):
    c=models_case;assert choose(c).status_code==200
    original=model_catalog.request_json
    def fail(url,**kwargs):
        if url.startswith('https:'):raise model_catalog.CatalogFailure('MODEL_CATALOG_UNAVAILABLE')
        return original(url,**kwargs)
    monkeypatch.setattr(model_catalog,'request_json',fail)
    result=c['client'].get(B+'/models?refresh=true').json()
    cloud=next(p for p in result['providers'] if p['id']=='aitunnel');local=next(p for p in result['providers'] if p['id']=='ollama')
    assert cloud['status']=='unavailable' and cloud['error_code']=='MODEL_CATALOG_UNAVAILABLE' and cloud['models']==[]
    assert local['status']=='ready' and local['models']
    assert choose(c,'aitunnel','fixture-gpt',1).status_code==503
    assert c['client'].get(B+'/model-preference').json()['selection']['model']=='fixture-qwen'

def test_catalog_cache_refresh_and_filter_do_not_requery_each_model(models_case):
    c=models_case
    first=c['client'].get(B+'/models').json();count=len(c['calls'])
    assert c['client'].get(B+'/models').json()==first and len(c['calls'])==count
    filtered=c['client'].get(B+'/models?q=qwen').json();assert len(c['calls'])==count
    assert [m['id'] for p in filtered['providers'] for m in p['models']]==['fixture-qwen']
    assert c['client'].get(B+'/models?refresh=true').status_code==200 and len(c['calls'])==count*2

def test_turn_freezes_model_and_revision_and_replay_cannot_change_it(models_case,monkeypatch):
    c=models_case;assert choose(c).status_code==200
    captured=[]
    class ExplicitModelStub:
        def chat(self,messages,schema,tokens):return ToolSelection(tools=[])
        def text(self,*args):return 'Тестовый ответ провайдера; проверяется транспорт выбора модели, не качество генерации.'
    def factory(selection=None):
        captured.append(selection)
        # A second real request changes the preference while the first turn is running.
        assert choose(c,'ollama','fixture-b:latest',1).status_code==200
        return ExplicitModelStub()
    monkeypatch.setattr(service,'provider',factory)
    chat=thread(c['client']);key=str(uuid4());body=dict(content='Кто ты?',idempotency_key=key,model_preference_revision=1)
    sent=c['client'].post(B+f'/conversations/{chat}/messages',json=body);assert sent.status_code==202,sent.text
    assert captured==[dict(provider='aitunnel',model='fixture-qwen',preference_revision=1)]
    turn=c['client'].get(B+'/conversations/'+chat).json()['turns'][0]
    assert turn['model_selection']==captured[0] and turn['status']=='completed'
    assert c['client'].post(B+f'/conversations/{chat}/messages',json=body).status_code==202
    assert len(captured)==1
    assert c['client'].post(B+f'/conversations/{chat}/messages',json={**body,'model_preference_revision':2}).status_code==409
    assert c['client'].post(B+f'/conversations/{chat}/messages',json={**body,'idempotency_key':str(uuid4())}).status_code==409

def test_assistant_can_propose_confirm_and_replay_its_own_preference_change(models_case):
    c=models_case;chat=thread(c['client'])
    action=proposal(c['client'],chat,'chat_model_select',dict(body=dict(provider='aitunnel',model='fixture-qwen',expected_revision=0)))
    assert c['client'].get(B+'/model-preference').json()['revision']==0
    result=confirm(c['client'],action);assert result.status_code==200 and result.json()['status']=='succeeded',result.text
    assert c['client'].get(B+'/model-preference').json()['revision']==1
    assert confirm(c['client'],action).json()['status']=='succeeded'
    assert c['client'].get(B+'/model-preference').json()['revision']==1

def test_preference_does_not_cross_role_or_site(models_case):
    c=models_case;assert choose(c).status_code==200
    with c['engine'].begin() as db:db.execute(text("UPDATE site_memberships SET role='dispatcher' WHERE site_id=:site AND user_id=:user"),dict(site=c['ids']['site'],user=c['ids']['user']))
    assert c['client'].get(B+'/model-preference').json()['revision']==0
    with c['engine'].begin() as db:db.execute(text("UPDATE site_memberships SET role='admin' WHERE site_id=:site AND user_id=:user"),dict(site=c['ids']['site'],user=c['ids']['user']))
    assert c['client'].get(B+'/model-preference').json()['selection']['model']=='fixture-qwen'

def test_provider_config_uses_selected_model_without_secret_in_snapshot(models_case):
    cloud=model_preferences.config(dict(provider='aitunnel',model='fixture-qwen'))
    assert cloud.model=='fixture-qwen' and cloud.api_key=='catalog-secret-fixture' and 'catalog-secret-fixture' not in repr(cloud)
    local=model_preferences.config(dict(provider='ollama',model='fixture-b:latest',digest='sha256:'+'b'*64))
    assert local.model=='fixture-b:latest' and local.digest=='sha256:'+'b'*64

def test_preference_is_scoped_to_the_selected_site(models_case):
    c=models_case;assert choose(c).status_code==200
    second=uuid4()
    with c['engine'].begin() as db:
        db.execute(text("INSERT INTO sites(site_id,name) VALUES (:id,'TEST ONLY second model scope')"),dict(id=second))
        db.execute(text("INSERT INTO site_memberships(user_id,site_id,role) VALUES (:user,:site,'admin')"),dict(user=c['ids']['user'],site=second))
    try:
        switched=c['client'].post('/api/v1/auth/site',json=dict(site_id=str(second)));assert switched.status_code==200,switched.text
        c['client'].headers['X-CSRF-Token']=switched.json()['csrfToken']
        assert c['client'].get(B+'/model-preference').json()['revision']==0
        assert choose(c,'ollama','fixture-b:latest').status_code==200
        restored=c['client'].post('/api/v1/auth/site',json=dict(site_id=str(c['ids']['site'])));assert restored.status_code==200
        c['client'].headers['X-CSRF-Token']=restored.json()['csrfToken']
        assert c['client'].get(B+'/model-preference').json()['selection']['model']=='fixture-qwen'
    finally:
        with c['engine'].begin() as db:
            for table in ('assistant_model_preferences','fixrate_sessions','site_memberships'):
                db.execute(text('DELETE FROM '+table+' WHERE site_id=:id'),dict(id=second))
            db.execute(text('DELETE FROM sites WHERE site_id=:id'),dict(id=second))

def test_running_turn_keeps_its_captured_deadline_after_model_change(models_case,monkeypatch):
    c=models_case;assert choose(c,'ollama','fixture-b:latest').status_code==200
    monkeypatch.setattr(service,'run_turn',lambda *args:service.SLOTS.release())
    chat=thread(c['client'])
    sent=c['client'].post(B+f'/conversations/{chat}/messages',json=dict(content='TEST ONLY delayed worker',idempotency_key=str(uuid4()),model_preference_revision=1));assert sent.status_code==202,sent.text
    with c['engine'].connect() as db:
        before=db.execute(text('SELECT model_selection,deadline_at-created_at AS budget FROM assistant_turns WHERE turn_id=:id'),dict(id=sent.json()['turn_id'])).mappings().one()
    assert before['budget'].total_seconds()>240
    assert choose(c,'aitunnel','fixture-qwen',1).status_code==200
    assert c['client'].get(B+'/conversations/'+chat).json()['turns'][0]['status']=='running'
    with c['engine'].begin() as db:db.execute(text("UPDATE assistant_turns SET deadline_at=now()-interval '1 minute' WHERE turn_id=:id"),dict(id=sent.json()['turn_id']))
    expired=c['client'].get(B+'/conversations/'+chat).json()['turns'][0]
    assert expired['status']=='failed' and expired['error_code']=='ASSISTANT_INTERRUPTED'

def test_database_rejects_unpinned_local_preference(models_case):
    from sqlalchemy.exc import IntegrityError
    c=models_case
    with pytest.raises(IntegrityError),c['engine'].begin() as db:
        db.execute(text("INSERT INTO assistant_model_preferences(user_id,site_id,role,provider,model,digest) VALUES (:user,:site,'admin','ollama','fixture-a:latest',NULL)"),dict(user=c['ids']['user'],site=c['ids']['site']))
    assert c['client'].get(B+'/model-preference').json()['revision']==0


def test_only_catalog_can_mark_cloud_presets_as_aliases(models_case):
    c=models_case
    selected=choose(c,'aitunnel','preset-test')
    assert selected.status_code==200,selected.text
    selection=selected.json()['selection']
    assert selection==dict(provider='aitunnel',model='preset-test',is_alias=True)
    assert model_preferences.config(selection).allow_model_alias
    assert not model_preferences.config(dict(provider='aitunnel',model='fixture-qwen')).allow_model_alias
    forged=c['client'].post(B+'/model-preference',json=dict(provider='aitunnel',model='fixture-qwen',expected_revision=1,is_alias=True))
    assert forged.status_code==422
