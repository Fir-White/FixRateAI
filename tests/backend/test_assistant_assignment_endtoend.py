"""Assignment is proposed by the agent and applied only by explicit confirmation."""
from contextlib import closing
from uuid import uuid4
import json
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime,login,assignment_search,ASSIGNMENT_TASK
from tests.backend.test_assignment_save import jobs
from tests.backend.test_assistant import B,thread,confirm

def test_confirmed_assistant_proposal_assigns_exact_validated_workers(jobs):
    engine,app,create=jobs;task=create()
    with engine.begin() as db:
        shared_before=db.execute(text('SELECT status,revision FROM work_orders WHERE work_order_id=:id'),dict(id=ASSIGNMENT_TASK)).one()
        # A unique label preserves the natural-language title choice while the
        # actual assignment uses its own disposable work order, not the seed
        # used later by the runtime role/preview regression.
        db.execute(text("UPDATE work_orders SET operation_snapshot=jsonb_set(operation_snapshot,'{label}',CAST(:label AS jsonb)) WHERE work_order_id=:id"),dict(id=task,label=json.dumps('Isolated assistant selection '+str(task))))
    with closing(login(app,'chief_engineer')) as client:
        _,window=assignment_search(client)
        preview=client.post(f'/api/v1/maintenance/tasks/{task}/assignment-preview',json=window).json()
        workers=preview['command']['executor_ids'];chat=thread(client)
        names=', '.join(worker['name'] for worker in preview['selectedWorkers'])
        with engine.begin() as db:
            title=db.scalar(text('SELECT operation_snapshot FROM work_orders WHERE work_order_id=:id'),dict(id=task))['label']
            db.execute(text("INSERT INTO assistant_turns(turn_id,conversation_id,request_key,content,answer,status,prompt_version,created_at) VALUES (:turn,:chat,:key,:content,:answer,'completed','TEST',now()-interval '1 minute')"),dict(turn=uuid4(),chat=chat,key=uuid4(),content='Назначь сотрудников '+names,answer='Укажите конкретное задание для назначения.'))
            before=db.scalar(text('SELECT count(*) FROM work_assignments WHERE work_order_id=:id'),dict(id=task))
        class Provider:
            def __init__(self):self.stage=0
            def chat(self,messages,schema,tokens):
                if schema.__name__=='ToolSelection':
                    payload=json.loads(messages[-1]['content'])
                    assert payload['question']==title
                    assert any(names in row['content'] for row in payload['context']['history'])
                    return schema(tools=[],goals=[dict(id='assign',title='Назначить выбранных сотрудников на выбранное задание',kind='change',tool='task_assign')])
                assert schema.__name__=='AgentStep'
                self.stage+=1
                if self.stage==1:
                    tool='assignment_prepare';args=dict(path=dict(task_id=str(task)),body=dict(executor_ids=workers))
                else:
                    observed=next(json.loads(m['content'].split('\n',1)[1]) for m in reversed(messages)
                                  if m['role']=='user' and m['content'].startswith('Результаты инструментов'))
                    value=next(row['result'] for row in observed if row['tool']=='assignment_prepare')
                    command=value['command'];assert set(command['executor_ids'])==set(workers)
                    body={key:command[key] for key in ('expected_revision','executor_ids','start_at','end_at')}
                    if command.get('crew_id'):body['crew_id']=command['crew_id']
                    tool='task_assign';args=dict(path=dict(task_id=str(task)),body={**body,'reason':'TEST ONLY selected workers'})
                return schema(answer='',calls=[dict(tool=tool,arguments_json=json.dumps(args),explanation='TEST ONLY semantic execution; server validates assignment')])
        app.state.assistant_provider_factory=Provider
        try:
            response=client.post(B+f'/conversations/{chat}/messages',json=dict(content=title,idempotency_key=str(uuid4())))
            assert response.status_code==202
            action=client.get(B+'/conversations/'+chat).json()['actions'][0]
            with engine.connect() as db:assert db.scalar(text('SELECT count(*) FROM work_assignments WHERE work_order_id=:id'),dict(id=task))==before
            result=confirm(client,action)
            assert result.status_code==200 and result.json()['status']=='succeeded',result.text
            with engine.connect() as db:
                actual={str(row) for row in db.scalars(text("SELECT user_id FROM work_assignments WHERE work_order_id=:id AND status NOT IN ('cancelled','declined')"),dict(id=task))}
                assert db.execute(text('SELECT status,revision FROM work_orders WHERE work_order_id=:id'),dict(id=ASSIGNMENT_TASK)).one()==shared_before
            assert actual==set(workers)
            assert confirm(client,action).json()['status']=='succeeded'
        finally:
            del app.state.assistant_provider_factory
            assert client.delete(B+'/conversations/'+chat).status_code==200
