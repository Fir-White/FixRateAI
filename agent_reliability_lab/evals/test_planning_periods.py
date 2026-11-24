"""Planning comparisons with unequal, empty and overlapping actual windows."""
from datetime import timedelta
from itertools import product
import os
import re

import pytest
from sqlalchemy import text

from agent_reliability_lab.evals.oracle import OPEN
from agent_reliability_lab.evals.test_agent_v3_e2e import ZONE, lab
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import stored, turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


WINDOWS = {
    'historical-vs-now': ((-15, -8), (-3, 2)),
    'overlap': ((-10, -2), (-7, 0)),
    'empty-vs-planned': ((-30, -20), (0, 2)),
    'planned-vs-empty': ((0, 2), (4, 7)),
    'adjacent-shared-date': ((-10, -7), (-7, -5)),
    'same': ((-8, 0), (-8, 0)),
}
CASES = tuple(product(('chief_engineer', 'executor'), WINDOWS))


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize(('role', 'profile'), CASES)
def test_planning_period_counts(lab, role, profile):
    fixture, now, _, worker, _, _, clients = lab
    engine, _, _, _, ids = fixture
    day = now.astimezone(ZONE).date()
    windows = [(day+timedelta(days=start), day+timedelta(days=end)) for start, end in WINDOWS[profile]]
    with engine.connect() as db:
        rows = db.execute(text('''SELECT task.status,task.planned_start_at,task.regulatory_deadline_at,
                  EXISTS(SELECT 1 FROM work_assignments a WHERE a.site_id=task.site_id AND a.work_order_id=task.work_order_id
                         AND a.user_id=:worker AND a.status NOT IN ('cancelled','declined')) AS assigned_to_me
                  FROM work_orders task WHERE task.site_id=:site AND task.planned_start_at IS NOT NULL
                  AND task.status<>'cancelled' '''), dict(ids, worker=worker)).all()
    expected = []
    for start, end in windows:
        selected = [row for row in rows if start <= row.planned_start_at.astimezone(ZONE).date() <= end
                    and (role != 'executor' or row.assigned_to_me)]
        unfinished = [row for row in selected if row.status in OPEN]
        expected.append((len(selected), len(unfinished), sum(row.regulatory_deadline_at is not None
                         and row.regulatory_deadline_at < now for row in unfinished)))
    first, second = windows
    before = checksums(fixture)
    result, actions, _ = turn(clients[role], f'Сравни периоды планирования с {first[0]} по {first[1]} и '
                               f'с {second[0]} по {second[1]} по числу запланированных, незавершённых и просроченных работ. '
                               'Укажи изменение числа запланированных работ. Ничего не изменяй.')
    assert result['status'] == 'completed' and result['execution_engine'] == 'v3' and not actions
    state = stored(fixture, result['turn_id'])
    if role == 'executor' or first == second:
        assert state and state['outcome'] in ('blocked', 'partial'), result['answer']
        assert not any(item['tool'] == 'work_order_analytics' and item['status'] in ('FOUND', 'EMPTY')
                       for item in state['evidence'])
        assert checksums(fixture) == before
        return
    assert state and state['outcome'] == 'completed', result['answer']
    proof = next(item['result'] for item in state['evidence'] if item['tool'] == 'work_order_analytics')
    assert [(row['planned'], row['unfinished'], row['overdue']) for row in proof['groups']] == expected
    rows = re.findall(r'запланировано (\d+),\s*незаверш[её]нных (\d+),\s*просроченных (\d+)', result['answer'])
    assert [tuple(map(int, row)) for row in rows] == expected
    assert f'{expected[1][0] - expected[0][0]:+d}' in result['answer']
    assert checksums(fixture) == before
