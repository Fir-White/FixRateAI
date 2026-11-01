from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, timedelta
import json
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db.repository import MaintenanceRepository
from app.integration.demo import demo_id
from tests.backend.test_runtime_integration import runtime, login, PREFIX

RULE=demo_id('planning-rule')


@pytest.fixture
def planning(runtime):
    engine,app=runtime
    with engine.connect() as conn:
        day=conn.scalar(text('SELECT active_from FROM maintenance_rules WHERE maintenance_rule_id=:id'),{'id':RULE})
    try:
        yield engine,app,day
    finally:
        with engine.begin() as c:
            params={'id':RULE}
            for sql in [
                'DELETE FROM work_assignments WHERE work_order_id IN (SELECT work_order_id FROM work_orders WHERE maintenance_rule_id=:id)',
                'DELETE FROM work_order_equipment WHERE work_order_id IN (SELECT work_order_id FROM work_orders WHERE maintenance_rule_id=:id)',
                'DELETE FROM audit_events WHERE entity_id IN (SELECT work_order_id FROM work_orders WHERE maintenance_rule_id=:id)',
                'DELETE FROM work_orders WHERE maintenance_rule_id=:id',
                'DELETE FROM schedule_entries WHERE maintenance_rule_id=:id',
                'DELETE FROM orchestration_decisions WHERE maintenance_rule_id=:id',
                'DELETE FROM forecast_runs WHERE maintenance_rule_id=:id',
            ]: c.execute(text(sql),params)
            c.execute(text("DELETE FROM schedule_plans WHERE source_snapshot ? 'planning_run_id'"))
            c.execute(text('DELETE FROM planning_runs'))


def body(client,day):
    response=client.get(PREFIX+f'/ui/calendar/preview?year={day.year}&month={day.month}')
    assert response.status_code==200,response.text
    preview=response.json()
    assert any(row['operationCode']=='DEMO-PIPELINE' for row in preview['items']),preview
    return dict(year=day.year,month=day.month,preview_token=preview['generationToken'],idempotency_key=str(uuid4()))


def counts(engine):
    with engine.connect() as c:
        result={name:c.scalar(text(f'SELECT count(*) FROM {name} WHERE maintenance_rule_id=:id'),{'id':RULE})
                for name in ('work_orders','schedule_entries','forecast_runs','orchestration_decisions')}
        result['runs']=c.scalar(text('SELECT count(*) FROM planning_runs'))
        return result


def test_generation_persists_both_forecasts_task_and_replays_without_duplicates(planning):
    engine,app,day=planning
    with closing(login(app,'dispatcher')) as client:
        request=body(client,day)
        response=client.post(PREFIX+'/calendar/generate',json=request)
        assert response.status_code==200,response.text
        result=response.json()
        assert result['createdCount']==1 and not result['replayed']
        row=next(row for row in result['items'] if row['operationTitle']=='DEMO — сквозное планирование')
        assert row['state']=='draft' and row['comparison']['algorithmic']['status']=='ok'
        assert row['comparison']['snapshotHash']
        assert row['assignment']['status']=='ok' and len(row['assignment']['selectedWorkers'])==2
        task_response=client.get(PREFIX+f"/ui/tasks/{row['taskId']}")
        assert task_response.status_code==200,task_response.text
        task=task_response.json()['task']
        # Midnight ending the due day must not display as a one-day extension.
        assert task['mandatoryDueDate']==day.isoformat()
        before=counts(engine)
        assert before==dict(work_orders=1,schedule_entries=1,forecast_runs=2,orchestration_decisions=1,runs=1)
        repeated=client.post(PREFIX+'/calendar/generate',json=request)
        assert repeated.status_code==200 and repeated.json()==dict(result,replayed=True)
        assert counts(engine)==before
        request['idempotency_key']=str(uuid4())
        other=client.post(PREFIX+'/calendar/generate',json=request)
        assert other.status_code==200,other.text
        assert other.json()['createdCount']==0 and other.json()['existingCount']==1
        assert counts(engine)==dict(before,runs=2)
        saved=client.get(PREFIX+f'/ui/calendar?year={day.year}&month={day.month}').json()
        assert any(item['taskId']==row['taskId'] for item in saved)
        # The end-to-end response carries a proposal, never an implicit reservation.
        with engine.connect() as c:
            assert c.scalar(text('SELECT count(*) FROM work_assignments WHERE work_order_id=:id'),{'id':row['taskId']})==0
        assigned=client.post(PREFIX+f"/tasks/{row['taskId']}/assign",json={**row['assignment']['command'],'crew_id':row['assignment']['crewId']})
        assert assigned.status_code==200,assigned.text
        assert assigned.json()['task']['state']=='assigned'


