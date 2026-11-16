"""Independent ledger fixtures in disposable PostgreSQL; no production writes or model facts."""
import asyncio, json
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import text, event
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed, equipment, config, join
from tests.backend.test_assistant import assistant_case, thread, B
from app.assistant.tools import available, describe, validate_arguments
from app.integration import task_analytics as analytics

URL='/api/v1/assistant/workspace/task-analysis'
TODAY=datetime(2026,11,15,8,tzinfo=timezone.utc)

def report_principal(case):
    engine,_,_,_,ids=case
    with engine.connect() as db:
        row=db.execute(text('SELECT name,timezone FROM sites WHERE site_id=:site'),dict(site=ids['site'])).one()
    return SimpleNamespace(site_name=row.name,timezone=row.timezone,site_id=ids['site'],role='admin')


@pytest.fixture
def clock(monkeypatch):
    # Test clock only: the public endpoint never accepts a caller supplied "now".
    from zoneinfo import ZoneInfo
    state=[TODAY]
    def server(zone):return dict(checked_at=state[0].isoformat(),timezone=zone,local_date=state[0].astimezone(ZoneInfo(zone)).date().isoformat())
    monkeypatch.setattr(analytics,'server_time',server)
    return state


def add_orders(case, definitions):
    engine,_,admin,_,ids=case
    eq=equipment(admin,ids)
    service=admin.chief.post(f"/api/v1/maintenance/equipment/{eq['equipment_id']}/service-configurations",json=config(date(2026,11,1)))
    assert service.status_code==201,service.text
    with engine.begin() as c:
        rule=c.scalar(text('SELECT maintenance_rule_id FROM rule_equipment WHERE site_id=:site AND binding_id=:binding'),dict(site=ids['site'],binding=service.json()['binding_id']))
        identities=[]
        for index,values in enumerate(definitions):
            identity=uuid4();identities.append(identity)
            defaults=dict(status='draft',deadline=TODAY+timedelta(days=1),start=None,norm='2',basis='total_person_hours',crew=2,
                snapshot=dict(code='OP',title='Test maintenance',norm_unit='person_hour',planning_duration_minutes=60))
            defaults.update(values)
            c.execute(text('''INSERT INTO work_orders(work_order_id,site_id,system_id,maintenance_rule_id,origin,status,
                required_people_snapshot,norm_hours_snapshot,norm_hours_basis_snapshot,operation_snapshot,planned_start_at,regulatory_deadline_at)
                VALUES (:id,:site,:system,:rule,'manual',:status,:crew,:norm,:basis,CAST(:snapshot AS jsonb),:start,:deadline)'''),
                dict(id=identity,site=ids['site'],system=ids['system'],rule=None if defaults.get('unruled') else rule,**{k:v for k,v in defaults.items() if k!='snapshot'},snapshot=json.dumps(defaults['snapshot'])))
            if not values.get('unlinked'):
                c.execute(text('INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id) VALUES (:site,:system,:id,:equipment)'),dict(site=ids['site'],system=ids['system'],id=identity,equipment=eq['equipment_id']))
    return identities,eq


def test_124_is_not_76_and_all_83_unfinished_are_aggregated(managed,clock):
    # Independently specified business statuses: 76 pending + 7 reviews + 41 done.
    definitions=[dict(status='draft',deadline=TODAY+timedelta(days=i+1)) for i in range(75)]
    definitions += [dict(status='assigned')]+[dict(status='in_review') for _ in range(7)]+[dict(status='completed') for _ in range(41)]
    add_orders(managed,definitions)
    _,_,admin,_,_=managed
    old=admin.get('/api/v1/assistant/workspace/tasks',params=dict(period='all',active_only=False)).json()
    pending=admin.get('/api/v1/assistant/workspace/tasks',params=dict(period='all')).json()
    response=admin.get(URL);assert response.status_code==200,response.text
    data=response.json()
    assert old['total']==124 and len(old['items'])==25 and pending['total']==76
    assert data['complete'] is True and data['scanned_tasks']==124 and data['selected_tasks']==83
    assert data['counters']['unfinished']==83 and data['counters']['execution_pending']==76 and data['counters']['completed']==41
    assert data['sample_truncated'] is True and sum(data['due'].values())==83
    from decimal import Decimal
    assert Decimal(data['known_person_hours'])==166
    first=admin.get(URL,params=dict(section='dates')).json()
    second=admin.get(URL,params=dict(section='dates',offset=25)).json()
    assert first['total']>25 and first['snapshot_id']==second['snapshot_id']
    # Counts are whole-set aggregates, never the 25-row sample.
    assert sum(r['tasks'] for r in first['items'])<83
    assert admin.get(URL).json()==data


