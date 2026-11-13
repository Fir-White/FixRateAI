"""Real PostgreSQL: revisions, explicit confirmation, source and plan isolation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from uuid import uuid4
import pytest
from sqlalchemy import text, event
from tests.backend.test_catalog_imports import upload, BASE
from tests.backend.test_management import managed, equipment
from tests.backend.test_runtime_integration import runtime, login
from tests.fixtures.catalog_source import catalog_book


def catalog(admin,count=5):
    content=catalog_book(count)
    token=upload(admin,content).json()['preview_token']
    identity=upload(admin,content,'',token).json()['import_id']
    rows=admin.get(BASE+f'/{identity}/operations').json()['items']
    return identity,[r['row'] for r in rows],content


def decision(ids,**updates):
    return dict(interpretation='ALLOWED_WINDOW',calendar_year=2027,mark_slots='one_per_mark',
        semantics_note='TEST ONLY: marks delimit one allowed window, not ten jobs',
        frequency_kind='month',frequency_interval=1,equipment_ids=ids,
        norm_value='3.000',norm_unit='person_hour',norm_scope='per_asset',crew_size=1,
        norm_ref='TEST ONLY: synthetic approved methodology',splittable=False,
        policy_note='TEST ONLY: execute as one uninterrupted job')|updates


def write(client,identity,row,payload,revision=0,confirm=False):
    return client.post(BASE+f'/{identity}/operations/{row}/decision',json=dict(
        expected_revision=revision,confirm=confirm,reason='TEST ONLY: reviewed source interpretation',decision=payload))


def test_partial_draft_confirmation_revision_history_and_no_active_writes(managed):
    engine,_,admin,_,ids=managed
    identity,rows,content=catalog(admin)
    eq=equipment(admin,ids)
    tables=('equipment','maintenance_rules','rule_equipment','schedule_entries','work_orders','work_assignments')
    def snapshot():
        with engine.connect() as c:
            return {t:c.scalar(text(f"SELECT md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text,'[]')) FROM {t} t WHERE site_id=:site"),ids) for t in tables}
    before=snapshot()
    url=BASE+f'/{identity}/operations/{rows[0]}/decision'
    empty=admin.get(url).json()
    assert empty['revision']==0 and not empty['prepared'] and len(empty['blockers'])==5
    partial=write(admin,identity,rows[0],{'semantics_note':'Partial decision'})
    assert partial.status_code==200,partial.text
    assert partial.json()['revision']==1 and not partial.json()['confirmed']
    assert write(admin.chief,identity,rows[0],{},revision=1,confirm=True).status_code==422
    complete=decision([eq['equipment_id']])
    assert write(admin,identity,rows[0],complete,1,True).status_code==403
    saved=write(admin.chief,identity,rows[0],complete,1,True)
    assert saved.status_code==200,saved.text
    data=saved.json()
    assert data['revision']==2 and data['prepared'] and data['blockers']==[]
    assert data['author_name']=='Test chief'
    assert data['total_person_hours']=='3.000' and data['elapsed_hours']=='3.000'
    assert not data['ready_for_real_plan']
    assert write(admin.chief,identity,rows[0],complete,1,True).status_code==409
    history=admin.get(url+'/history').json()
    assert history['total']==2 and [r['revision'] for r in history['items']]==[2,1]
    assert history['items'][0]['created_by']!=history['items'][1]['created_by']
    progress=admin.get(BASE+f'/{identity}/preparation').json()
    assert progress['prepared_count']==1 and progress['total']==5
    assert snapshot()==before
    assert admin.get(BASE+f'/{identity}/source').content==content
    assert admin.get(BASE+f'/{identity}/operations/{rows[0]}').json()['norm_value'] is None
    # Editing appends an unconfirmed head and preserves the earlier confirmation.
    result=write(admin,identity,rows[0],complete,2)
    assert result.status_code==200 and not result.json()['prepared']
    assert admin.get(url+'/history').json()['items'][1]['confirmed']


@pytest.mark.parametrize(('unit','scope','hours','elapsed'),[
    ('person_hour','per_asset','6.000','3.000'),('person_hour','whole_binding','3.000','1.500'),
    ('elapsed_hour','per_asset','12.000','6.000'),('elapsed_hour','whole_binding','6.000','3.000')])
def test_norm_units_and_real_inventory_quantity(managed,unit,scope,hours,elapsed):
    engine,_,admin,_,ids=managed
    first=equipment(admin,ids)
    with engine.begin() as c:
        second=c.scalar(text("INSERT INTO equipment(site_id,system_id,equipment_type_id,asset_code,name) VALUES (:site,:system,:type,:code,'Second synthetic asset') RETURNING equipment_id"),dict(ids,code='SECOND-'+ids['marker']))
    identity,rows,_=catalog(admin)
    payload=decision([first['equipment_id'],str(second)],norm_unit=unit,norm_scope=scope,crew_size=2)
    result=write(admin.chief,identity,rows[0],payload,confirm=True)
    assert result.status_code==200,result.text
    assert result.json()['total_person_hours']==hours
    assert result.json()['elapsed_hours']==elapsed


def test_included_steps_are_not_counted_twice_and_parent_edits_invalidate(managed):
    _,_,admin,_,ids=managed
    eq=equipment(admin,ids);identity,rows,_=catalog(admin)
    base=decision([eq['equipment_id']])
    assert write(admin.chief,identity,rows[0],base,confirm=True).status_code==200
    child=decision([eq['equipment_id']],frequency_kind='included_in',included_in_row=rows[0],norm_value=None)
    result=write(admin.chief,identity,rows[1],child,confirm=True)
    assert result.status_code==200,result.text
    assert result.json()['prepared'] and result.json()['total_person_hours']=='0'
    assert write(admin.chief,identity,rows[2],dict(child,calendar_year=2028),confirm=True).status_code==422
    assert write(admin.chief,identity,rows[2],dict(child,splittable=True,min_segment_minutes=10),confirm=True).status_code==422
    assert write(admin.chief,identity,rows[2],dict(child,included_in_row=rows[1]),confirm=True).status_code==422
    assert write(admin.chief,identity,rows[2],dict(child,included_in_row=rows[2]),confirm=True).status_code==422
    assert write(admin,identity,rows[0],base,1).status_code==200
    result=admin.get(BASE+f'/{identity}/operations/{rows[1]}/decision').json()
    assert not result['prepared'] and 'STALE_PARENT' in result['blockers']
    assert admin.get(BASE+f'/{identity}/preparation').json()['prepared_count']==0


def test_changed_asset_invalidates_confirmation_but_does_not_rewrite_history(managed):
    engine,_,admin,_,ids=managed;eq=equipment(admin,ids)
    identity,rows,_=catalog(admin)
    payload=decision([eq['equipment_id']])
    assert write(admin.chief,identity,rows[0],payload,confirm=True).status_code==200
    with engine.begin() as c:c.execute(text("UPDATE equipment SET revision=revision+1,status='retired' WHERE equipment_id=:id"),dict(id=eq['equipment_id']))
    data=admin.get(BASE+f'/{identity}/operations/{rows[0]}/decision').json()
    assert data['confirmed'] and not data['prepared'] and 'STALE_ASSET_BINDING' in data['blockers']
    assert write(admin.chief,identity,rows[0],payload,1,True).status_code==422
    history=admin.get(BASE+f'/{identity}/operations/{rows[0]}/decision/history').json()
    assert history['total']==1 and history['items'][0]['equipment'][0]['status']=='active'


def test_concurrent_writers_have_one_winner(managed):
    _,_,admin,_,_=managed;identity,rows,_=catalog(admin)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:write(admin,identity,rows[0],{}),range(2)))
    assert sorted(r.status_code for r in responses)==[200,409]
    assert admin.get(BASE+f'/{identity}/operations/{rows[0]}/decision/history').json()['total']==1


def test_input_isolation_roles_site_unknown_assets_and_validation(managed):
    _,app,admin,_,_=managed;identity,rows,_=catalog(admin)
    for update in ({'equipment_ids':[str(uuid4())]}, {'crew_size':0}, {'norm_value':'NaN'},
                   {'equipment_ids':[str(uuid4())]*2}, {'frequency_kind':'included_in','norm_value':'2'},
                   {'splittable':False,'min_segment_minutes':30},{'invented_field':True}):
        assert write(admin,identity,rows[0],update).status_code==422
    assert write(admin,identity,9999,{}).status_code==404
    with closing(login(app,'chief_engineer')) as other:
        for tail in ('/preparation','/binding-options',f'/operations/{rows[0]}/decision',f'/operations/{rows[0]}/decision/history'):
            assert other.get(BASE+f'/{identity}'+tail).status_code==404
        assert write(other,identity,rows[0],{}).status_code==404
    with closing(login(app,'director')) as director:
        assert write(director,identity,rows[0],{}).status_code==403
    with closing(login(app,'executor')) as executor:
        assert executor.get(BASE+f'/{identity}/preparation').status_code==403


def test_readiness_requires_explicit_choices_and_preserves_one_worker_for_new_code(managed):
    _,_,admin,_,ids=managed;eq=equipment(admin,ids);identity,rows,_=catalog(admin)
    complete=decision([eq['equipment_id']],splittable=True,min_segment_minutes=30)
    for name,value in [('interpretation','UNKNOWN'),('calendar_year',None),('mark_slots','unconfirmed'),
                       ('semantics_note',' '),('frequency_kind','unconfirmed'),('frequency_interval',None),
                       ('equipment_ids',[]),('norm_value',None),('norm_unit','unconfirmed'),('norm_scope','unconfirmed'),
                       ('crew_size',None),('norm_ref',' '),('splittable',None),('policy_note',' '),('min_segment_minutes',200)]:
        response=write(admin.chief,identity,rows[0],dict(complete,**{name:value}),confirm=True)
        assert response.status_code==422,(name,response.text)
    # This source has no legacy heating-operation crew constraint; source code alone never grants it.
    assert admin.get(BASE+f'/{identity}/operations/{rows[3]}').json()['code']=='1.4'
    result=write(admin.chief,identity,rows[3],complete,confirm=True)
    assert result.status_code==200 and result.json()['decision']['crew_size']==1


def test_preparation_queries_and_binding_picker_are_bounded(managed):
    import json
    engine,_,admin,_,ids=managed;eq=equipment(admin,ids);identity,_,_=catalog(admin,500)
    from app.schemas.catalog_decisions import DecisionInput
    payload=DecisionInput.model_validate(decision([eq['equipment_id']])).model_dump(mode='json')
    with engine.begin() as c:
        c.execute(text('''INSERT INTO catalog_operation_decisions
            (decision_id,site_id,import_id,row_number,revision,created_by,reason,payload,binding_snapshot)
            SELECT gen_random_uuid(),site_id,import_id,(o->>'row')::int,1,:actor,'TEST ONLY bulk drafts',CAST(:payload AS jsonb),'[]'
            FROM regulation_catalog_imports c,LATERAL jsonb_array_elements(c.catalog_data->'operations') o WHERE import_id=:id'''),
            dict(actor=ids['user'],payload=json.dumps(payload),id=identity))
    statements=[]
    def count(conn,cursor,statement,params,context,many):
        if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(engine,'before_cursor_execute',count)
    try:
        response=admin.get(BASE+f'/{identity}/preparation')
        assert response.status_code==200 and len(response.json()['items'])==500
        assert len(statements)<=10
        found=admin.get(BASE+f'/{identity}/binding-options?q=WEB-').json()
        assert found['total']==1 and len(found['items'])==1
        assert admin.get(BASE+f'/{identity}/binding-options?q=%25').json()['total']==0
    finally:event.remove(engine,'before_cursor_execute',count)
