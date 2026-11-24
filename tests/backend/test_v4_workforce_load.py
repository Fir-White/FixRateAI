from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
import json

from sqlalchemy import text

from tests.backend.test_assistant import B, assistant_case, thread
from tests.backend.test_assistant_tool_agent import send
from tests.backend.test_management import managed, join
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_v4_context_reads import v4, call


def test_daily_workforce_keeps_zero_unknown_and_unavailable_distinct(monkeypatch, assistant_case):
    engine, app, _, login, ids = assistant_case
    workers = [join(assistant_case) for _ in range(4)]
    _, engineer_email = join(assistant_case, 'engineer')
    day = date.today()+timedelta(days=5)
    def at(hour, minute=0):
        return datetime.combine(day, time(hour, minute), timezone.utc)

    with engine.begin() as db:
        db.execute(text("UPDATE sites SET timezone='UTC' WHERE site_id=:site"), ids)
        for index,(user,_) in enumerate(workers):
            if index != 3:
                db.execute(text("""INSERT INTO availability_slots(site_id,user_id,starts_at,ends_at,status)
                    VALUES (:site,:user,:starts,:ends,'available')"""),
                    dict(site=ids['site'],user=user,starts=at(9),ends=at(17)))
            if index==0:
                db.execute(text("""INSERT INTO availability_slots(site_id,user_id,starts_at,ends_at,status)
                    VALUES (:site,:user,:starts,:ends,'unavailable')"""),
                    dict(site=ids['site'],user=user,starts=at(9),ends=at(13)))
                continue
            start,end = {1:(at(13),at(13,30)),2:(at(11,45),at(12,30)),3:(None,None)}[index]
            order=uuid4()
            db.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,origin,status,
                required_people_snapshot,norm_hours_snapshot,planned_start_at,planned_end_at)
                VALUES (:order,:site,:system,'manual','assigned',1,1,:starts,:ends)"""),
                dict(ids,order=order,starts=start,ends=end))
            db.execute(text("""INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by,start_at,end_at)
                VALUES (:site,:order,:user,:chief,:starts,:ends)"""),
                dict(ids,order=order,user=user,starts=start,ends=end))

    args=dict(day=day.isoformat(),window_start='12:00',window_end='13:00')
    def validate(result):
        assert result['total']==4 and result['page_complete']
        by_id={row['executorId']: row for row in result['items']}
        assert set(by_id)=={user for user,_ in workers}
        assert [(by_id[user]['loadMinutes'],by_id[user]['windowAvailable']) for user,_ in workers] == [
            (0,False),(30,True),(45,False),(None,None)]
        assert result['qualificationChecked'] is False
        assert result['windowCounts'] == {'available':1, 'unavailable':2, 'unknown':1, 'complete':True}

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role']=='user':
                return call('read_workforce_load',**args)
            validate(json.loads(messages[-1]['content']))
            return dict(content='Загрузка проверена.')

    v4(monkeypatch, app, Provider)
    with closing(login(engineer_email)) as engineer, closing(login(workers[0][1])) as executor:
        route=B+'/workspace/workforce-load'
        response=engineer.get(route,params=args)
        assert response.status_code==200
        validate(response.json())
        assert engineer.get(route,params={**args,'window_end':'11:00'}).status_code==422
        assert executor.get(route,params=args).status_code==403
        assert send(engineer,thread(engineer),'Кто свободен в обед?')['turns'][-1]['answer']=='Загрузка проверена.'
