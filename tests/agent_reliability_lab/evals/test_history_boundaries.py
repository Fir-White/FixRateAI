"""Calendar cutoffs and accepted maintenance against known temporal fixtures."""
from datetime import datetime, timedelta
import os
import re

import pytest
from sqlalchemy import text

from tests.agent_reliability_lab.evals.corpus import Case, Step
from tests.agent_reliability_lab.evals.oracle import ledger
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import ZONE, lab, test_independent_v3 as execute_case
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import add_order
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('offset', [-1, 0, 1])
def test_end_of_historical_day(lab, caplog, offset):
    fixture, now, historical, worker, data, known, clients = lab
    engine, _, _, _, ids = fixture
    first, second = 'ИТП-21', 'КА-21'
    end = datetime.combine(historical+timedelta(days=1), datetime.min.time(), ZONE)
    asset = {'equipment_id': data['equipment'][first]['id']}
    identity = add_order(fixture, [asset], 'Наряд на границе суток', 'assigned',
                         end + timedelta(microseconds=offset), end - timedelta(hours=1))
    scenario = Case(f'calendar-local-end-{offset}', 'analytics', 'chief_engineer', (
        Step(f'На дату {historical} сравни {first} и {second} по числу незавершённых и просроченных нарядов. '
             'Укажи UUID и основание исторического расчёта.', 'historical_compare', (first, second)),
    ), 'calendar_boundary')
    data = ledger(engine, ids['site'])
    execute_case((fixture, now, historical, worker, data, known | {identity}, clients), scenario, caplog)


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('profile', ['undated', 'conflicting'])
def test_unverified_dates_do_not_become_confirmed_maintenance(lab, profile):
    from tests.backend.test_assistant_architecture_v2 import turn
    from tests.backend.test_assistant_equipment_history import add_report

    fixture, now, _, _, data, _, clients = lab
    engine, _, _, _, _ = fixture
    asset = data['equipment']['КА-210']
    actual = now - timedelta(days=2)
    _, bad_report = add_report(fixture, {'equipment_id': asset['id']},
                               actual=actual.isoformat() if profile == 'conflicting' else None,
                               submitted=actual+timedelta(hours=1),
                               decision_actual=(actual-timedelta(days=2)).isoformat() if profile == 'conflicting' else None)
    with engine.begin() as db:
        db.execute(text('UPDATE acceptance_reviews SET reviewed_at=:accepted WHERE work_report_id=:id'),
                   {'id': bad_report, 'accepted': actual+timedelta(days=1)})
    result, actions, _ = turn(clients['chief_engineer'],
                               'Когда было последнее принятое обслуживание КА-210? Укажи UUID отчёта.')
    answer = result['answer'].casefold()
    assert result['execution_engine'] == 'v3' and result['status'] == 'completed' and not actions
    assert bad_report not in answer, result['answer']
    assert re.search(r'не (?:установлен|подтвержд)|подтвердить не удалось', answer), result['answer']
