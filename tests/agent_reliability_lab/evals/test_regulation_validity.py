"""Dated rule versions with independent SQL inclusion and exclusion checks."""
from datetime import timedelta
from itertools import product
import os

import pytest

from tests.agent_reliability_lab.evals.oracle import ledger
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import ZONE, lab
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import config, managed
from tests.backend.test_runtime_integration import PREFIX, runtime


CASES = tuple(product(('chief_engineer', 'engineer', 'executor'), (-10, -3, 0, 5)))


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize(('role', 'offset'), CASES)
def test_rule_validity_uses_requested_date(lab, role, offset):
    fixture, now, _, _, data, _, clients = lab
    engine, _, _, _, ids = fixture
    chief = clients['chief_engineer']
    asset = data['equipment']['КА-21']['id']
    today = now.astimezone(ZONE).date()
    for index, (start, finish, enabled) in enumerate(((-30, -3, True), (2, 14, True), (-12, 12, False))):
        start_day, finish_day = today + timedelta(days=start), today + timedelta(days=finish)
        edited = chief.post(f'{PREFIX}/equipment/{asset}/service-configurations', json=config(
            start_day, code=f'TEMPORAL-{index}', title=f'Нормативная версия {index}',
            valid_until=str(finish_day), enabled=enabled))
        assert edited.status_code == 201, edited.text
    day = today + timedelta(days=offset)
    rows = [rule for rule in ledger(engine, ids['site'])['rules'] if rule['equipment'] == asset]
    expected = {rule['id'] for rule in rows if rule['is_approved'] and rule['publication_status'] == 'published'
                and rule['valid_from'] <= day and (rule['valid_to'] is None or day <= rule['valid_to'])}
    before = checksums(fixture)
    result, actions, _ = turn(clients[role], f'Покажи действующие на {day} регламенты КА-21 и версии их привязок.')
    assert result['status'] == 'completed' and result['execution_engine'] == 'v3' and not actions, result
    answer = result['answer'].casefold()
    assert {rule['id'] for rule in rows if rule['id'] in answer} == expected, answer
    assert 'версия' in answer and str(day) in answer
    if offset:
        assert 'публикац' in answer and 'не подтвержд' in answer
    assert checksums(fixture) == before
