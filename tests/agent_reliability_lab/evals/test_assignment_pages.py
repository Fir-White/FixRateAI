"""Population tests at the response and retained-snapshot page boundaries."""
from datetime import timedelta
import json
from math import ceil
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.agent_reliability_lab.evals.oracle import UUID
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('total', [19, 20, 21, 40, 41, 101])
def test_assignment_pages_preserve_population_and_order(lab, total):
    fixture, now, _, worker, data, _, clients = lab
    engine, _, _, _, ids = fixture
    chief = clients['chief_engineer']
    heat = data['equipment']['ИТП-21']['id']
    rows = [dict(ids, task=uuid4(), equipment=heat, worker=worker,
                 deadline=now+timedelta(days=10+index), start=now+timedelta(days=8, hours=index),
                 finish=now+timedelta(days=8, hours=index, minutes=30),
                 snapshot=json.dumps({'title': f'Сверка секции {index}'})) for index in range(total-3)]
    with engine.begin() as db:
        db.execute(text('''INSERT INTO work_orders(work_order_id,site_id,system_id,origin,status,
                           required_people_snapshot,norm_hours_snapshot,operation_snapshot,regulatory_deadline_at)
                           VALUES (:task,:site,:system,'manual','assigned',1,1,CAST(:snapshot AS jsonb),:deadline)'''), rows)
        db.execute(text('''INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id)
                           VALUES (:site,:system,:task,:equipment)'''), rows)
        db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by,start_at,end_at)
                           VALUES (:site,:task,:worker,:chief,:start,:finish)'''), rows)
        # Historical records must not add a duplicate task or move it earlier.
        db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by,status)
                           VALUES (:site,:task,:worker,:chief,'declined')'''), rows[:2])
        expected = list(db.scalars(text('''SELECT w.work_order_id::text FROM work_assignments a
             JOIN work_orders w USING(site_id,work_order_id)
             WHERE a.site_id=:site AND a.user_id=:worker AND a.status NOT IN ('cancelled','declined')
             AND w.status NOT IN ('completed','cancelled')
             ORDER BY a.start_at NULLS LAST,w.work_order_id'''), dict(ids, worker=worker)))
    assert len(expected) == total
    before = checksums(fixture)
    first, actions, chat = turn(chief, 'Найди исполнителя с наибольшим количеством назначенных незавершённых заданий. '
                                'Перечисли все его незавершённые задания с нормативными сроками постранично. Ничего не меняй.')
    assert first['execution_engine'] == 'v3' and not actions
    retained = min(total, 100)
    assert first['workflow']['outcome'] == ('completed' if retained == total else 'partial'), first
    pages = ceil(retained/20)
    for page in range(1, pages+1):
        result = first
        if page > 1:
            result, actions, _ = turn(chief, f'Покажи страницу {page} назначений.', chat=chat)
            assert not actions and result['execution_engine'] == 'v3'
        start, finish = (page-1)*20, min(page*20, retained)
        found = [identity for identity in UUID.findall(result['answer']) if identity in expected]
        assert found == expected[start:finish], result['answer']
        assert f'{start+1}–{finish} из {total}' in result['answer']
    if retained < total:
        assert 'Полный перечень не подтверждён' in result['answer']
    after, actions, _ = turn(chief, f'Покажи страницу {pages+1} назначений.', chat=chat)
    assert not actions and 'отсутствует в сохранённом снимке' in after['answer']
    assert checksums(fixture) == before