@pytest.mark.parametrize('role',['admin','engineer','executor'])
def test_generation_role_matrix(planning,role):
    engine,app,day=planning
    with closing(login(app,'dispatcher')) as client: request=body(client,day)
    before=counts(engine)
    with closing(login(app,role)) as client:
        assert client.post(PREFIX+'/calendar/generate',json=request).status_code==403
    assert counts(engine)==before


def test_generation_rejects_csrf_and_stale_preview_and_conflicting_key(planning):
    engine,app,day=planning
    with closing(login(app,'dispatcher')) as client:
        request=body(client,day)
        assert client.post(PREFIX+'/calendar/generate',json=request,headers={'X-CSRF-Token':'bad'}).status_code==403
        assert client.post(PREFIX+'/calendar/generate',json={**request,'preview_token':'1'*64}).status_code==409
        assert counts(engine)['work_orders']==0
        with engine.begin() as c:
            old=c.scalar(text('SELECT title FROM operation_templates WHERE operation_template_id=:id'),{'id':demo_id('planning-operation')})
            c.execute(text("UPDATE operation_templates SET title='Changed operation' WHERE operation_template_id=:id"),{'id':demo_id('planning-operation')})
        try:
            assert client.post(PREFIX+'/calendar/generate',json=request).status_code==409
        finally:
            with engine.begin() as c:
                c.execute(text('UPDATE operation_templates SET title=:title WHERE operation_template_id=:id'),{'id':demo_id('planning-operation'),'title':old})
        assert client.post(PREFIX+'/calendar/generate',json=request).status_code==200
        changed={**request,'month':day.month%12+1}
        assert client.post(PREFIX+'/calendar/generate',json=changed).status_code==409


@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_generation_serializes_the_month_and_preserves_single_occurrence(planning,same_key):
    engine,app,day=planning
    with closing(login(app,'dispatcher')) as one,closing(login(app,'dispatcher')) as two:
        request=body(one,day)
        second=dict(request,idempotency_key=request['idempotency_key'] if same_key else str(uuid4()))
        barrier=Barrier(2)
        def send(client,payload):
            barrier.wait(timeout=10)
            return client.post(PREFIX+'/calendar/generate',json=payload)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(send,one,request)
            b=pool.submit(send,two,second)
            responses=[a.result(timeout=30),b.result(timeout=30)]
        assert all(r.status_code==200 for r in responses),[r.text for r in responses]
        assert counts(engine)==dict(work_orders=1,schedule_entries=1,forecast_runs=2,orchestration_decisions=1,runs=1 if same_key else 2)


def test_model_absence_keeps_generation_on_rules(planning):
    _,app,day=planning
    original=app.state.forecaster
    app.state.forecaster=None
    try:
        with closing(login(app,'dispatcher')) as client:
            response=client.post(PREFIX+'/calendar/generate',json=body(client,day))
            assert response.status_code==200,response.text
            row=response.json()['items'][0]
            assert row['comparison']['ai']['status']=='unavailable'
            assert row['comparison']['ai']['errorCode']=='MODEL_NOT_READY'
            assert row['comparison']['decision']['status']=='fallback'
            assert row['created']
    finally: app.state.forecaster=original


