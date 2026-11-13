"""Real PostgreSQL, authenticated commands, stale snapshots and a spawned solver."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from time import monotonic,sleep
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest
from sqlalchemy import text
from app.optimization_worker import OptimizationManager
from app.scheduling.optimization import calculate
from tests.backend.test_draft_plans import prepare,save,worker,BASE
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime,login

PATH='/api/v1/maintenance/optimization-runs/'

@pytest.fixture
def queued(managed):
    engine,app,_,_,_=managed
    app.state.optimizer=SimpleNamespace(alive=lambda:True,wake=lambda:None)
    try:yield managed
    finally:app.state.optimizer=None

def enqueue(managed,*,capacity=True):
    engine,app,_,_,ids=managed
    admin,_,_,_,_,request=prepare(managed)
    request['policy']['capacity_confirmed']=capacity
    worker_id=worker(managed,'TEST ONLY optimizer worker')
    record,_,_=save(admin,request)
    command=dict(expected_revision=1,idempotency_key=str(uuid4()),options=dict(time_limit_seconds=10))
    response=admin.post(BASE+f"/{record['draft_id']}/optimization-runs",json=command)
    assert response.status_code==202,response.text
    return admin,record,command,response.json(),worker_id

def finish(engine,run_id):
    with engine.connect() as conn:payload=conn.scalar(text('SELECT input_snapshot FROM draft_optimization_runs WHERE run_id=:id'),dict(id=run_id))
    result=calculate(payload)
    with engine.begin() as conn:
        conn.execute(text("UPDATE draft_optimization_runs SET state='succeeded',finished_at=now(),result=CAST(:result AS jsonb),baseline_segments=CAST(:baseline AS jsonb),optimized_segments=CAST(:optimized AS jsonb) WHERE run_id=:id"),dict(id=run_id,result=json.dumps(result['result'],default=str),baseline=json.dumps(result['baseline_segments']) if result['baseline_segments'] is not None else None,optimized=json.dumps(result['optimized_segments']) if result['optimized_segments'] is not None else None))
    return result

def test_explicit_apply_idempotency_and_no_active_plan_writes(queued):
    engine,_,_,_,ids=queued
    with engine.connect() as c:before={t:c.scalar(text(f'SELECT count(*) FROM {t}')) for t in ('work_orders','work_assignments','schedule_entries','schedule_plans')}
    admin,record,command,run,_=enqueue(queued);url=BASE+f"/{record['draft_id']}/optimization-runs"
    assert admin.post(url,json=command).status_code==200
    assert admin.post(url,json=dict(command,options=dict(time_limit_seconds=9))).status_code==409
    assert admin.post(url,json=dict(command,idempotency_key=str(uuid4()))).status_code==409
    finish(engine,run['run_id']);detail=admin.get(PATH+run['run_id']).json()
    assert detail['result']['optimized']['validation']['status']=='valid'
    assert admin.get(url).json()['items'][0]['result'] is None
    placements=admin.get(PATH+run['run_id']+'/placements?kind=optimized').json()
    assert placements['total']==1 and len(placements['items'][0]['worker_ids'])==1
    assert len(placements['occurrence_labels'])==1 and 'SYNTHETIC OPERATION 0190' in next(iter(placements['occurrence_labels'].values()))
    assert all('input_snapshot' not in r for r in [detail,run])
    body=dict(expected_revision=1,kind='optimized',reason='TEST ONLY reviewed balanced variant')
    applied=admin.post(PATH+run['run_id']+'/apply',json=body)
    assert applied.status_code==200,applied.text
    assert applied.json()['revision']==2
    assert admin.post(PATH+run['run_id']+'/apply',json=body).json()==applied.json()
    assert admin.post(PATH+run['run_id']+'/apply',json=dict(body,kind='baseline')).status_code==409
    assert admin.get(BASE+f"/{record['draft_id']}/versions").json()['total']==2
    with engine.connect() as c:assert before=={t:c.scalar(text(f'SELECT count(*) FROM {t}')) for t in before}

@pytest.mark.parametrize('change',['availability','revision','source'])
def test_changed_inputs_block_adoption(queued,change):
    engine,_,_,_,_=queued;admin,record,_,run,worker_id=enqueue(queued);finish(engine,run['run_id'])
    if change=='availability':
        with engine.begin() as c:c.execute(text('UPDATE availability_slots SET ends_at=ends_at-interval \'1 hour\' WHERE user_id=:id'),dict(id=worker_id))
    elif change=='revision':
        root=admin.get(BASE+f"/{record['draft_id']}/occurrences").json()['items'][0]['occurrence_id']
        segment=admin.get(BASE+f"/{record['draft_id']}/occurrences/{root}/segments").json()['items'][0]
        response=admin.post(BASE+f"/{record['draft_id']}/segments",json=dict(expected_revision=1,occurrence_id=root,segments=[segment],reason='TEST ONLY concurrent manual edit'))
        assert response.status_code==200,response.text
    else:
        with engine.begin() as c:c.execute(text("UPDATE equipment SET revision=revision+1 WHERE site_id=(SELECT site_id FROM draft_optimization_runs WHERE run_id=:id)"),dict(id=run['run_id']))
    response=admin.post(PATH+run['run_id']+'/apply',json=dict(expected_revision=1,kind='optimized',reason='TEST ONLY stale apply'))
    assert response.status_code==409,response.text

def test_cancel_permissions_site_scope_and_service_unavailable(queued):
    _,app,_,_,_=queued;admin,record,command,run,_=enqueue(queued);url=BASE+f"/{record['draft_id']}/optimization-runs"
    with closing(login(app,'chief_engineer')) as other:
        assert other.get(PATH+run['run_id']).status_code==404
        assert other.post(PATH+run['run_id']+'/cancel').status_code==404
        assert other.get(url).status_code==404
    with closing(login(app,'executor')) as executor:assert executor.get(PATH+run['run_id']).status_code==403
    with closing(login(app,'director')) as director:assert director.post(PATH+run['run_id']+'/cancel').status_code==403
    assert admin.post(PATH+run['run_id']+'/cancel',headers={'X-CSRF-Token':'bad'}).status_code==403
    assert admin.post(PATH+run['run_id']+'/cancel').json()['state']=='cancelled'
    assert admin.post(PATH+run['run_id']+'/cancel').json()['state']=='cancelled'
    assert admin.post(PATH+run['run_id']+'/apply',json=dict(expected_revision=1,kind='baseline',reason='TEST ONLY cancelled')).status_code==409
    app.state.optimizer=None
    assert admin.post(url,json=dict(command,idempotency_key=str(uuid4()))).status_code==503

@pytest.mark.parametrize('capacity',[True,False])
def test_spawned_worker_completes_and_stores_nullable_results(queued,capacity):
    engine,app,_,_,_=queued;admin,record,_,run,_=enqueue(queued,capacity=capacity)
    manager=OptimizationManager(engine);app.state.optimizer=manager;manager.start()
    try:
        deadline=monotonic()+30
        while monotonic()<deadline:
            detail=admin.get(PATH+run['run_id']).json()
            if detail['state'] in ('succeeded','failed','cancelled'):break
            sleep(.1)
        assert detail['state']=='succeeded',detail
        assert detail['result']['completion_reason']==('finished' if capacity else 'needs_input')
        assert bool(detail['result']['optimized'])==capacity
        assert admin.get(BASE+f"/{record['draft_id']}/versions").json()['total']==1
    finally:manager.stop()


def waiting_child(payload,cancel,output):
    cancel.wait(20)
    output.put(dict(ok=False,error='CANCELLED'))


def test_running_job_cancellation_wins_and_concurrent_retry_is_one_job(queued,monkeypatch):
    import app.optimization_worker as module
    monkeypatch.setattr(module,'child_calculate',waiting_child)
    engine,app,_,_,_=queued;admin,record,command,run,_=enqueue(queued)
    manager=OptimizationManager(engine);app.state.optimizer=manager;manager.start()
    try:
        deadline=monotonic()+15
        while monotonic()<deadline:
            if admin.get(PATH+run['run_id']).json()['state']=='running':break
            sleep(.05)
        assert admin.post(PATH+run['run_id']+'/cancel').json()['state']=='cancel_requested'
        while monotonic()<deadline:
            detail=admin.get(PATH+run['run_id']).json()
            if detail['state']=='cancelled':break
            sleep(.05)
        assert detail['state']=='cancelled' and detail['result'] is None
    finally:manager.stop()
    app.state.optimizer=SimpleNamespace(alive=lambda:True,wake=lambda:None)
    body=dict(command,idempotency_key=str(uuid4()))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:admin.post(BASE+f"/{record['draft_id']}/optimization-runs",json=body),range(2)))
    assert sorted(r.status_code for r in responses)==[200,202]
    assert len({r.json()['run_id'] for r in responses})==1


@pytest.mark.parametrize('state,expected',[('running','failed'),('cancel_requested','cancelled')])
def test_worker_restart_does_not_present_abandoned_job_as_success(queued,state,expected):
    engine,app,_,_,_=queued;admin,_,_,run,_=enqueue(queued)
    with engine.begin() as conn:conn.execute(text('UPDATE draft_optimization_runs SET state=:state,lease_token=:lease WHERE run_id=:id'),dict(state=state,lease=uuid4(),id=run['run_id']))
    manager=OptimizationManager(engine);manager.start()
    try:
        deadline=monotonic()+10
        while monotonic()<deadline:
            detail=admin.get(PATH+run['run_id']).json()
            if detail['state']==expected:break
            sleep(.05)
        assert detail['state']==expected and detail['result'] is None
        assert detail['error_code']==('WORKER_LOST' if expected=='failed' else None)
    finally:manager.stop()
