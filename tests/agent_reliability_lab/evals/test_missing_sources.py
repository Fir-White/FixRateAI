"""A saved local rule cannot stand in for an unavailable manufacturer source."""
import os
import re

import pytest

from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import stored, turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('role', ['director', 'chief_engineer', 'engineer', 'executor'])
def test_manufacturer_document_required(lab, role):
    fixture, _, _, _, data, _, clients = lab
    asset = data['equipment']['КА-21']
    local_rules = {row['id'] for row in data['rules'] if row['equipment'] == asset['id']}
    assert local_rules
    before = checksums(fixture)
    result, actions, _ = turn(clients[role], 'Для КА-21 проверь по паспорту производителя норму периодичности ТО. '
                              'Укажи точную ссылку на документ производителя, если он доступен.')
    assert result['execution_engine'] == 'v3' and result['status'] == 'completed' and not actions
    answer = result['answer'].casefold()
    assert re.search(r'(?:источни\w*|инструкци\w*|паспорт\w*).{0,120}(?:нет|недоступ|не найд|не подтвержд)', answer)
    assert all(binding not in answer for binding in local_rules)
    state = stored(fixture, result['turn_id'])
    assert state is None or state['outcome'] in ('blocked', 'partial')
    assert checksums(fixture) == before