def test_generation_does_not_rewrite_existing_task_after_rule_edit(planning):
    engine,app,day=planning
    with closing(login(app,'dispatcher')) as client:
        created=client.post(PREFIX+'/calendar/generate',json=body(client,day))
        assert created.status_code==200
        task_id=created.json()['items'][0]['taskId']
        before=counts(engine)
        with engine.begin() as c:
            original=c.scalar(text('SELECT title FROM operation_templates WHERE operation_template_id=:id'),{'id':demo_id('planning-operation')})
            c.execute(text("UPDATE operation_templates SET title='Edited operation' WHERE operation_template_id=:id"),{'id':demo_id('planning-operation')})
        try:
            response=client.post(PREFIX+'/calendar/generate',json=body(client,day))
            assert response.status_code==200,response.text
            assert any(w['code']=='EXISTING_VERSION_CHANGED' for w in response.json()['warnings'])
            assert counts(engine)==dict(before,runs=before['runs']+1)
            assert client.post(PREFIX+f'/tasks/{task_id}/forecast',json={'expected_revision':1}).status_code==409
        finally:
            with engine.begin() as c:
                c.execute(text('UPDATE operation_templates SET title=:title WHERE operation_template_id=:id'),{'id':demo_id('planning-operation'),'title':original})


def test_crossing_local_midnight_requires_a_new_preview(planning,monkeypatch):
    from datetime import datetime
    import app.integration.planning as module
    engine,app,day=planning
    with closing(login(app,'dispatcher')) as client:
        request=body(client,day)
        instant=datetime.now(module.timezone.utc)
        class Clock(datetime):
            calls=0
            @classmethod
            def now(cls,tz=None):
                cls.calls+=1
                return (instant+timedelta(days=1) if cls.calls>1 else instant).astimezone(tz)
        monkeypatch.setattr(module,'datetime',Clock)
        before=counts(engine)
        response=client.post(PREFIX+'/calendar/generate',json=request)
        assert response.status_code==409,response.text
        assert 'STALE_PREVIEW' in response.text and counts(engine)==before


def test_generation_failure_rolls_back_tasks_forecasts_plan_and_idempotency_record(planning,monkeypatch):
    engine,app,day=planning
    following=(day.replace(day=28)+timedelta(days=4)).replace(day=1)
    with engine.begin() as c:
        prior=dict(c.execute(text('SELECT period_unit,active_from,active_until,schedule_parameters FROM maintenance_rules WHERE maintenance_rule_id=:id'),{'id':RULE}).mappings().one())
        c.execute(text("UPDATE maintenance_rules SET period_unit='day',active_from=:start,active_until=:end,schedule_parameters=schedule_parameters || CAST(:params AS jsonb) WHERE maintenance_rule_id=:id"),
            {'id':RULE,'start':following,'end':following+timedelta(days=1),'params':json.dumps({'anchor_date':str(following)})})
    try:
        with closing(login(app,'dispatcher')) as client:
            request=body(client,following)
            before=counts(engine)
            original=MaintenanceRepository.add
            calls=0
            def broken(repo,table,**values):
                nonlocal calls
                if table=='work_orders': calls+=1
                if calls==2: raise RuntimeError('injected generation failure')
                return original(repo,table,**values)
            monkeypatch.setattr(MaintenanceRepository,'add',broken)
            with pytest.raises(RuntimeError,match='injected'):
                client.post(PREFIX+'/calendar/generate',json=request)
            assert counts(engine)==before
    finally:
        with engine.begin() as c:
            c.execute(text('UPDATE maintenance_rules SET period_unit=:unit,active_from=:start,active_until=:end,schedule_parameters=CAST(:params AS jsonb) WHERE maintenance_rule_id=:id'),
                {'id':RULE,'unit':prior['period_unit'],'start':prior['active_from'],'end':prior['active_until'],'params':json.dumps(prior['schedule_parameters'])})
