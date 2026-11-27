"""Validate selection and readiness independently across order and access states."""
from datetime import timedelta
from itertools import product
import os

import pytest
from sqlalchemy import text

from tests.agent_reliability_lab.evals.oracle import OPEN, ledger
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import ZONE, lab
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import stored, turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


PROFILES = ('normal', 'equal-due', 'completed-earliest', 'cancelled-earliest', 'all-undated',
            'all-future', 'old-deadline-after-cutoff', 'older-unassigned')


def overdue_orders(data, worker, cutoff):
    assigned = {row['task'] for row in data['assignments'] if row['worker'] == worker and
                row['status'] not in ('cancelled', 'declined')}
    return sorted((row for row in data['work'].values() if row['status'] in OPEN and row['deadline'] and
                   row['deadline'] < cutoff and (worker is None or row['id'] in assigned)),
                  key=lambda row: (row['deadline'], row['id']))


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize(('role', 'profile'), tuple(product(('chief_engineer', 'executor'), PROFILES)))
def test_select_oldest_and_validate_readiness(lab, role, profile):
    fixture, now, historical, worker, data, _, clients = lab
    engine, _, _, _, ids = fixture
    actor = worker if role == 'executor' else None
    ranked = overdue_orders(data, actor, now)
    cutoff = now
    when = ''
    with engine.begin() as db:
        if profile == 'all-undated':
            db.execute(text('UPDATE work_orders SET regulatory_deadline_at=NULL WHERE site_id=:site'), ids)
        elif profile == 'all-future':
            db.execute(text('UPDATE work_orders SET regulatory_deadline_at=:deadline WHERE site_id=:site'),
                       dict(ids, deadline=now+timedelta(days=20)))
        elif profile == 'equal-due':
            other = next(row for row in data['work'].values() if row['snapshot'].get('title') == 'Сверить уставки защиты')
            db.execute(text('''UPDATE work_orders SET regulatory_deadline_at=:deadline,planned_start_at=NULL
                               WHERE work_order_id IN (:winner,:other)'''),
                       dict(winner=ranked[0]['id'], other=other['id'], deadline=now-timedelta(days=30)))
        elif profile in ('completed-earliest', 'cancelled-earliest'):
            state = profile.split('-')[0]
            db.execute(text('''UPDATE work_orders SET regulatory_deadline_at=:deadline,planned_start_at=NULL
                               WHERE site_id=:site AND status=:state'''),
                       dict(ids, state=state, deadline=now-timedelta(days=40)))
        elif profile == 'older-unassigned':
            db.execute(text('DELETE FROM work_assignments WHERE work_order_id=:task'), {'task': ranked[0]['id']})
        elif profile == 'old-deadline-after-cutoff':
            cutoff = now-timedelta(days=20)
            day = cutoff.astimezone(ZONE).date()
            cutoff = cutoff.astimezone(ZONE).replace(hour=0, minute=0, second=0, microsecond=0)+timedelta(days=1)
            when = f' по состоянию на {day}'
    data = ledger(engine, ids['site'])
    expected = overdue_orders(data, actor, cutoff)
    before = checksums(fixture)
    result, actions, _ = turn(clients[role], 'Самостоятельно определи незавершённое задание с самой ранней '
                              f'нарушенной нормативной датой{when}. При равенстве выбери наименьший UUID. '
                              'Проверь готовность к приёмке: чек-лист, отчёт и фото. Укажи UUID, препятствия и источники. Ничего не изменяй.')
    assert result['status'] == 'completed' and result['execution_engine'] == 'v3' and not actions, result
    state = stored(fixture, result['turn_id'])
    assert state, result['answer']
    aggregate = next(item['result'] for item in state['evidence'] if item.get('output_type') == 'aggregate')
    assert checksums(fixture) == before
    assert [row['id'] for row in aggregate['groups']] == [row['id'] for row in expected[:1]]
    if not expected:
        assert not any(item['tool'] == 'task_acceptance_evidence' for item in state['evidence'])
        return
    receipt = next(item['result'] for item in state['evidence'] if item['tool'] == 'task_acceptance_evidence')
    assert receipt['task_id'] == expected[0]['id'] and receipt['submission_ready'] is False
    assert expected[0]['id'] in result['answer'] and 'отчёт' in result['answer'].casefold()
    assert any(item['tool'] == 'task_read' for item in state['evidence'])
