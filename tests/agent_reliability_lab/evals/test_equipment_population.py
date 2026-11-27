"""Exact, absent and ambiguous assets across the real role matrix."""
from itertools import product
import os
import re
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import stored, turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


ROLES = ('director', 'chief_engineer', 'engineer', 'executor')
STATE_LABELS = {'active': 'в эксплуатации', 'under_repair': 'в ремонте', 'retired': 'выведено из эксплуатации'}


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize(('role', 'status'), tuple(product(ROLES, STATE_LABELS)))
def test_current_inventory_state(lab, role, status):
    fixture, _, _, _, data, _, clients = lab
    engine, _, _, _, _ = fixture
    card = data['equipment']['КА-21']
    with engine.begin() as db:
        expected = db.execute(text('''UPDATE equipment SET status=:state WHERE equipment_id=:asset
                                      RETURNING equipment_id::text AS id,name,status'''),
                              {'state': status, 'asset': card['id']}).mappings().one()
    before = checksums(fixture)
    result, actions, _ = turn(clients[role], 'Открой карточку КА-21.')
    assert result['execution_engine'] == 'v3' and result['workflow']['outcome'] == 'completed' and not actions
    assert all(value in result['answer'] for value in (expected['id'], expected['name'], STATE_LABELS[expected['status']]))
    assert checksums(fixture) == before


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize(('role', 'profile'), tuple(product(ROLES, ('unknown-id', 'near-code', 'near-name', 'ambiguous-name'))))
def test_resolve_asset_without_speculating(lab, role, profile):
    fixture, _, _, _, data, _, clients = lab
    engine, _, _, _, _ = fixture
    own, hidden = data['equipment']['КА-21'], data['equipment']['КА-210']
    if profile == 'unknown-id':
        prompt = f'Покажи карточку оборудования с UUID {uuid4()}.'
    elif profile == 'near-code':
        prompt = 'Открой карточку КА-211.'
    elif profile == 'near-name':
        prompt = f'Найди оборудование с точным названием «{own["name"].split()[0]}».'
    else:
        with engine.begin() as db:
            db.execute(text('UPDATE equipment SET name=:name WHERE equipment_id=:id'), {'name': own['name'], 'id': hidden['id']})
        prompt = f'Найди оборудование с названием «{own["name"]}». Если вариантов несколько, покажи их коды и попроси выбрать.'
    before = checksums(fixture)
    result, actions, _ = turn(clients[role], prompt)
    assert result['status'] == 'completed' and result['execution_engine'] == 'v3' and not actions
    answer = result['answer'].casefold()
    if profile != 'ambiguous-name':
        assert re.search(r'не найд|нет доступ|недоступ', answer)
        assert all(row['id'] not in answer and row['location'].casefold() not in answer for row in data['equipment'].values())
    elif role == 'executor':
        assert own['id'] in answer and hidden['id'] not in answer and 'ка-210' not in answer
    else:
        assert 'ка-21' in answer and 'ка-210' in answer and re.search(r'уточн|выбер|несколько|неоднознач', answer)
        state = stored(fixture, result['turn_id'])
        assert state['outcome'] == 'awaiting_input'
        assert all(proof['tool'] != 'equipment_read' for proof in state['evidence'])
    assert checksums(fixture) == before
