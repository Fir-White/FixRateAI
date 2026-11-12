"""Presentation task identity must reach HTTP views without repairing old history."""
from contextlib import closing
from datetime import datetime, timezone
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import make_engine
from app.main import create_app
from app.manage import migrate, seed_demo
from app.integration.presentation import identity, seed_presentation
from tests.backend.test_presentation import sign_in
from tests.backend.test_runtime_integration import PREFIX, runtime


@pytest.fixture
def archived_presentation(runtime, tmp_path, monkeypatch):
    """A historical seed cannot share today's idempotently preserved rules."""
    parent, _ = runtime
    assert parent.url.database.startswith('fixrate_test_')
    name = 'fixrate_test_archived_presentation_' + uuid4().hex
    with parent.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.exec_driver_sql('CREATE DATABASE ' + name)
    engine = make_engine(parent.url.set(database=name))
    try:
        migrate(engine)
        seed_demo(engine, os.environ['FIXRATE_TEST_PASSWORD'])
        monkeypatch.setenv('PHOTO_STORAGE_ROOT', str(tmp_path/'photos'))
        monkeypatch.setenv('MAINTENANCE_SCHEDULER', 'false')
        with TestClient(create_app(engine)) as client:
            yield engine, client.app
    finally:
        engine.dispose()
        with parent.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.exec_driver_sql('DROP DATABASE ' + name)


def test_new_presentation_tasks_have_exact_equipment_and_rerun_preserves_missing_history(archived_presentation):
    engine, app = archived_presentation
    # A fixed date makes the archived IDs reproducible and keeps the fixture isolated.
    moment = datetime(2026, 11, 6, 7, tzinfo=timezone.utc)
    args = dict(as_of=moment, storage=app.state.settings.photo_storage_root)
    seed_presentation(engine, os.environ['FIXRATE_TEST_PASSWORD'], **args)
    targets = {
        'month-2026-11-1.1-2026-11-06': 'point',
        'month-2026-11-1.2-2026-11-06': 'point',
        'month-2026-11-1.3-2026-11-05': 'controller',
        'month-2026-11-1.5-2026-11-06': 'gauge',
        'history-1.1-0': 'point',
    }
    with closing(sign_in(app, 'engineer@fixrate.local')) as engineer:
        response = engineer.get(PREFIX + '/ui/tasks')
        assert response.status_code == 200
        listed = {row['id']: row for row in response.json()}
        for key, equipment in targets.items():
            task_id, equipment_id = str(identity(key)), str(identity(equipment))
            detail = engineer.get(PREFIX + '/ui/tasks/' + task_id)
            assert detail.status_code == 200
            assert listed[task_id]['equipmentId'] == equipment_id
            assert detail.json()['task']['equipmentId'] == equipment_id
            assert listed[task_id]['equipmentName'] != 'Не указано'
        context = engineer.get(PREFIX + '/ui/tasks/' + str(identity(next(iter(targets)))) + '/assignment-context')
        assert context.status_code == 200
        assert context.json().get('code') != 'EQUIPMENT_CONTEXT_INVALID'

    with closing(sign_in(app, 'technician@fixrate.local')) as executor:
        task_id = str(identity('month-2026-11-1.2-2026-11-06'))
        detail = executor.get(PREFIX + '/ui/tasks/' + task_id)
        assert detail.status_code == 200
        assert detail.json()['task']['equipmentId'] == str(identity('point'))
        passport = executor.get(PREFIX + '/ui/equipment/' + str(identity('point')))
        assert passport.status_code == 200
        # The new relation does not grant access to another worker's task.
        other = executor.get(PREFIX + '/ui/tasks/' + str(identity('month-2026-11-1.1-2026-11-06')))
        assert other.status_code == 404

    with engine.begin() as connection:
        selected = connection.execute(text('SELECT work_order_id, revision, operation_snapshot FROM work_orders WHERE work_order_id=:id'),
            dict(id=identity('month-2026-11-1.3-2026-11-05'))).mappings().one()
        connection.execute(text('DELETE FROM work_order_equipment WHERE work_order_id=:id'), dict(id=selected['work_order_id']))
    seed_presentation(engine, os.environ['FIXRATE_TEST_PASSWORD'], **args)
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM work_order_equipment WHERE work_order_id=:id'), dict(id=selected['work_order_id'])) == 0
        preserved = connection.execute(text('SELECT work_order_id, revision, operation_snapshot FROM work_orders WHERE work_order_id=:id'), dict(id=selected['work_order_id'])).mappings().one()
        assert preserved == selected
    with closing(sign_in(app, 'engineer@fixrate.local')) as engineer:
        detail = engineer.get(PREFIX + '/ui/tasks/' + str(selected['work_order_id']))
        assert detail.status_code == 200
        assert detail.json()['task']['equipmentId'] is None
        context = engineer.get(PREFIX + '/ui/tasks/' + str(selected['work_order_id']) + '/assignment-context')
        assert context.status_code == 200
        assert context.json()['code'] == 'EQUIPMENT_CONTEXT_INVALID'
