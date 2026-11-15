"""Opt-in live model evaluation; all domain data and writes are real, isolated PostgreSQL."""
import json,os,time
from datetime import date,datetime,timezone
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import text
from tests.backend.test_management import managed,config,equipment
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_draft_plans import prepare,save,worker,BASE
from tests.backend.test_assistant import B,thread,confirm

CASES=json.loads((Path(__file__).parents[1]/'fixtures/assistant/production_scenarios.json').read_text(encoding='utf-8'))
pytestmark=pytest.mark.skipif(os.environ.get('FIXRATE_SCENARIOS_LIVE')!='1',reason='Explicit live local model evaluation only')
ALLOWED={4:{'draft_save','portfolio_save','optimization_start','optimization_apply'},5:{'optimization_start'},6:{'optimization_start','optimization_apply'},7:{'optimization_start'},9:set(),12:{'optimization_start','optimization_apply','publication_prepare'}}

@pytest.fixture
def production_case(managed,monkeypatch):
    engine,app,admin,login,ids=managed
    provider_file=Path(os.environ.get('FIXRATE_LIVE_PROVIDER_FILE','/probe/provider.env'))
    live=provider_file.exists()
    if os.environ.get('FIXRATE_SCENARIOS_LIVE')=='1' and not live:raise RuntimeError('Live evaluation requires the pinned provider configuration')
    if live:
        env=dict(line.split('=',1) for line in provider_file.read_text().splitlines() if '=' in line)
        for key,value in env.items():monkeypatch.setenv(key,value)
        assert env.get('ASSISTANT_PROVIDER')=='ollama'
    else:
        class NoInference:
            def chat(self,*args):raise AssertionError('Typed production workflow must obtain facts from backend')
        app.state.assistant_provider_factory=NoInference
    admin,eq,import_id,row,decision,request=prepare(managed)
    request['ends_on']='2027-01-31'
    workers=[worker(managed,'SCENARIO worker '+str(i)) for i in (1,2)]
    for code,pattern in [('MONTHLY',dict(frequency='month',anchor_date='2027-01-01',month_days=[15])),('SEMIANNUAL',dict(frequency='yearly_count',anchor_date='2027-01-01',count_per_year=2,annual_policy='calendar_year'))]:
        body=config(date(2027,1,1),code='SCENARIO-'+code,title='SCENARIO '+code,pattern=pattern)
        reply=admin.chief.post('/api/v1/maintenance/equipment/'+eq['equipment_id']+'/service-configurations',json=body)
        assert reply.status_code==201,reply.text
    incomplete=admin.post('/api/v1/maintenance/equipment',json=dict(system_id=str(ids['system']),asset_code='SCENARIO-INCOMPLETE',name='SCENARIO missing regulations'))
    assert incomplete.status_code==201,incomplete.text
    for position,limit in [('KNOWN',100),('UNKNOWN',None)]:
        body=dict(position_code=position,name='SCENARIO part '+position,installed_on=date.today().isoformat(),usage_unit='hour',initial_usage='90',resource_limit=limit,resource_basis='SCENARIO explicit resource' if limit else None)
        response=admin.post('/api/v1/maintenance/equipment/'+eq['equipment_id']+'/components',json=body)
        assert response.status_code==201,response.text
    from tests.backend.test_catalog_decisions import write
    reviewed=write(admin.chief,import_id,row,decision,revision=1,confirm=True)
    assert reviewed.status_code==200,reviewed.text
    second_row=admin.get('/api/v1/maintenance/catalog-imports/'+import_id+'/operations?q=0191').json()['items'][0]['row']
    reviewed=write(admin.chief,import_id,second_row,decision,revision=0,confirm=True)
    assert reviewed.status_code==200,reviewed.text
    request['row_numbers']=[row,second_row]
    record,_,preview=save(admin,request)
    from app.optimization_worker import OptimizationManager
    manager=OptimizationManager(engine);app.state.optimizer=manager;manager.start()
    try:yield dict(engine=engine,app=app,admin=admin,chief=admin.chief,login=login,ids=ids,record=record,workers=workers,preview=preview)
    finally:
        manager.stop();app.state.optimizer=None
        if not live:del app.state.assistant_provider_factory
        with engine.begin() as c:
            for table in ('assistant_turn_attachments','assistant_actions','assistant_attachments','assistant_turns'):
                c.execute(text('DELETE FROM '+table+' WHERE conversation_id IN (SELECT conversation_id FROM assistant_conversations WHERE site_id=:site)'),dict(site=ids['site']))
            c.execute(text('DELETE FROM assistant_conversations WHERE site_id=:site'),dict(site=ids['site']))
            c.execute(text('DELETE FROM component_usage_readings WHERE site_id=:site'),dict(site=ids['site']))
            c.execute(text('DELETE FROM equipment_components WHERE site_id=:site'),dict(site=ids['site']))

def snapshot(case):
    with case['engine'].connect() as c:
        return {table:c.scalar(text(f"SELECT md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text,'[]')) FROM {table} t WHERE site_id=:site"),dict(site=case['ids']['site'])) for table in ('work_orders','work_assignments','schedule_entries','schedule_plans')}

