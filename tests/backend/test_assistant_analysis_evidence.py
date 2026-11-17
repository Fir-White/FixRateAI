"""Analytical reconciliation unit faults and real authorized PostgreSQL reads."""
import asyncio
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.assistant import analysis_evidence as ae
from app.assistant.tools import available
from app.security.sessions import Principal
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed, join
from tests.backend.test_assistant_task_analytics import add_orders, clock, TODAY

NOW=datetime(2026,11,15,8,tzinfo=timezone.utc)
TOOL=SimpleNamespace(name='tasks_analyze',mode='read',method='GET')
ACTOR=SimpleNamespace(user_id=uuid4(),site_id=uuid4(),role='admin',site_name='Unit analytical site',timezone='Asia/Yekaterinburg')


def snapshot(count=1):
    """Explicit unit data; successful business integrations below use real SQL."""
    common=dict(checked_at=NOW.isoformat(),local_date='2026-11-15',timezone=ACTOR.timezone,snapshot_id='a'*64,
        complete=True,scanned_tasks=count,selected_tasks=count,
        scope=dict(site_id=str(ACTOR.site_id),site_name=ACTOR.site_name,role=ACTOR.role,visibility='whole_site',
                   origin='all',cohort='unfinished',starts_on=None,ends_on=None),
        counters=dict(all_tasks=count,execution_pending=count,unfinished=count,scheduled_unfinished=0,completed=0,cancelled=0,
                      by_status={'draft':count},by_origin={'manual':count}),
        due={'future':count},execution_pending_due={'future':count},scheduled={'unscheduled':count},
        norm_checks={'consistent':count},known_person_hours=str(2*count),unknown_effort_tasks=0,
        business_duplicates=dict(candidate_groups=0,candidate_tasks=0,unchecked_tasks=0))
    summary=dict(common,sample=[],sample_total=count,sample_truncated=count>0)
    equipment=[]
    for index in range(count):
        operation=dict(rule_id=str(uuid4()),title='Actual fixture operation',code='UNIT',tasks=1,execution_pending=1,in_review=0,
            period_unit='day',period_count=1,occurrences_per_period=1,calendar_pattern=None,
            first_source_date='2026-11-16',last_source_date='2026-11-16',plan_periods=[],norm_checks={'consistent':1})
        equipment.append(dict(id=str(uuid4()),asset_code=f'UNIT-{index}',name='Fixture equipment',tasks=1,execution_pending=1,
            in_review=0,known_person_hours='2',unknown_effort_tasks=0,operations=[operation],operations_total=1,operations_truncated=False))
    dates=[dict(date='2026-11-16',tasks=count,known_person_hours=str(2*count),unknown_effort_tasks=0,
                planned_tasks=0,deadline_only_tasks=count)] if count else []
    return common,summary,dict(equipment=equipment,dates=dates,duplicates=[])


@pytest.fixture
def source(monkeypatch):
    common,summary,sections=snapshot()
    calls=[]
    def validate(app,tool,args):
        return deepcopy(args)
    async def read(app,tool,args,headers,trace):
        query=args['query'];section=query['section'];offset=query['offset'];calls.append((section,offset))
        trace.append(dict(tool=tool.name,status='completed',attempt=1))
        if section=='summary':value=deepcopy(summary)
        else:value=dict(deepcopy(common),items=deepcopy(sections[section][offset:offset+25]),
                        total=len(sections[section]),offset=offset,limit=25)
        return deepcopy(args),value
    monkeypatch.setattr(ae,'validate_arguments',validate)
    monkeypatch.setattr(ae,'read',read)
    monkeypatch.setattr(ae.task_analytics,'server_time',lambda zone:dict(checked_at=NOW.isoformat(),local_date='2026-11-15',timezone=zone))
    return dict(common=common,summary=summary,sections=sections,calls=calls,read=read)


def execute(args=None,*,principal=ACTOR,check=lambda:None,max_reads=64):
    trace=[]
    checked,bundle=asyncio.run(ae.read_analysis(None,TOOL,args or {},{},trace,check,principal,max_reads=max_reads))
    return checked,bundle,trace


def test_valid_report_reads_every_section_and_renders_business_details(source):
    checked,result,trace=execute()
    assert result['status']=='complete' and result['complete'] is True
    assert source['calls']==[('summary',0),('equipment',0),('dates',0),('duplicates',0)]
    assert result['read_count']==len(result['reads'])==4
    assert set(result['sections'])=={'equipment','dates','duplicates'}
    assert result['provenance']['actor']['user_id']==str(ACTOR.user_id)
    assert result['provenance']['snapshot_id']=='a'*64
    assert checked['query']==dict(section='summary',offset=0)
    for text in ('2026-11-15','Незавершённых — **1**','Нагрузка по оборудованию','Нагрузка по датам',
                 'Дубликаты и нормы','UNIT-0','Известная трудоёмкость — **2 чел·ч**'):
        assert text in result['report']


