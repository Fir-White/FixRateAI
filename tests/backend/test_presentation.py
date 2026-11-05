"""The presentation fixture is synthetic; lifecycle calls use real HTTP/PostgreSQL."""
from contextlib import closing
import os
from uuid import UUID
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.integration.demo import demo_id
from app.integration.presentation import seed_presentation,identity
from tests.backend.test_runtime_integration import runtime,PREFIX
from tests.backend.test_automatic_photos import install_stub


def sign_in(app,email):
    client=TestClient(app)
    result=client.post('/api/v1/auth/login',json=dict(email=email,password=os.environ['FIXRATE_TEST_PASSWORD']))
    assert result.status_code==200,result.text
    client.headers['X-CSRF-Token']=result.json()['csrfToken']
    return client


def test_presentation_profile_is_complete_scoped_and_idempotent(runtime):
    engine,app=runtime
    with engine.connect() as c:
        before=list(c.execute(text('SELECT maintenance_rule_id,publication_status,schedule_parameters FROM maintenance_rules WHERE site_id=:id ORDER BY maintenance_rule_id'),dict(id=demo_id('site'))))
    result=seed_presentation(engine,os.environ['FIXRATE_TEST_PASSWORD'],storage=app.state.settings.photo_storage_root)
    assert result['operations']==6 and result['checklist_items']==46 and result['calendar_items']>=28*3
    with closing(sign_in(app,'engineer@fixrate.local')) as client:
        rows=client.get(PREFIX+'/ui/equipment').json()
        assert len(rows)==5 and all(r['siteId']==str(identity('site')) for r in rows)
        assert not any('DEMO' in r['name'] for r in rows)
        bundle=client.get(PREFIX+'/ui/tasks/'+result['photo_task_id']).json()
        assert bundle['task']['dataOrigin']=='synthetic_demo'
        assert bundle['execution']['photos'] and bundle['execution']['acts']
        assert bundle['execution']['actual']['person_hours']=='1.000'
    with engine.begin() as c:
        report_id=c.scalar(text('SELECT work_report_id FROM work_reports WHERE work_order_id=:id'),dict(id=UUID(result['photo_task_id'])))
        c.execute(text("UPDATE work_reports SET comment='Preserve my edit' WHERE work_report_id=:id"),dict(id=report_id))
        count=c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:id'),dict(id=identity('site')))
    repeated=seed_presentation(engine,os.environ['FIXRATE_TEST_PASSWORD'],storage=app.state.settings.photo_storage_root)
    assert repeated['photo_task_id']==result['photo_task_id']
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:id'),dict(id=identity('site')))==count
        assert c.scalar(text('SELECT comment FROM work_reports WHERE work_report_id=:id'),dict(id=report_id))=='Preserve my edit'
        assert list(c.execute(text('SELECT maintenance_rule_id,publication_status,schedule_parameters FROM maintenance_rules WHERE site_id=:id ORDER BY maintenance_rule_id'),dict(id=demo_id('site'))))==before
        assert c.scalar(text('SELECT count(*) FROM ai_quality_checks WHERE site_id=:id'),dict(id=identity('site')))==0


def test_presentation_report_runs_actual_workflow_with_explicit_ml_contract_stub(runtime,monkeypatch):
    engine,app=runtime
    result=seed_presentation(engine,os.environ['FIXRATE_TEST_PASSWORD'],storage=app.state.settings.photo_storage_root)
    task=result['photo_task_id'];calls=install_stub(monkeypatch)
    with closing(sign_in(app,'technician@fixrate.local')) as executor:
        bundle=executor.get(PREFIX+f'/ui/tasks/{task}').json()
        submitted=executor.post(PREFIX+f'/tasks/{task}/submit',json=dict(expected_revision=bundle['task']['revision']))
        assert submitted.status_code==200,submitted.text
        assert len(calls)==1
        bundle=executor.get(PREFIX+f'/ui/tasks/{task}').json()
        assert bundle['photoAnalysisStatus']=='ready' and bundle['task']['state']=='submitted'
    with closing(sign_in(app,'engineer@fixrate.local')) as engineer:
        act=bundle['execution']['acts'][0]
        denied=engineer.post(PREFIX+f'/tasks/{task}/review',json=dict(expected_revision=bundle['task']['revision'],execution_id=bundle['execution']['id'],verdict='accepted',reason='TEST protocol not yet checked'))
        assert denied.status_code==422
        verified=engineer.post(PREFIX+f'/tasks/{task}/acts/{act["id"]}/verify',json=dict(expected_revision=bundle['task']['revision'],reason='TEST verified fictional protocol'))
        assert verified.status_code==200,verified.text
        accepted=engineer.post(PREFIX+f'/tasks/{task}/review',json=dict(expected_revision=verified.json()['task']['revision'],execution_id=bundle['execution']['id'],verdict='accepted',reason='TEST explicit human acceptance'))
        assert accepted.status_code==200 and accepted.json()['task']['state']=='accepted',accepted.text
