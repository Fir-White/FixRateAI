"""Exercise the intersection of task state, person, assignment state and day."""
from datetime import datetime, timedelta
from itertools import product
import os

import pytest
from sqlalchemy import text

from agent_reliability_lab.evals.corpus import Case, Step
from agent_reliability_lab.evals.oracle import ledger
from agent_reliability_lab.evals.test_agent_v3_e2e import ZONE, lab, test_independent_v3 as execute_case
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import add_order
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


STATES = ('draft', 'assigned', 'clarification', 'rework', 'in_progress', 'in_review', 'completed', 'cancelled')
OWNERSHIP = ('self', 'other', 'declined', 'unassigned')
SCENARIOS = tuple(product(STATES, OWNERSHIP))


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize(('state', 'assignment'), SCENARIOS)
def test_assignment_scope_and_state(lab, caplog, state, assignment):
    fixture, now, historical, worker, data, known, clients = lab
    engine, _, _, _, ids = fixture
    day = now.astimezone(ZONE).date()
    midnight = datetime.combine(day, datetime.min.time(), ZONE)
    equipment = {'equipment_id': data['equipment']['КА-21']['id']}
    today_task = add_order(fixture, [equipment], 'Проверка шкалы манометра М2', state,
                           midnight+timedelta(days=1), midnight)
    late_task = add_order(fixture, [equipment], 'Контроль обратного клапана R3', state,
                          midnight-timedelta(days=1), midnight-timedelta(days=2))
    if assignment != 'unassigned':
        other = next(row['worker'] for row in data['assignments'] if row['worker'] != worker)
        with engine.begin() as db:
            db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by,status)
                               VALUES (:site,:task,:user,:chief,:status)'''),
                       [dict(ids, task=task, user=other if assignment == 'other' else worker,
                             status='declined' if assignment == 'declined' else 'assigned')
                        for task in (today_task, late_task)])
    current = ledger(engine, ids['site'])
    scenario = Case(f'executor-{state}-{assignment}', 'executor', 'executor', (
        Step('Какие у меня сегодня задания?', 'own_today', ()),
        Step('Покажи мои просроченные задания.', 'own_overdue', ()),
    ), 'executor_matrix')
    execute_case((fixture, now, historical, worker, current, known | {today_task, late_task}, clients), scenario, caplog)