def test_authorized_empty_snapshot_is_complete_but_not_a_claim_of_no_equipment(source):
    common,summary,sections=snapshot(0)
    source['common'].update(common);source['summary'].update(summary);source['sections'].update(sections)
    _,result,_=execute()
    assert result['complete'] is True and result['summary']['selected_tasks']==0
    assert 'не означает отсутствия объектов или регламентов' in result['report']


@pytest.mark.parametrize('fault',[
    'snapshot','site','role','timezone','visibility','origin','cohort','date_filter','counter',
    'clock','page_offset','page_total','empty_page','date_sum','repeated_equipment','nested_operations',
])
def test_inconsistent_results_never_return_a_complete_report(source,monkeypatch,fault):
    original=source['read']
    async def corrupt(app,tool,args,headers,trace):
        checked,data=await original(app,tool,args,headers,trace)
        section=args['query']['section']
        if section=='equipment':
            if fault=='snapshot':data['snapshot_id']='b'*64
            if fault=='site':data['scope']['site_id']=str(uuid4())
            if fault=='role':data['scope']['role']='executor'
            if fault=='timezone':data['timezone']='UTC'
            if fault=='visibility':data['scope']['visibility']='assigned_to_user'
            if fault=='origin':data['scope']['origin']='scheduled'
            if fault=='cohort':data['scope']['cohort']='in_review'
            if fault=='date_filter':data['scope']['starts_on']='2026-01-01'
            if fault=='counter':data['known_person_hours']='3'
            if fault=='clock':data['checked_at']='2026-11-08T08:00:00+00:00';data['local_date']='2026-11-08'
            if fault=='page_offset':data['offset']=1
            if fault=='page_total':data['total']=0
            if fault=='empty_page':data['items']=[]
            if fault=='repeated_equipment':data['items']*=2;data['total']=2
            if fault=='nested_operations':
                data['items'][0]['operations_total']=2;data['items'][0]['operations_truncated']=True
        if section=='dates' and fault=='date_sum':data['items'][0]['tasks']=0;data['items'][0]['deadline_only_tasks']=0
        return checked,data
    monkeypatch.setattr(ae,'read',corrupt)
    _,result,trace=execute()
    assert result['status']=='blocked' and result['complete'] is False
    assert result['summary'] is None and result['sections']=={}
    assert 'Полный анализ не выполнен' in result['report'] and 'Всего записей' not in result['report']
    assert 'это не означает отсутствия заданий' in result['report']
    assert any(row.get('tool')=='__evidence' and row['status']=='denied' for row in trace)


@pytest.mark.parametrize('code',[401,403,404,409,422,503])
def test_failed_summary_never_becomes_a_verified_empty_result(source,monkeypatch,code):
    async def denied(*args):raise HTTPException(code,'PRIVATE ERROR MUST NOT BE EXPOSED')
    monkeypatch.setattr(ae,'read',denied)
    _,result,trace=execute()
    assert result['status']=='blocked' and result['read_count']==1 and result['reads']==[]
    assert 'PRIVATE ERROR' not in str(result)
    assert result['reason']=='tool_error_'+str(code)


def test_read_budget_is_exact_and_no_empty_duplicate_section_is_silently_omitted(source):
    _,result,_=execute(max_reads=3)
    assert result['status']=='blocked' and result['read_count']==3
    assert source['calls']==[('summary',0),('equipment',0),('dates',0)]


@pytest.mark.parametrize('fault',['repeated_group','repeated_task','hidden_ids'])
def test_equal_aggregate_counts_do_not_hide_repeated_or_missing_duplicate_evidence(source,fault):
    common,summary,sections=snapshot(4)
    duplicate_counts=dict(candidate_groups=2,candidate_tasks=4,unchecked_tasks=0)
    common['business_duplicates']=summary['business_duplicates']=duplicate_counts
    ids=[str(uuid4()) for _ in range(4)]
    groups=[dict(equipment_ids=[sections['equipment'][index]['id']],operation='UNIT',
                 operation_title='Fixture operation',source_or_due_date='2026-11-16',sequence=1,
                 task_ids=ids[2*index:2*index+2],count=2,task_ids_truncated=False) for index in range(2)]
    if fault=='repeated_group':groups[1]['equipment_ids']=groups[0]['equipment_ids']
    if fault=='repeated_task':groups[1]['task_ids'][0]=groups[0]['task_ids'][0]
    if fault=='hidden_ids':groups[1].update(task_ids=groups[1]['task_ids'][:1],task_ids_truncated=True)
    sections['duplicates']=groups
    source['common'].update(common);source['summary'].update(summary);source['sections'].update(sections)
    _,result,_=execute()
    assert result['complete'] is False
    assert 'Всего записей' not in result['report']


def test_access_checked_before_every_read_and_context_pin_is_restored(source):
    from app.assistant.tools import EXPECTED_PRINCIPAL
    seen=[];previous=EXPECTED_PRINCIPAL.get()
    def check():seen.append(1)
    assert execute(check=check)[1]['complete'] is True
    assert len(seen)==4 and EXPECTED_PRINCIPAL.get()==previous


