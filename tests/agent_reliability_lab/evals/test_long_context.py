"""Real conversation history through restart and after multiple intervening turns."""
import os

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from tests.agent_reliability_lab.evals.corpus import Case, Step
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab, test_independent_v3 as execute_case
from tests.backend.test_assistant import B, assistant_case
from tests.backend.test_assistant_architecture_v2 import turn
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import PREFIX, runtime


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
def test_return_to_comparison_after_intervening_turns(lab, caplog):
    case = Case('context-return-to-comparison', 'long_dialogue', 'chief_engineer', (
        Step('Сравни КА-21 и ИТП-21 по состоянию, незавершённым заданиям и просрочкам.',
             'compare', ('КА-21', 'ИТП-21')),
        Step('Найди КА-210.', 'card', ('КА-210',)),
        Step('Покажи его действующий регламент.', 'active_rule', ('КА-210',)),
        Step('А покажи его историю ТО.', 'accepted_history', ('КА-210',)),
        Step('Открой карточку КА-21.', 'card', ('КА-21',)),
        Step('Покажи её действующий регламент.', 'active_rule', ('КА-21',)),
        Step('Найди ИТП-21.', 'card', ('ИТП-21',)),
        Step('Теперь проверь его историю обслуживания.', 'accepted_history', ('ИТП-21',)),
        Step('А покажи его действующий регламент.', 'active_rule', ('ИТП-21',)),
        Step('Теперь вернись к сравнению. Из сравниваемой пары выбери оборудование с большим числом просрочек. '
             'При равенстве используй меньший UUID. Укажи выбранный UUID, историю ТО и действующий регламент.',
             'winner_history', ('КА-21', 'ИТП-21')),
    ), 'context')
    execute_case(lab, case, caplog)


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
def test_restored_chat_reads_current_equipment_revision(lab):
    fixture, _, _, _, data, _, clients = lab
    engine, _, _, _, _ = fixture
    chief = clients['chief_engineer']
    row = data['equipment']['КА-21']
    answer, actions, chat = turn(chief, 'Открой карточку КА-21.')
    assert answer['execution_engine'] == 'v3' and row['name'] in answer['answer'] and not actions
    revision = chief.get(f'{PREFIX}/equipment/{row["id"]}').json()['revision']
    name = 'Переименованная панель резерва'
    edit = chief.patch(f'{PREFIX}/equipment/{row["id"]}', json={'name': name, 'expected_revision': revision})
    assert edit.status_code == 200, edit.text
    with TestClient(create_app(engine), cookies=chief.cookies,
                    headers={'X-CSRF-Token': chief.headers['X-CSRF-Token']}) as restarted:
        view = restarted.get(f'{B}/conversations/{chat}')
        assert view.status_code == 200 and view.json()['turns'][0]['turn_id'] == answer['turn_id']
        current, actions, _ = turn(restarted, 'Открой карточку КА-21.', chat=chat)
    assert current['status'] == 'completed' and current['execution_engine'] == 'v3' and not actions
    assert all(value in current['answer'] for value in (row['id'], name))
    assert row['name'] not in current['answer']
