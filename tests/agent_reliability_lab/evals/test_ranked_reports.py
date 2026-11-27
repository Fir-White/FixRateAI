"""Compound ranked reports validated against independently selected subject IDs."""
from itertools import product
import os
import re

import pytest

from tests.agent_reliability_lab.evals.oracle import OPEN
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import stored, turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


PROFILES = {
    1: 'Для выбранного оборудования перечисли названия и нормативные сроки просроченных заданий.',
    2: 'Для каждой выбранной единицы прочитай историю принятого ТО и действующий регламент.',
    3: 'Для каждой выбранной единицы прочитай карточку, названия и нормативные сроки просроченных заданий, '
       'историю принятого ТО и действующий регламент.',
}


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize(('role', 'limit'), tuple(product(('chief_engineer', 'engineer'), PROFILES)))
def test_ranked_report_follows_only_selected_equipment(lab, role, limit):
    fixture, now, _, _, data, _, clients = lab
    overdue = {key for key, row in data['work'].items() if row['status'] in OPEN and
               row['deadline'] is not None and row['deadline'] < now}
    groups = {}
    for relation in data['links']:
        if relation['task'] in overdue:
            groups.setdefault(relation['equipment'], set()).add(relation['task'])
    expected = sorted(groups, key=lambda key: (-len(groups[key]), key))[:limit]
    before = checksums(fixture)
    prompt = (f'Найди топ {limit} единиц оборудования с наибольшим количеством просроченных работ. '
              'При равенстве ставь меньший UUID раньше. '
              f'{PROFILES[limit]} Предложи два обоснованных действия. Ничего не изменяй.')
    result, actions, _ = turn(clients[role], prompt)
    assert result['status'] == 'completed' and result['execution_engine'] == 'v3' and not actions
    state = stored(fixture, result['turn_id'])
    assert state and state['outcome'] == 'completed', result['answer']
    proof = next(item['result'] for item in state['evidence'] if item['tool'] == 'work_order_analytics'
                 and item.get('output_type') == 'aggregate')
    assert [(row['id'], row['overdue']) for row in proof['groups']] == [(key, len(groups[key])) for key in expected]
    answer = result['answer']
    assert all(key in answer for key in expected) and all(key not in answer for key in set(groups) - set(expected))
    typed_sources = ('equipment_service_history', 'regulations_read') if limit > 1 else ()
    if limit == 3:
        typed_sources += ('equipment_read',)
    for tool in typed_sources:
        assert {item['entity']['equipment_id'] for item in state['evidence'] if item['tool'] == tool} == set(expected)
    if limit in (1, 3):
        assert all(key in answer for group in expected for key in groups[group])
    recommendations = re.findall(r'(?m)^\d+\. .*\bИсточник e\d+\b', answer)
    assert len(recommendations) == 2, answer
    assert checksums(fixture) == before