@pytest.mark.parametrize('args',[{'view':{'path':['counters']}},{'query':{'section':'dates'}},{'query':{'offset':25}}])
def test_full_report_does_not_reinterpret_projection_or_nonzero_page(source,args):
    _,result,_=execute(args)
    assert result['complete'] is False and source['calls']==[]


def _principal(client):
    profile=client.get('/api/v1/auth/session').json()['profile']
    return Principal(UUID(profile['userId']),UUID(profile['siteId']),profile['role'],profile['name'],
                     profile['email'],profile['siteName'],profile['timezone'])


def _authorized(app,client,*,args=None,principal=None,check=lambda:None,max_reads=64):
    trace=[]
    principal=principal or _principal(client)
    headers={'cookie':'; '.join(f'{key}={value}' for key,value in client.cookies.items())}
    checked,result=asyncio.run(ae.read_analysis(app,available(app,principal.role)['tasks_analyze'],args or {},headers,
                                              trace,check,principal,max_reads=max_reads))
    return checked,result,trace


def test_real_snapshot_reconciles_all_date_pages_load_norms_and_duplicate_groups(managed,clock):
    definitions=[dict(deadline=TODAY+timedelta(days=index+1)) for index in range(31)]
    definitions.extend((dict(status='in_review'),dict(status='completed')))
    add_orders(managed,definitions)
    engine,app,client,_,ids=managed
    with engine.connect() as db:
        before=db.scalar(text("SELECT md5(string_agg(to_jsonb(w)::text,',' ORDER BY work_order_id)) FROM work_orders w WHERE site_id=:site"),dict(site=ids['site']))
    _,result,trace=_authorized(app,client)
    assert result['complete'] is True,result
    assert result['summary']['counters']['all_tasks']==33
    assert result['summary']['counters']['unfinished']==32 and result['summary']['counters']['execution_pending']==31
    assert len(result['sections']['dates'])==31 and result['section_totals']['duplicates']==1
    assert result['read_count']==5
    assert [(read['arguments']['query']['section'],read['arguments']['query']['offset']) for read in result['reads']]==[
        ('summary',0),('equipment',0),('dates',0),('dates',25),('duplicates',0)]
    assert 'Незавершённых — **32**' in result['report'] and '2026-11-15' in result['report']
    with engine.connect() as db:
        after=db.scalar(text("SELECT md5(string_agg(to_jsonb(w)::text,',' ORDER BY work_order_id)) FROM work_orders w WHERE site_id=:site"),dict(site=ids['site']))
    assert before==after


def test_real_query_filters_are_bound_to_each_source_page(managed,clock):
    add_orders(managed,[dict(deadline=TODAY+timedelta(days=1)),dict(deadline=TODAY+timedelta(days=2))])
    _,app,client,_,_=managed
    query=dict(origin='manual',starts_on='2026-11-16',ends_on='2026-11-16',cohort='execution_pending')
    _,result,_=_authorized(app,client,args=dict(query=query))
    assert result['complete'] is True,result
    assert result['summary']['selected_tasks']==1 and result['summary']['counters']['all_tasks']==2
    assert result['provenance']['filters']==query
    assert all(all(read['arguments']['query'][key]==value for key,value in query.items()) for read in result['reads'])


def test_real_mutation_between_summary_and_details_never_yields_a_complete_report(managed,clock,monkeypatch):
    from app.assistant import read_transport
    identities,_=add_orders(managed,[dict()]);engine,app,client,_,_=managed
    original=read_transport.invoke;calls=[]
    async def changed(*args,**kwargs):
        value=await original(*args,**kwargs);calls.append(1)
        if len(calls)==1:
            with engine.begin() as db:
                db.execute(text("UPDATE work_orders SET status='completed',revision=revision+1 WHERE work_order_id=:id"),dict(id=identities[0]))
        return value
    monkeypatch.setattr(read_transport,'invoke',changed)
    _,result,trace=_authorized(app,client)
    assert result['complete'] is False and result['reason']=='tool_error_409'
    assert 'Данные изменились' in result['report'] and 'Всего записей' not in result['report']


def test_user_identity_is_checked_by_authorized_transport_not_just_scope_labels(managed,clock):
    add_orders(managed,[dict()]);_,app,client,_,_=managed
    actual=_principal(client)
    forged=Principal(uuid4(),actual.site_id,actual.role,actual.name,actual.email,actual.site_name,actual.timezone)
    _,result,_=_authorized(app,client,principal=forged)
    assert result['complete'] is False and result['reason']=='tool_error_403'


def test_executor_report_is_only_its_assigned_cohort(managed,clock):
    identities,_=add_orders(managed,[dict(),dict()]);engine,app,client,login,ids=managed
    worker,email=join(managed)
    with engine.begin() as db:
        db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
            VALUES (:site,:task,:user,:actor)'''),dict(site=ids['site'],task=identities[0],user=worker,actor=ids['user']))
    with closing(login(email)) as executor:
        _,result,_=_authorized(app,executor)
    assert result['complete'] is True,result
    assert result['summary']['counters']['all_tasks']==result['summary']['selected_tasks']==1
    assert result['provenance']['scope']['visibility']=='assigned_to_user'
    assert 'только назначенные вам задания' in result['report']
