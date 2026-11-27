"""Actual PostgreSQL/HTTP evidence for atomic equipment snapshots."""
import asyncio
from uuid import uuid4
from sqlalchemy import event,text
from app.assistant import orchestrator,read_transport
from app.assistant.tools import TOOLS
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed,join
from tests.backend.test_assistant import assistant_case

BASE='/api/v1/assistant/workspace/equipment'
FIELDS={'equipment_id','site_id','system_id','parent_equipment_id','equipment_type_id','asset_code','name','serial_number','commissioned_on','location','properties','status','revision'}

def assets(case,count=31):
    _,_,client,_,ids=case;result=[]
    for index in range(count):
        response=client.post('/api/v1/maintenance/equipment',json=dict(system_id=str(ids['system']),asset_code=f'SNAPSHOT-{index:03}',name=f'Asset {index}',properties={'ordinal':index}))
        assert response.status_code==201,response.text
        result.append(response.json())
    return result

def read(client,**query):
    response=client.get(BASE,params=query);assert response.status_code==200,response.text
    return response.json()

def test_stable_snapshot_retains_full_31_rows_and_exact_projection(assistant_case):
    _,_,client,_,_=assistant_case;expected=assets(assistant_case)
    first=read(client);last=read(client,offset=25)
    assert first['total']==last['total']==31 and len(first['items'])==25 and len(last['items'])==6
    assert first['snapshot_id']==last['snapshot_id'] and len(first['snapshot_id'])==64
    rows=first['items']+last['items']
    assert rows==expected and len({row['equipment_id'] for row in rows})==31
    assert all(set(row)==FIELDS for row in rows)
    assert read(client,offset=100)['snapshot_id']==first['snapshot_id']

def test_mutation_between_pages_same_total_is_detected_by_real_orchestrator(assistant_case,monkeypatch):
    _,app,client,_,_=assistant_case;items=assets(assistant_case);before=read(client);calls=[]
    async def actual_http(app,tool,args,headers):
        data=read(client,**args.get('query',{}));calls.append(data)
        if len(calls)==1:
            response=client.patch('/api/v1/maintenance/equipment/'+items[-1]['equipment_id'],json=dict(expected_revision=1,name='Changed between pages'))
            assert response.status_code==200,response.text
        return data
    monkeypatch.setattr(read_transport,'invoke',actual_http)
    tool=next(tool for tool in TOOLS if tool.name=='equipment_find');trace=[]
    _,result=asyncio.run(orchestrator._read_pages(app,tool,{}, {},full=True,check=lambda:None,trace=trace))
    assert len(calls)==2 and calls[0]['total']==calls[1]['total']==31
    assert calls[0]['snapshot_id']==before['snapshot_id']!=calls[1]['snapshot_id']
    assert result['complete'] is False and 'snapshot_changed' in result['pagination']['limitations']
    assert len(result['items'])==25

def test_snapshot_binds_actor_filters_and_all_projected_values(assistant_case):
    _,_,client,_,_=assistant_case;items=assets(assistant_case,2);baseline=read(client)
    assert read(client)['snapshot_id']==baseline['snapshot_id']
    assert read(client,q='Asset')['snapshot_id']!=baseline['snapshot_id']
    assert read(client,asset_code=items[0]['asset_code'])['snapshot_id']!=baseline['snapshot_id']
    assert read(client.chief)['snapshot_id']!=baseline['snapshot_id']
    changed=client.patch('/api/v1/maintenance/equipment/'+items[0]['equipment_id'],json=dict(expected_revision=1,properties={'ordinal':999}))
    assert changed.status_code==200,changed.text
    assert read(client)['snapshot_id']!=baseline['snapshot_id']
    empty=read(client,asset_code='ABSENT')
    assert empty['items']==[] and empty['total']==0 and len(empty['snapshot_id'])==64

def test_equipment_snapshot_uses_one_statement_independent_of_rows(assistant_case):
    engine,_,client,_,ids=assistant_case;assets(assistant_case,1)
    def capture():
        statements=[]
        def before(conn,cursor,statement,parameters,context,many):
            if 'authorized_equipment AS MATERIALIZED' in statement:statements.append(statement)
        event.listen(engine,'before_cursor_execute',before)
        try:result=read(client)
        finally:event.remove(engine,'before_cursor_execute',before)
        assert len(statements)==1 and 'equipment_summary AS' in statements[0] and 'equipment_page AS' in statements[0]
        return result
    first=capture()
    for index in range(30):
        response=client.post('/api/v1/maintenance/equipment',json=dict(system_id=str(ids['system']),asset_code=f'EXTRA-{index}',name='Extra'))
        assert response.status_code==201,response.text
    last=capture();assert first['total']==1 and last['total']==31

def test_executor_snapshot_follows_assignment_visibility(assistant_case):
    engine,_,client,login,ids=assistant_case;items=assets(assistant_case,2)
    user,email=join(assistant_case);executor=login(email)
    try:
        assert read(executor)['items']==[]
        task=uuid4()
        with engine.begin() as db:
            db.execute(text("INSERT INTO work_orders(work_order_id,site_id,system_id,origin,status,required_people_snapshot,norm_hours_snapshot,operation_snapshot) VALUES (:task,:site,:system,'manual','draft',1,1,CAST(:snapshot AS jsonb))"),dict(task=task,site=ids['site'],system=ids['system'],snapshot='{}'))
            db.execute(text('INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id) VALUES (:site,:system,:task,:asset)'),dict(site=ids['site'],system=ids['system'],task=task,asset=items[0]['equipment_id']))
            db.execute(text('INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by) VALUES (:site,:task,:user,:admin)'),dict(site=ids['site'],task=task,user=user,admin=ids['user']))
        visible=read(executor);assert visible['total']==1 and visible['items'][0]['equipment_id']==items[0]['equipment_id']
        assert read(executor,asset_code=items[1]['asset_code'])['total']==0
        with engine.begin() as db:db.execute(text("UPDATE work_assignments SET status='cancelled' WHERE site_id=:site AND user_id=:user"),dict(site=ids['site'],user=user))
        revoked=read(executor);assert revoked['items']==[] and revoked['snapshot_id']!=visible['snapshot_id']
    finally:executor.close()

def test_exact_asset_filter_keeps_percent_underscore_literal(assistant_case):
    _,_,client,_,_=assistant_case;items=assets(assistant_case,2)
    for item,code in zip(items,('PUMP%_LITERAL','PUMPxxLITERAL')):
        response=client.patch('/api/v1/maintenance/equipment/'+item['equipment_id'],json=dict(expected_revision=1,asset_code=code))
        assert response.status_code==200,response.text
    result=read(client,asset_code='PUMP%_LITERAL')
    assert result['total']==1 and result['items'][0]['equipment_id']==items[0]['equipment_id']