def test_server_date_timezone_and_deadline_rules_change_with_date(managed,clock):
    engine,_,admin,_,ids=managed
    with engine.begin() as c:c.execute(text("UPDATE sites SET timezone='Asia/Yekaterinburg' WHERE site_id=:site"),dict(site=ids['site']))
    add_orders(managed,[dict(deadline=TODAY-timedelta(seconds=1)),dict(deadline=TODAY),
        dict(deadline=datetime(2026,11,15,18,tzinfo=timezone.utc),start=TODAY),
        dict(deadline=TODAY+timedelta(days=1),start=TODAY-timedelta(days=2)),dict(deadline=None)])
    data=admin.get(URL).json()
    assert data['local_date']=='2026-11-15' and data['timezone']=='Asia/Yekaterinburg'
    assert data['due']==dict(overdue=2,today=1,future=1,undated=1)
    assert data['scheduled']==dict(unscheduled=3,today=1,past=1)
    clock[0]=datetime(2026,11,15,20,tzinfo=timezone.utc)  # Already Nov16 in object zone.
    changed=admin.get(URL).json()
    assert changed['local_date']=='2026-11-16' and changed['due']['overdue']==3
    assert changed['snapshot_id']!=data['snapshot_id']
    assert admin.get(URL,params={'now':'2026-11-07'}).status_code==422


def test_business_duplicates_use_operation_equipment_date_not_id(managed,clock):
    identities,_=add_orders(managed,[dict(),dict(),dict(deadline=TODAY+timedelta(days=2)),
        dict(unruled=True,snapshot=dict(code='OTHER',norm_unit='person_hour',planning_duration_minutes=60)),dict(deadline=None,unlinked=True)])
    _,_,admin,_,_=managed
    response=admin.get(URL,params=dict(section='duplicates'));assert response.status_code==200,response.text
    data=response.json()
    assert len(set(identities))==5
    assert data['business_duplicates']['candidate_groups']==1 and data['business_duplicates']['unchecked_tasks']==1
    assert set(data['items'][0]['task_ids'])=={str(i) for i in identities[:2]}


@pytest.mark.parametrize('unit,norm,crew,minutes,expected,hours',[
    ('person_hour','3',2,90,'consistent','3'),('elapsed_hour','1.5',2,90,'consistent','3.0'),
    ('person_hour','1.5',2,90,'mismatch','1.5'),('unconfirmed','1.5',2,90,'unknown_unit',None),
    ('person_hour','0',2,90,'missing_norm',None),('person_hour','2',2,None,'missing_duration','2')])
def test_norm_units_are_not_compared_to_minutes_directly(unit,norm,crew,minutes,expected,hours):
    row=dict(operation_snapshot=dict(norm_unit=unit,planning_duration_minutes=minutes),norm_hours_snapshot=norm,
        norm_hours_basis_snapshot='per_person' if unit=='elapsed_hour' else 'total_person_hours',required_people_snapshot=crew)
    result=analytics.effort(row)
    assert result['status']==expected and result['person_hours']==hours


def test_contradictory_norm_basis_does_not_certify_effort():
    row=dict(operation_snapshot=dict(norm_unit='elapsed_hour',planning_duration_minutes=90),norm_hours_snapshot='1.5',
        norm_hours_basis_snapshot='total_person_hours',required_people_snapshot=2)
    assert analytics.effort(row)==dict(status='basis_unit_conflict',person_hours=None)


def test_executor_sees_only_assigned_and_other_site_is_excluded(managed,clock):
    ids,_=add_orders(managed,[dict(),dict()]);engine,_,admin,login,site=managed
    user,address=join(managed)
    with engine.begin() as c:
        c.execute(text("INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by) VALUES (:site,:task,:user,:admin)"),dict(site=site['site'],task=ids[0],user=user,admin=site['user']))
    with closing(login(address)) as executor:
        result=executor.get(URL);assert result.status_code==200,result.text
        data=result.json();assert data['selected_tasks']==1 and data['scope']['visibility']=='assigned_to_user'
        assert data['counters']['all_tasks']==1
        assert executor.get(URL,params=dict(site_id=str(uuid4()))).status_code==422
    assert admin.chief.get(URL).json()['selected_tasks']==2
    assert admin.get(URL).json()['selected_tasks']==2