@pytest.mark.parametrize('scenario',CASES,ids=[str(c['id']).zfill(2) for c in CASES])
def test_live_production_scenario(production_case,scenario):
    case=production_case;number=scenario['id'];client=case['chief'];role='chief_engineer'
    if number in (10,11):
        client=case['login'](case['workers'][0]+'@example.test');role='executor'
    if number in (6,12):
        draft=case['record']['draft_id'];occ=case['preview']['items'][0]['occurrence_id']
        segment=client.get(BASE+f'/{draft}/occurrences/{occ}/segments').json()['items'][0]
        segment.update(start_at='2027-01-02T09:00:00+05:00',end_at='2027-01-02T12:00:00+05:00',worker_ids=[case['workers'][0]],locked=True)
        placed=client.post(BASE+f'/{draft}/segments',json=dict(expected_revision=1,occurrence_id=occ,segments=[segment],reason='SCENARIO manual lock'))
        assert placed.status_code==200,placed.text
    with case['engine'].connect() as db:
        old_segments=db.scalar(text('SELECT segments FROM planning_draft_versions WHERE draft_id=:id ORDER BY revision DESC LIMIT 1'),dict(id=case['record']['draft_id']))
    def frozen(segments):
        return {s['segment_id']:dict(start=datetime.fromisoformat(s['start_at']).astimezone(timezone.utc).isoformat(),end=datetime.fromisoformat(s['end_at']).astimezone(timezone.utc).isoformat(),workers=sorted(s['worker_ids']),locked=True) for s in segments if s.get('locked')}
    locked=frozen(old_segments)
    chat=thread(client);before=snapshot(case);events=[];started=time.monotonic()
    try:
        message=client.post(B+f'/conversations/{chat}/messages',json=dict(content=scenario['prompt'],idempotency_key=str(uuid4())))
        assert message.status_code==202,message.text
        view=client.get(B+'/conversations/'+chat).json()
        seen=set()
        for phase in range(4):
            turn=view['turns'][-1];events.append(dict(kind='answer',content=turn['content'],answer=turn['answer'],status=turn['status'],trace=turn['trace'],error_code=turn['error_code']))
            confirmed=False
            for action in view['actions']:
                if action['action_id'] in seen:continue
                seen.add(action['action_id'])
                if action['tool_name'] not in ALLOWED.get(number,set()):
                    events.append(dict(kind='not_confirmed',tool=action['tool_name'],arguments=action['arguments']))
                    continue
                result=confirm(client,action);payload=result.json()
                events.append(dict(kind='confirmation',tool=action['tool_name'],http=result.status_code,status=payload.get('status'),result=payload.get('result'),arguments=action['arguments']))
                confirmed=payload.get('status')=='succeeded'
                if action['tool_name']=='optimization_start' and payload.get('status')=='succeeded':
                    run=payload['result']['data']['run_id']
                    for _ in range(120):
                        details=client.get('/api/v1/maintenance/optimization-runs/'+run).json()
                        if details.get('state') in ('succeeded','failed','cancelled'):break
                        time.sleep(.25)
                    events.append(dict(kind='solver',data=details))
            if not confirmed:break
            sent=client.post(B+f'/conversations/{chat}/messages',json=dict(content='Продолжи исходную задачу после подтверждённого действия. Покажи фактический результат и подготовь следующий шаг, если он был запрошен.',idempotency_key=str(uuid4())))
            assert sent.status_code==202,sent.text
            view=client.get(B+'/conversations/'+chat).json()
        after=snapshot(case)
        with case['engine'].connect() as db:
            final_segments=db.scalar(text('SELECT segments FROM planning_draft_versions WHERE draft_id=:id ORDER BY revision DESC LIMIT 1'),dict(id=case['record']['draft_id']))
        final_locked=frozen(final_segments)
        denied_publish=None
        if number in (10,11):
            denied=client.post('/api/v1/maintenance/publication-proposals/'+str(uuid4())+'/publish',json=dict(expected_digest='a'*64,approval_token=str(uuid4()),idempotency_key=str(uuid4())))
            denied_publish=denied.status_code;assert denied.status_code==403,denied.text
        output=dict(scenario=scenario,role=role,seconds=round(time.monotonic()-started,2),draft_id=str(case['record']['draft_id']),events=events,before=before,after=after,active_data_unchanged=before==after,locked_unchanged=locked==final_locked,backend_publication_status=denied_publish)
        directory=Path(os.environ.get('FIXRATE_SCENARIO_OUTPUT','/probe'))/os.environ.get('FIXRATE_SCENARIO_ROUND','production-round1');directory.mkdir(exist_ok=True)
        (directory/f'{number:02}.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps(dict(scenario=number,status=view['turns'][-1]['status'],actions=[a['tool_name'] for a in view['actions']],seconds=output['seconds'],active_data_unchanged=before==after)),flush=True)
        assert before==after,'Scenario must not publish or mutate active schedules'
        assert locked==final_locked,'Manual assignments must be preserved'
        if os.environ.get('FIXRATE_SCENARIO_ASSERT')=='1':
            answers='\n'.join(e['answer'] for e in events if e['kind']=='answer')
            succeeded={e['tool'] for e in events if e['kind']=='confirmation' and e['status']=='succeeded'}
            assert all(e['status']=='completed' for e in events if e['kind']=='answer'),events
            if number==2:assert '2027-01-15' in answers and 'SCENARIO SEMIANNUAL' in answers
            if number==3:assert 'не подтверждена трудоёмкость' in answers
            if number==4:assert {'portfolio_save','optimization_start','optimization_apply'}<=succeeded,events
            if number==5:assert 'optimization_start' in succeeded and any(e['kind']=='solver' and e['data']['result']['baseline'] and e['data']['result']['optimized'] for e in events)
            if number in (6,12):assert {'optimization_start','optimization_apply'}<=succeeded,events
            if number==7:assert 'пока не поддерживается' in answers and not view['actions']
            if number in (8,10,11):assert not view['actions']
            if number==9:assert all(n in answers for n in ('90.000','100.000','10.000','не задан')) and '90 000' not in answers
    finally:
        if number in (10,11):client.close()
