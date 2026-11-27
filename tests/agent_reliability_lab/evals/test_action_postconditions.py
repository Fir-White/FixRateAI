"""Authorization and revision remain current at an ordinary approval boundary."""
import os

import pytest
from sqlalchemy import text

from tests.agent_reliability_lab.evals.test_action_lifecycle import event_counts, order
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab
from tests.backend.test_assistant import B, assistant_case
from tests.backend.test_assistant_architecture_v2 import turn
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import PREFIX, runtime


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('change', ['role', 'order'])
def test_approval_rechecks_postconditions(lab, change):
    fixture, _, _, _, ledger, _, clients = lab
    engine, _, admin, _, ids = fixture
    chief = clients['chief_engineer']
    task = next(row['id'] for row in ledger['work'].values()
                if row['snapshot'].get('title') == 'Проверить резервную индикацию')
    before = order(engine, task)
    turn_result, actions, _ = turn(chief, f'Отмени задание {task}, причина: сняли из испытательного графика.')
    assert turn_result['execution_engine'] == 'v3' and turn_result['workflow']['outcome'] == 'awaiting_confirmation'
    proposal, = actions
    identity = proposal['action_id']
    assert order(engine, task) == before

    if change == 'role':
        with engine.connect() as db:
            revision = db.scalar(text('SELECT revision FROM site_memberships WHERE site_id=:site AND user_id=:chief'), ids)
        edit = admin.put(f'{PREFIX}/management/staff/{ids["chief"]}',
                         json={'expected_revision': revision, 'role': 'engineer', 'is_active': True})
        assert edit.status_code == 200, edit.text
    else:
        update = chief.post(f'{PREFIX}/tasks/{task}/cancel',
                            json={'expected_revision': before.revision, 'reason': 'Отменено из штатной карточки'})
        assert update.status_code == 200, update.text

    result = chief.post(f'{B}/actions/{identity}/confirm',
                        json={'confirmed': True, 'payload_sha256': proposal['payload_sha256']})
    audit = event_counts(engine, identity)
    assert 'confirmed' not in audit and 'succeeded' not in audit
    if change == 'role':
        assert result.status_code in (401, 403, 404), result.text
        assert order(engine, task) == before
    else:
        assert result.status_code == 409 and audit.get('stale') == 1, result.text
        assert order(engine, task) == ('cancelled', before.revision + 1)