def test_empty_result_is_complete_not_denied(managed,clock):
    _,_,admin,_,_=managed
    data=admin.get(URL).json()
    assert data['selected_tasks']==0 and data['complete'] and data['due']=={} and data['norm_checks']=={}


def test_bounded_snapshot_fails_closed_and_query_count_does_not_scale(managed,clock,monkeypatch):
    add_orders(managed,[dict(),dict(),dict()]);engine,_,admin,_,_=managed
    statements=[]
    def capture(conn,cursor,statement,parameters,context,many):
        if 'FROM work_orders w' in statement:statements.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:data=admin.get(URL)
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert data.status_code==200 and len(statements)==1
    monkeypatch.setattr(analytics,'MAX_ROWS',2)
    response=admin.get(URL)
    assert response.status_code==413 and 'complete' not in response.json()


def test_chat_repeats_original_request_with_server_analysis_and_no_mutations(assistant_case,clock):
    engine,app,admin,_,ids=assistant_case;add_orders(assistant_case,[dict(),dict(status='in_review')])
    def fingerprint():
        with engine.connect() as c:return c.scalar(text("SELECT md5(string_agg(to_jsonb(w)::text,',' ORDER BY work_order_id)) FROM work_orders w WHERE site_id=:site"),dict(site=ids['site']))
    before=fingerprint()
    class SemanticPlan:
        def chat(self,messages,schema,tokens):
            if schema.__name__=='ToolSelection':
                return schema(tools=[],goals=[dict(id='analysis',title='Проверить сроки, нагрузку и дубликаты незавершённых заданий',kind='read',tool='tasks_analyze',requires_full_list=True)])
            assert schema.__name__=='AgentStep'
            return schema(answer='',calls=[dict(tool='tasks_analyze',arguments_json=json.dumps(dict(query=dict(section='summary'))),explanation='TEST ONLY semantic analysis; server reads and reconciles all sections')])
    app.state.assistant_provider_factory=SemanticPlan
    chat=thread(admin);question='Проанализируй незавершённые задания: сроки, нагрузку и дубликаты. Ничего не изменяй.'
    try:
        answers=[];proofs=[]
        for _ in range(2):
            response=admin.post(B+f'/conversations/{chat}/messages',json=dict(content=question,idempotency_key=str(uuid4())))
            assert response.status_code==202,response.text
            turns=admin.get(B+f'/conversations/{chat}').json()['turns'];turn=turns[-1]
            assert turn['status']=='completed',turn
            assert turn['workflow']['outcome']=='completed',turn
            business=[entry for entry in turn['trace'] if not entry['tool'].startswith('__') and entry['status']!='running']
            assert all(t['tool']=='tasks_analyze' and t['status']=='completed' for t in business)
            with engine.connect() as db:saved=db.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'),dict(id=turn['turn_id']))
            bundle=saved['evidence'][-1]['result']
            assert bundle['complete'] and bundle['status']=='complete'
            by_section={row['arguments']['query']['section']:row['result'] for row in saved['evidence']
                        if isinstance(row['result'],dict) and 'counters' in row['result']}
            assert set(by_section)=={'summary','equipment','dates','duplicates'}
            assert all(result['counters']['unfinished']==2 and result['local_date']=='2026-11-15' for result in by_section.values())
            proofs.append(by_section)
            assert '2026-11-15' in turn['answer'] and 'Незавершённых — **2**' in turn['answer']
            assert 'Источни' not in turn['answer'] or 'PostgreSQL' in turn['answer']
            answers.append(turn['answer'])
        assert proofs[0]==proofs[1]
        assert admin.get(B+f'/conversations/{chat}').json()['actions']==[]
        assert fingerprint()==before
        print(json.dumps(dict(analytics_chat=dict(status=turn['status'],answer=turn['answer'],trace=turn['trace'],actions=[])),ensure_ascii=True))
    finally:del app.state.assistant_provider_factory


