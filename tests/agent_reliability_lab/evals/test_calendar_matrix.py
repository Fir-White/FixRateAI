"""SQL-oracle comparisons across role, work cohorts and past cutoff boundaries."""
from datetime import timedelta
from itertools import combinations, product
import os

import pytest

from tests.agent_reliability_lab.evals.corpus import Case, Step
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import ZONE, lab, test_independent_v3 as execute_case
from tests.backend.test_assistant import assistant_case
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


PAIRS = tuple(combinations(('КА-21', 'КА-210', 'ИТП-21'), 2))
CUTOFFS = (16, 10, 5, 1)
ROLES = ('director', 'chief_engineer', 'engineer')
SCENARIOS = tuple(product(ROLES, enumerate(PAIRS, 1), CUTOFFS))


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('scenario', SCENARIOS, ids=[f'{role}-{index}-minus-{days}' for role, (index, _), days in SCENARIOS])
def test_historical_cutoff(lab, scenario, caplog):
    fixture, now, _, worker, data, known, clients = lab
    role, (index, codes), days = scenario
    condition = now.astimezone(ZONE).date() - timedelta(days=days)
    left, right = codes
    case = Case(f'calendar-{role}-{index}-minus-{days}', 'analytics', role, (
        Step(f'На дату {condition} сравни {left} и {right} по числу незавершённых и просроченных работ. '
             'Укажи UUID обеих карточек и основание исторического среза.', 'historical_compare', codes),
    ), 'calendar_matrix')
    execute_case((fixture, now, condition, worker, data, known, clients), case, caplog)
