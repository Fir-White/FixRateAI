"""v4 answer grounding for local regulation dates, role and empty private reads."""
from contextlib import closing
from datetime import datetime, time, timedelta
import json

import pytest
from sqlalchemy import text

from app.integration.demo import demo_id
from tests.backend.test_assistant import thread
from tests.backend.test_assistant_tool_agent import send
from tests.backend.test_runtime_integration import login, runtime
from tests.backend.test_v4_context_reads import call, v4


@pytest.mark.parametrize(('offset', 'expected'), [(-1, 'future'), (0, 'active'), (1, 'expired')])
def test_regulation_distinguishes_publication_from_effective_window(monkeypatch, runtime, offset, expected):
    from app.assistant import tool_agent
    engine, app = runtime
    ids = dict(edition=demo_id('assignment-edition'), binding=demo_id('assignment-binding'))
    with engine.begin() as db:
        first = db.scalar(text('SELECT valid_from FROM rule_equipment WHERE binding_id=:binding'), ids)
        prior = db.execute(text('SELECT effective_from,effective_to FROM regulation_editions WHERE regulation_edition_id=:edition'), ids).one()
        effective = first + timedelta(days=3)
        db.execute(text('UPDATE regulation_editions SET effective_from=:day,effective_to=:day WHERE regulation_edition_id=:edition'),
                   dict(ids, day=effective))
    day = effective + timedelta(days=offset)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.combine(day, time(hour=9), tz)

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] != 'tool':
                return call('read_regulations', equipment_id=str(demo_id('assignment-equipment')))
            rule, = json.loads(messages[-1]['content'])
            assert rule['publication_status'] == 'published'
            assert rule['effective_on'] == str(day)
            assert rule['effective_status'] == expected
            assert rule['effective_from'] == rule['effective_until'] == str(effective)
            return dict(content='Это черновик, а не опубликованное правило.')

    monkeypatch.setattr(tool_agent, 'datetime', Clock)
    v4(monkeypatch, app, Provider)
    try:
        with closing(login(app, 'engineer')) as client:
            result = send(client, thread(client), 'Какой регламент действует сейчас у учебного узла?')
        answer = result['turns'][-1]['answer'].casefold()
        assert {'future':'ещё не действует', 'active':'действует на дату', 'expired':'срок действия истёк'}[expected] in answer
        assert 'опубликован' in answer and 'черновик' not in answer
        assert effective.isoformat() in answer and 'раз в месяц' in answer
        assert result['actions'] == []
    finally:
        with engine.begin() as db:
            db.execute(text('UPDATE regulation_editions SET effective_from=:start,effective_to=:end WHERE regulation_edition_id=:edition'),
                       dict(ids, start=prior[0], end=prior[1]))


@pytest.mark.parametrize(('role','question'), [
    ('engineer', 'Верни на доработку отчёт о цепи сигнала, причину придумай сам.'),
    ('engineer', 'Попробуй принять «Осмотр соединений секции» за меня.'),
    ('executor', 'Сам прими мой отчёт по контрольной бирке.'),
])
def test_acceptance_actions_state_server_role_without_model(monkeypatch, runtime, role, question):
    _, app = runtime
    model_calls = []

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            model_calls.append(True)
            return dict(content='Решение может подтвердить обычный инженер.')

    v4(monkeypatch, app, Provider)
    with closing(login(app, role)) as client:
        result = send(client, thread(client), question)
    assert result['turns'][-1]['status'] == 'completed'
    assert 'главный инженер' in result['turns'][-1]['answer'].casefold()
    assert result['actions'] == [] and not model_calls


def test_executor_named_missing_order_does_not_request_foreign_code(monkeypatch, runtime):
    _, app = runtime
    title = 'TEST недоступный запрос 47316'

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] != 'tool':
                return call('find_work_orders', q=title)
            assert json.loads(messages[-1]['content'])['total'] == 0
            return dict(content='Во всём реестре наряда нет. Укажите его точный код.')

    v4(monkeypatch, app, Provider)
    with closing(login(app, 'executor')) as client:
        result = send(client, thread(client), f'Покажи мне наряд «{title}»: исполнителей, отчёт и фото.')
    answer = result['turns'][-1]['answer']
    assert 'не найден среди доступных вам нарядов' in answer
    assert 'код' not in answer and not result['actions']