@pytest.mark.parametrize('code,reason',[(403,'Доступ к данным ограничен'),(503,'Не удалось прочитать'),(409,'Данные изменились')])
def test_report_faults_are_not_empty_or_full(assistant_case,monkeypatch,code,reason):
    from app.assistant import read_transport
    from app.assistant.task_report import report
    _,app,admin,_,_=assistant_case
    async def fault(*args):raise HTTPException(code,'injected failure')
    monkeypatch.setattr(read_transport,'invoke',fault)
    trace=[]
    answer=asyncio.run(report(app,available(app,'admin')['tasks_analyze'],{},trace,lambda:None,'Проанализируй все задания',report_principal(assistant_case)))
    assert 'Полный анализ не выполнен' in answer and reason in answer and 'Заданий нет' not in answer
    assert len(trace)==1


def test_tool_schema_and_registration_use_actual_route(managed):
    _,app,admin,_,_=managed
    for role in ('chief_engineer','engineer','dispatcher','admin','director','executor'):
        tool=available(app,role)['tasks_analyze'];schema=describe(app,tool)['inputSchema']
        assert schema['properties']['query']['properties']['section']['enum']==['summary','dates','equipment','duplicates']
        assert validate_arguments(app,tool,dict(query=dict(section='summary')))['query']['section']=='summary'
    assert admin.get('/api/v1/assistant/workspace/tasks',params=dict(state='active',period='all')).status_code==422


def test_shifted_weekend_obligations_are_not_duplicates():
    # Distinct source dates and repeated obligations may legitimately share a due day.
    from app.schemas.maintenance import CalendarPattern
    from app.scheduling.recurrence import occurrence_pairs
    pattern=CalendarPattern(frequency='day',interval=1,anchor_date=date(2026,11,1),weekend_policy='next_workday')
    pairs=occurrence_pairs(pattern,date(2026,11,14),date(2026,11,16))
    assert len(pairs)==3 and len(set(due for _,due in pairs))==1 and len(set(source for source,_ in pairs))==3
    row=dict(equipment=[dict(id='eq')],operation_template_id='operation',operation_snapshot={},operation_code='OP',sequence_no=1)
    keys=[analytics.business_key(dict(row,source_date=source),due,None) for source,due in pairs]
    assert len(set(keys))==3
    assert analytics.business_key(dict(row,source_date=pairs[0][0],sequence_no=2),pairs[0][1],None) not in keys


def test_exclusive_midnight_deadline_belongs_to_previous_day():
    from zoneinfo import ZoneInfo
    row=dict(regulatory_deadline_at=datetime(2026,11,15,19,tzinfo=timezone.utc),regulatory_deadline_on=None,planned_start_at=None)
    due,_,day,_=analytics.timing(row,TODAY,ZoneInfo('Asia/Yekaterinburg'))
    assert due=='today' and day==date(2026,11,15)
    assert analytics.timing(row,row['regulatory_deadline_at'],ZoneInfo('Asia/Yekaterinburg'))[0]=='overdue'


def test_period_filter_does_not_relabel_all_site_counter(managed,clock):
    add_orders(managed,[dict(deadline=TODAY-timedelta(days=1)),dict(),dict(deadline=TODAY+timedelta(days=5)),dict(status='cancelled')])
    _,_,admin,_,_=managed
    response=admin.get(URL,params=dict(starts_on='2026-11-16',ends_on='2026-11-16',origin='manual'))
    assert response.status_code==200,response.text
    data=response.json()
    assert data['counters']['all_tasks']==4 and data['counters']['unfinished']==3 and data['selected_tasks']==1
    assert data['scope']['starts_on']=='2026-11-16' and data['scope']['origin']=='manual'
    assert admin.get(URL,params=dict(starts_on='2026-11-17',ends_on='2026-11-16')).status_code==422


def test_role_revocation_is_not_cached_as_empty(managed,clock):
    engine,_,admin,_,ids=managed
    assert admin.get(URL).status_code==200
    with engine.begin() as c:c.execute(text('UPDATE site_memberships SET is_active=false WHERE site_id=:site AND user_id=:user'),dict(site=ids['site'],user=ids['user']))
    # Membership revocation invalidates the session under the existing auth contract.
    assert admin.get(URL).status_code==401


