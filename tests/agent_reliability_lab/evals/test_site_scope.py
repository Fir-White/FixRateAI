"""Switch real authorized objects while the same equipment code exists in both."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab
from tests.backend.test_assistant import B, assistant_case
from tests.backend.test_assistant_architecture_v2 import turn
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


def use_site(client, site, role):
    response = client.post('/api/v1/auth/site', json={'site_id': str(site)})
    assert response.status_code == 200, response.text
    assert response.json()['profile']['role'] == role
    client.headers['X-CSRF-Token'] = response.json()['csrfToken']


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('role', ['director', 'chief_engineer', 'engineer', 'executor'])
def test_same_code_resolves_only_in_current_site(lab, role):
    fixture, _, _, _, data, _, clients = lab
    engine, _, _, _, ids = fixture
    client = clients[role]
    other, system, asset, task = map(str, (uuid4(), uuid4(), uuid4(), uuid4()))
    old = data['equipment']['КА-21']
    with engine.begin() as db:
        if role == 'executor':
            user = next(row['worker'] for row in data['assignments']
                        if data['work'][row['task']]['snapshot'].get('title') == 'Сверить уставки защиты')
        else:
            user = db.scalar(text('SELECT user_id FROM site_memberships WHERE site_id=:site AND role=:role'),
                             dict(ids, role=role))
        shared = {'site': other, 'user': user, 'system': system, 'type': ids['type'], 'id': asset, 'role': role, 'task': task}
        db.execute(text("INSERT INTO sites(site_id,name) VALUES (:site,'Резервная площадка E2E')"), shared)
        db.execute(text('INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:user,:role)'), shared)
        db.execute(text("INSERT INTO engineering_systems(system_id,site_id,code,name) VALUES (:system,:site,'B','Система B')"), shared)
        db.execute(text('''INSERT INTO equipment(equipment_id,site_id,system_id,equipment_type_id,asset_code,name)
                           VALUES (:id,:site,:system,:type,'КА-21','Шкаф резервной площадки')'''), shared)
        if role == 'executor':
            db.execute(text('''INSERT INTO work_orders(work_order_id,site_id,system_id,origin,status,
                               required_people_snapshot,norm_hours_snapshot,operation_snapshot)
                               VALUES (:task,:site,:system,'manual','assigned',1,1,'{}')'''), shared)
            db.execute(text('''INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id)
                               VALUES (:site,:system,:task,:id)'''), shared)
            db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
                               VALUES (:site,:task,:user,:user)'''), shared)
    try:
        first, actions, chat = turn(client, 'Открой карточку КА-21.')
        assert first['execution_engine'] == 'v3' and first['workflow']['outcome'] == 'completed' and not actions
        assert old['id'] in first['answer'] and asset not in first['answer']
        use_site(client, other, role)
        assert client.get(f'{B}/conversations/{chat}').status_code == 404
        second, actions, other_chat = turn(client, 'Открой карточку КА-21.')
        assert second['execution_engine'] == 'v3' and second['workflow']['outcome'] == 'completed' and not actions
        assert asset in second['answer'] and 'Шкаф резервной площадки' in second['answer']
        assert old['id'] not in second['answer'] and old['name'] not in second['answer']
        assert client.delete(f'{B}/conversations/{other_chat}').status_code == 200
        use_site(client, ids['site'], role)
        restored = client.get(f'{B}/conversations/{chat}')
        assert restored.status_code == 200 and restored.json()['turns'][0]['turn_id'] == first['turn_id']
    finally:
        with engine.begin() as db:
            for table in ('assistant_conversations', 'audit_events', 'fixrate_sessions', 'work_assignments',
                          'work_order_equipment', 'work_orders', 'equipment', 'engineering_systems', 'site_memberships', 'sites'):
                db.execute(text(f'DELETE FROM {table} WHERE site_id=:site'), shared)
