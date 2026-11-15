"""Repeatable domain regression: real DB and solver, inference explicitly forbidden."""
import pytest
from uuid import uuid4
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant_production_scenarios import production_case,CASES,test_live_production_scenario as _run

@pytest.mark.parametrize('scenario',CASES,ids=[str(c['id']).zfill(2) for c in CASES])
def test_production_workflow(production_case,scenario,tmp_path,monkeypatch):
    monkeypatch.setenv('FIXRATE_SCENARIO_ASSERT','1')
    monkeypatch.setenv('FIXRATE_SCENARIO_OUTPUT',str(tmp_path))
    _run(production_case,scenario)

def test_authorized_publication_requires_each_confirmation_and_writes_real_tasks(managed):
    from tests.backend.test_publication import prepared
    from tests.backend.test_assistant import B,thread,confirm
    engine,app,_,_,ids=managed
    admin,record,proposal,_,_=prepared(managed)
    client=admin.chief;chat=thread(client)
    class NoInference:
        def chat(self,*args):raise AssertionError('Publication must be prepared from the checked backend record')
    app.state.assistant_provider_factory=NoInference
    try:
        with engine.connect() as db:before=db.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),dict(site=ids['site']))
        for command,tool in [('Утверди предложение ','publication_approve'),('Опубликуй утверждённое предложение ','publication_publish')]:
            sent=client.post(B+f'/conversations/{chat}/messages',json=dict(content=command+proposal['proposal_id'],idempotency_key=str(uuid4())))
            assert sent.status_code==202
            view=client.get(B+'/conversations/'+chat).json();action=next(a for a in view['actions'] if a['tool_name']==tool)
            with engine.connect() as db:assert db.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),dict(site=ids['site']))==before
            response=confirm(client,action);assert response.status_code==200 and response.json()['status']=='succeeded',response.text
            assert confirm(client,action).json()['status']=='succeeded'
        with engine.connect() as db:assert db.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),dict(site=ids['site']))>before
    finally:
        del app.state.assistant_provider_factory
        with engine.begin() as db:
            for table in ('assistant_turn_attachments','assistant_actions','assistant_attachments','assistant_turns'):
                db.execute(text('DELETE FROM '+table+' WHERE conversation_id=:id'),dict(id=chat))
            db.execute(text('DELETE FROM assistant_conversations WHERE conversation_id=:id'),dict(id=chat))

def test_workforce_sql_count_does_not_grow_per_employee(managed):
    from sqlalchemy import event
    from tests.backend.test_draft_plans import worker
    engine,_,admin,_,_=managed
    def measure():
        statements=[]
        def capture(conn,cursor,statement,parameters,context,many):
            if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
        event.listen(engine,'before_cursor_execute',capture)
        try:response=admin.chief.get('/api/v1/maintenance/management/workforce')
        finally:event.remove(engine,'before_cursor_execute',capture)
        assert response.status_code==200,response.text
        return len(statements),response.json()
    baseline,_=measure()
    for index in range(20):worker(managed,f'WORKFORCE budget {index}')
    measured,payload=measure()
    assert len(payload['staff'])==22 and measured<=baseline+1 and measured<25
