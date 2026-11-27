"""Exercise an authorized action through the chat and confirmation HTTP APIs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
import os

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app.main import create_app
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab
from tests.backend.test_assistant import B, assistant_case
from tests.backend.test_assistant_architecture_v2 import turn
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


def order(engine, identity):
    with engine.connect() as db:
        return db.execute(text('SELECT status,revision FROM work_orders WHERE work_order_id=:id'),
                          {'id': identity}).one()


def event_counts(engine, identity):
    with engine.connect() as db:
        return dict(db.execute(text('''SELECT action,count(*) FROM audit_events WHERE entity_id=:id
                                       GROUP BY action'''), {'id': identity}).all())


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('decision', ['reject', 'confirm', 'confirm-after-restart', 'concurrent-confirm', 'expired'])
def test_real_action_lifecycle(lab, decision):
    fixture, _, _, _, data, _, sessions = lab
    engine, app, *_ = fixture
    chief = sessions['chief_engineer']
    identity = next(row['id'] for row in data['work'].values()
                    if row['snapshot'].get('title') == 'Проверить резервную индикацию')
    before = order(engine, identity)
    reply, proposals, _ = turn(chief, f'Отмени задание {identity}, причина: сняли работу из тестового графика.')
    assert reply['execution_engine'] == 'v3' and reply['workflow']['outcome'] == 'awaiting_confirmation', reply
    proposal, = proposals
    assert order(engine, identity) == before
    identity_action = proposal['action_id']
    assert event_counts(engine, identity_action) == {'proposed': 1}
    target = f'{B}/actions/{identity_action}'
    payload = {'confirmed': True, 'payload_sha256': proposal['payload_sha256']}

    if decision == 'reject':
        rejected = chief.post(f'{target}/reject')
        assert rejected.status_code == 200 and rejected.json()['status'] == 'rejected'
        repeated = chief.post(f'{target}/confirm', json=payload)
        assert repeated.status_code == 200 and repeated.json()['status'] == 'rejected'
        assert order(engine, identity) == before
        assert event_counts(engine, identity_action) == {'proposed': 1, 'rejected': 1}
        return
    if decision == 'expired':
        with engine.begin() as db:
            db.execute(text("UPDATE assistant_actions SET expires_at=now()-interval '1 second' WHERE action_id=:id"),
                       {'id': identity_action})
        response = chief.post(f'{target}/confirm', json=payload)
        assert response.status_code == 409
        assert order(engine, identity) == before and event_counts(engine, identity_action) == {'proposed': 1}
        return

    def approve(client):
        return client.post(f'{target}/confirm', json=payload)

    session_args = dict(cookies=chief.cookies, headers={'X-CSRF-Token': chief.headers['X-CSRF-Token']})
    with ExitStack() as clients:
        if decision == 'confirm-after-restart':
            client = clients.enter_context(TestClient(create_app(engine), **session_args))
            confirmations = [approve(client)]
        elif decision == 'concurrent-confirm':
            first = clients.enter_context(closing(TestClient(app, **session_args)))
            second = clients.enter_context(closing(TestClient(app, **session_args)))
            with ThreadPoolExecutor(max_workers=2) as pool:
                confirmations = list(pool.map(approve, [first, second]))
        else:
            confirmations = [approve(chief)]
    assert all(response.status_code == 200 for response in confirmations)
    assert {response.json()['status'] for response in confirmations} <= {'executing', 'succeeded'}
    replay = approve(chief)
    assert replay.status_code == 200 and replay.json()['status'] == 'succeeded'
    assert order(engine, identity) == ('cancelled', before.revision + 1)
    assert event_counts(engine, identity_action) == {'proposed': 1, 'confirmed': 1, 'succeeded': 1}
