"""Actual installed Ollama writes: goal state, SQL, confirmation and replay."""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime,TASK
from tests.backend.test_management import managed,join
from tests.backend.test_assistant import assistant_case,thread,confirm,B
from tests.backend.test_agent_redteam_live import live_case
from tests.backend.test_assistant_orchestrator_live import episode,record,send

pytestmark=pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE')!='1',reason='Installed local Ollama on disposable PostgreSQL only')
P='/api/v1/maintenance'


def saved(case,operation,identity):
    with case['engine'].connect() as db:
        if operation=='staff_edit':
            return db.scalar(text('SELECT to_jsonb(t) FROM site_memberships t WHERE site_id=:site AND user_id=:id'),dict(site=case['ids']['site'],id=identity))
        return db.scalar(text('SELECT to_jsonb(t) FROM work_orders t WHERE work_order_id=:id'),dict(id=identity))


def run_write(case,operation,identity,question,oracle,request):
    client=case['client'];profile=client.get(P+'/users/me').json();before=saved(case,operation,identity)
    chat=thread(client)
    with episode(case,'WRITE-'+operation.upper()+'-'+profile['role'].upper()) as outcome:
        outcome.update(kind='positive-confirmed-write',operation=operation,acceptance_operation=operation,
            actor_role=profile['role'],actor_id=profile['userId'],test_node=request.node.nodeid,
            fixture_version='orchestrator-positive-writes-v1',fixture_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        view,turn=send(case,chat,question);record(outcome,view,turn,question)
        assert turn['status']=='completed' and case['calls']
        assert len(view['actions'])==1,view
        action=view['actions'][0]
        assert action['tool_name']==operation
        assert saved(case,operation,identity)==before,'No business write before human confirmation'
        assert any(goal['status']=='awaiting_confirmation' for goal in turn['workflow']['goals'])
        applied=confirm(client,action)
        assert applied.status_code==200 and applied.json()['status']=='succeeded',applied.text
        assert applied.json()['result']['verification']['status']=='confirmed',applied.json()
        after=saved(case,operation,identity);oracle(before,after)
        replay=confirm(client,action)
        assert replay.status_code==200 and replay.json()['status']=='succeeded'
        assert saved(case,operation,identity)==after,'Confirmation replay duplicated the write'
        resumed=client.post(B+f'/conversations/{chat}/messages',json=dict(content='Continue the saved task and verify its outcome.',
            idempotency_key=str(uuid4()),resume_turn_id=turn['turn_id']))
        assert resumed.status_code==202,resumed.text
        reopened=client.get(B+'/conversations/'+chat).json();final=reopened['turns'][-1]
        record(outcome,reopened,final,'Explicit resume after confirmed write')
        assert final['status']=='completed' and final['workflow']['outcome']=='completed',final
        assert all(goal['status']=='completed' for goal in final['workflow']['goals']),final
        assert len(reopened['actions'])==1 and saved(case,operation,identity)==after
        outcome.update(workflow_outcome=final['workflow']['outcome'],unfinished_goals=[],
            acceptance=dict(operation=operation,actor_role=profile['role'],goal_achieved=True,data_verified=True,
                no_unconfirmed_writes=True,provider='ollama',mocked=False,whole_request_completed=True))


def test_admin_staff_date_change_preserves_other_fields_and_finishes_saved_goal(live_case,request):
    c=live_case;identity,_=join((c['engine'],c['app'],c['admin'],c['login'],c['ids']))
    def oracle(before,after):
        assert after['employed_until']=='2028-04-05' and after['revision']==before['revision']+1
        omitted={'employed_until','revision','updated_at'}
        assert {k:v for k,v in after.items() if k not in omitted}=={k:v for k,v in before.items() if k not in omitted}
        fresh=c['admin'].get('/api/v1/assistant/workspace/staff/'+str(identity))
        assert fresh.status_code==200 and fresh.json()['employed_until']=='2028-04-05'
    run_write(dict(c,client=c['admin']),'staff_edit',str(identity),
        f'Change only the employment end date of employee user_id={identity} to 2028-04-05. Keep the role, active membership and all other fields unchanged. Prepare one proposal for my confirmation.',oracle,request)


def test_executor_start_creates_one_report_and_finishes_saved_goal(live_case,request):
    c=live_case;identity,email=join((c['engine'],c['app'],c['admin'],c['login'],c['ids']))
    order=uuid4();admin=c['admin'].get(P+'/users/me').json()['userId']
    with c['engine'].begin() as db:
        snapshot=db.scalar(text('SELECT operation_snapshot FROM work_orders WHERE work_order_id=:id'),dict(id=TASK))
        db.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,origin,status,required_people_snapshot,norm_hours_snapshot,operation_snapshot)
            VALUES (:id,:site,:system,'manual','assigned',1,1,CAST(:snapshot AS jsonb))"""),dict(id=order,site=c['ids']['site'],system=c['ids']['system'],snapshot=json.dumps(snapshot)))
        db.execute(text('INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id) VALUES (:site,:system,:task,:unit)'),
            dict(site=c['ids']['site'],system=c['ids']['system'],task=order,unit=c['equipment']['equipment_id']))
        db.execute(text('INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by) VALUES (:site,:task,:user,:actor)'),
            dict(site=c['ids']['site'],task=order,user=identity,actor=admin))
    client=c['login'](email)
    try:
        before=client.get(P+'/ui/tasks/'+str(order))
        assert before.status_code==200 and before.json()['task']['state']=='assigned'
        def oracle(previous,after):
            assert after['status']=='in_progress' and after['revision']==previous['revision']+1
            fresh=client.get(P+'/ui/tasks/'+str(order))
            assert fresh.status_code==200 and fresh.json()['task']['state']=='in_progress'
            assert fresh.json()['execution']['id'] and fresh.json()['execution']['state']=='draft'
            with c['engine'].connect() as db:
                assert db.scalar(text('SELECT count(*) FROM work_reports WHERE work_order_id=:id'),dict(id=order))==1
                assert str(db.scalar(text('SELECT submitted_by FROM work_reports WHERE work_order_id=:id'),dict(id=order)))==str(identity)
            assert after['started_at'] and previous['started_at'] is None
            omitted={'status','revision','updated_at','started_at'}
            assert {k:v for k,v in after.items() if k not in omitted}=={k:v for k,v in previous.items() if k not in omitted}
        run_write(dict(c,client=client),'task_start',str(order),
            f'Start only my assigned task task_id={order}. Prepare one action for my confirmation. Do not submit or accept a report.',oracle,request)
    finally:client.close()