def test_data_change_between_sections_never_yields_full_report(assistant_case,clock,monkeypatch):
    from app.assistant import read_transport
    from app.assistant.task_report import report
    identities,_=add_orders(assistant_case,[dict()]);engine,app,admin,_,_=assistant_case
    original=read_transport.invoke;calls=[]
    async def changing(*args):
        value=await original(*args);calls.append(1)
        if len(calls)==1:
            with engine.begin() as c:c.execute(text("UPDATE work_orders SET status='completed',revision=revision+1 WHERE work_order_id=:id"),dict(id=identities[0]))
        return value
    monkeypatch.setattr(read_transport,'invoke',changing)
    headers={'cookie':'; '.join(f'{k}={v}' for k,v in admin.cookies.items())}
    answer=asyncio.run(report(app,available(app,'admin')['tasks_analyze'],headers,[],lambda:None,'Проанализируй все задания',report_principal(assistant_case)))
    assert 'Полный анализ не выполнен' in answer and 'Данные изменились' in answer
    assert 'Всего записей' not in answer


def test_final_prose_receives_server_clock_even_without_tools(assistant_case,clock):
    _,app,admin,_,_=assistant_case
    class ClockBoundary:
        def chat(self,messages,schema,tokens):
            if schema.__name__=='ToolSelection':
                return schema(tools=[],goals=[dict(id='clock',title='Назвать дату сервера',kind='conversation',tool='')])
            assert schema.__name__=='FinalReply'
            context=json.loads(messages[-1]['content'])['server_context']
            assert context['local_date']=='2026-11-15' and context['timezone']
            return schema(answer='TEST ONLY: server clock reached the final prompt')
    app.state.assistant_provider_factory=ClockBoundary
    try:
        chat=thread(admin)
        response=admin.post(B+f'/conversations/{chat}/messages',json=dict(content='Какая сегодня дата в системе?',idempotency_key=str(uuid4())))
        assert response.status_code==202
        turn=admin.get(B+f'/conversations/{chat}').json()['turns'][-1]
        assert turn['status']=='completed' and turn['workflow']['outcome']=='completed'
        assert 'TEST ONLY: server clock reached the final prompt' in turn['answer']
    finally:del app.state.assistant_provider_factory


def test_periodic_operation_count_is_explained_by_real_calendar(managed,clock):
    _,_,admin,login,ids=managed
    created=admin.post('/api/v1/maintenance/equipment',json=dict(system_id=str(ids['system']),equipment_type_id=str(ids['type']),
        asset_code='CALENDAR-'+ids['marker'],name='Calendar fixture pump',commissioned_on='2023-11-06'))
    assert created.status_code==201,created.text
    eq=created.json()
    # A complete future month: generation intentionally refuses expired obligations.
    year=datetime.now(timezone.utc).year+1
    first,last=date(year,11,1),date(year,11,30)
    pattern=dict(frequency='day',interval=1,anchor_date=first.isoformat(),weekend_policy='next_workday')
    saved=admin.chief.post(f"/api/v1/maintenance/equipment/{eq['equipment_id']}/service-configurations",json=config(first,pattern=pattern))
    assert saved.status_code==201,saved.text
    _,address=join(managed,'dispatcher')
    with closing(login(address)) as dispatcher:
        preview=dispatcher.get(f'/api/v1/maintenance/ui/calendar/preview?year={year}&month=11').json()
        result=dispatcher.post('/api/v1/maintenance/calendar/generate',json=dict(year=year,month=11,preview_token=preview['generationToken'],idempotency_key=str(uuid4())))
        assert result.status_code==200,result.text
    from app.schemas.maintenance import CalendarPattern
    from app.scheduling.recurrence import occurrence_pairs
    expected=occurrence_pairs(CalendarPattern.model_validate_json(json.dumps(pattern)),first,last)
    data=admin.get(URL,params=dict(section='equipment',origin='scheduled')).json()
    assert data['selected_tasks']==len(expected)==30
    operation=data['items'][0]['operations'][0]
    assert operation['tasks']==30 and operation['calendar_pattern']==saved.json()['pattern']
    assert operation['plan_periods']==[f'{year}-11']
    assert operation['first_source_date']==first.isoformat() and operation['last_source_date']==last.isoformat()
    assert data['business_duplicates']['candidate_groups']==0
