"""Agent transport/boundary checks; these do not measure model quality."""
import asyncio
import base64
import io
import json
from contextlib import closing
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image
import pytest
from sqlalchemy import text

from tests.backend.test_runtime_integration import runtime, login
from tests.backend.test_assignment_save import jobs, proposal
from tests.backend.test_assistant import B, thread, confirm


def test_loop_returns_model_prose_after_a_real_tool_result():
    from app.assistant.tool_agent import run_loop

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] == 'user':
                return dict(role='assistant', content='', tool_calls=[
                    dict(id='1', function=dict(name='orders', arguments={'limit': 1}))])
            assert 'Насос №2' in messages[-1]['content']
            return dict(role='assistant', content='Первой идёт проверка насоса №2.')

    async def dispatch(name, args):
        assert (name, args) == ('orders', {'limit': 1})
        return {'title': 'Насос №2'}

    reply, evidence = asyncio.run(run_loop(Provider(), [dict(role='user', content='Что первое?')],
        [dict(function=dict(name='orders'))], dispatch, lambda: None))
    assert reply == 'Первой идёт проверка насоса №2.'
    assert evidence[0]['result'] == {'title': 'Насос №2'}


def test_loop_never_dispatches_unknown_tool_or_identical_repeat():
    from app.assistant.tool_agent import run_loop

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            return dict(role='assistant', content='', tool_calls=[
                dict(id='0', function=dict(name='confirm_action', arguments={})),
                dict(id='1', function=dict(name='orders', arguments={})),
                dict(id='2', function=dict(name='orders', arguments={}))])

    seen = []

    async def dispatch(name, args):
        seen.append(name)
        return {'items': []}

    with pytest.raises(TimeoutError):
        asyncio.run(run_loop(Provider(), [dict(role='user', content='тест')],
            [dict(function=dict(name='orders'))], dispatch, lambda: None))
    assert seen == ['orders']


def test_ollama_native_turn_preserves_actual_image_and_tool_roles(monkeypatch):
    from ml_service.app.providers.ollama import OllamaClient, OllamaConfig
    client = OllamaClient(OllamaConfig('http://127.0.0.1:11434', 'demo:local', 'sha256:'+'1'*64, 10))
    stream = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(stream, 'JPEG')
    image = base64.b64encode(stream.getvalue()).decode()
    tools = [dict(type='function', function=dict(name='orders', parameters=dict(type='object')))]
    messages = [dict(role='user', content='Проверь фото', images=[image]),
                dict(role='assistant', content='', tool_calls=[dict(id='a', function=dict(name='orders', arguments={}))]),
                dict(role='tool', tool_call_id='a', tool_name='orders', content='{"items":[]}')]

    def request(path, payload=None):
        if path == '/api/tags':
            return {'models': [{'name': 'demo:local', 'digest': '1'*64}]}
        assert path == '/api/chat'
        assert payload['tools'] == tools
        assert base64.b64decode(payload['messages'][0]['images'][0]) == stream.getvalue()
        assert payload['messages'][-1]['role'] == 'tool'
        assert payload['messages'][-1]['tool_name'] == 'orders'
        return dict(model='demo:local', done=True, done_reason='stop', message=dict(content='Готово'))

    monkeypatch.setattr(client, 'request', request)
    assert client.tool_chat(messages, tools, 500)['content'] == 'Готово'


def test_ollama_wire_failure_can_recover_with_structured_model_output(monkeypatch):
    from ml_service.app.providers.ollama import OllamaClient, OllamaConfig, OllamaFailure
    client = OllamaClient(OllamaConfig('http://127.0.0.1:11434', 'demo:local', 'sha256:'+'1'*64, 10))
    specs = [dict(type='function', function=dict(name='orders', parameters=dict(type='object')))]
    endpoints = []

    def request(path, payload=None):
        if path == '/api/tags':
            return {'models': [{'name': 'demo:local', 'digest': '1'*64}]}
        if payload.get('tools'):
            endpoints.append('native')
            raise OllamaFailure('OLLAMA_UNAVAILABLE', reason='server_error')
        endpoints.append('structured')
        assert 'orders' in str(payload['messages'])
        assert payload['format']['type'] == 'object'
        return dict(model='demo:local', done=True, done_reason='stop',
                    message=dict(content='{"answer":"","calls":[{"name":"orders","arguments":{"limit":1}}]}'))

    monkeypatch.setattr(client, 'request', request)
    result = client.tool_chat([dict(role='user', content='Найди работу')], specs, 1000)
    assert endpoints == ['native', 'structured']
    assert result['tool_calls'][0]['function'] == dict(name='orders', arguments={'limit': 1})


@pytest.mark.parametrize('finish_reason', ['length', 'content_filter'])
def test_v4_retries_only_truncated_cloud_output_without_dispatching_it(finish_reason):
    from app.assistant.tool_agent import run_loop
    from ml_service.app.providers.aitunnel import AITunnelClient, AITunnelConfig, AITunnelFailure

    client = AITunnelClient(AITunnelConfig('deepseek-v4.1-flash-1017', 'isolated-test'))
    calls = []
    replies = iter([
        dict(finish_reason='tool_calls', message=dict(content='', tool_calls=[
            dict(id='order-1', function=dict(name='orders', arguments='{}'))])),
        dict(finish_reason=finish_reason, message=dict(content='Незавершённый текст', tool_calls=[
            dict(id='order-2', function=dict(name='orders', arguments='{"extra": true}'))])),
        dict(finish_reason='stop', message=dict(content='В реестре один проверенный наряд.')),
    ])

    class Opener:
        def open(self, request, timeout):
            calls.append(json.loads(request.data))
            result = dict(model='deepseek-v4.1-flash-1017', choices=[next(replies)])
            return io.BytesIO(json.dumps(result).encode())

    client.opener = Opener()
    seen = []

    async def dispatch(name, args):
        seen.append((name, args))
        return {'total': 1}

    def run():
        return asyncio.run(run_loop(client, [dict(role='user', content='Сделай сводку.')],
            [dict(type='function', function=dict(name='orders', parameters=dict(type='object')))],
            dispatch, lambda: None))

    if finish_reason == 'length':
        assert run()[0] == 'В реестре один проверенный наряд.'
        assert len(calls) == 3
    else:
        with pytest.raises(AITunnelFailure):
            run()
        assert len(calls) == 2
    assert seen == [('orders', {})]


def test_rejected_tool_arguments_are_model_observations_not_success():
    from app.assistant.tool_agent import run_loop

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] == 'tool':
                assert '"code": 422' in messages[-1]['content']
                return dict(content='Пожалуйста, уточните интервал.')
            return dict(tool_calls=[dict(function=dict(name='orders', arguments={'limit': 1}))])

    async def dispatch(name, args):
        raise HTTPException(422, 'Интервал невалиден')

    result, _ = asyncio.run(run_loop(Provider(), [dict(role='user', content='Проверь интервал')],
        [dict(function=dict(name='orders'))], dispatch, lambda: None))
    assert result == 'Пожалуйста, уточните интервал.'


def send(client, chat, content):
    reply = client.post(f'{B}/conversations/{chat}/messages', json=dict(content=content, idempotency_key=str(uuid4())))
    assert reply.status_code == 202, reply.text
    return client.get(f'{B}/conversations/{chat}').json()


@pytest.mark.parametrize(('utc_hour', 'local_day', 'expected_day_total'), [
    (12, '2026-11-24', 0),
    (19, '2026-11-25', 1),
])
def test_relative_day_uses_site_clock_not_first_order_in_all_time_search(monkeypatch, jobs,
                                                                        utc_hour, local_day, expected_day_total):
    from app.assistant import tool_agent
    from app.config import RuntimeSettings

    engine, app, create = jobs
    task = create()
    with engine.begin() as db:
        db.execute(text("""UPDATE work_orders SET planned_start_at='2026-11-25 06:00:00+00',
            planned_end_at='2026-11-25 06:30:00+00',
            operation_snapshot=operation_snapshot || '{"title":"TEST relative day only"}'::jsonb WHERE work_order_id=:id"""),
            dict(id=task))
        counts = dict(db.execute(text('SELECT status,count(*) FROM work_orders WHERE site_id='
                                      '(SELECT site_id FROM work_orders WHERE work_order_id=:id) GROUP BY status'),
                                 dict(id=task)).all())
        on_day = db.scalar(text("""SELECT count(*) FROM work_orders w
            LEFT JOIN schedule_entries e USING (site_id, schedule_entry_id)
            WHERE w.site_id=(SELECT site_id FROM work_orders WHERE work_order_id=:id)
            AND coalesce((w.planned_start_at AT TIME ZONE 'Asia/Yekaterinburg')::date,e.planned_date)=:day"""),
                           dict(id=task, day=local_day))
        total = sum(counts.values())

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 24, utc_hour, 51, tzinfo=timezone.utc).astimezone(tz)

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] == 'user':
                assert f'Текущая дата объекта: {local_day}' in messages[0]['content']
                assert 'Asia/Yekaterinburg' in messages[0]['content']
                return dict(tool_calls=[
                    dict(id='all', function=dict(name='find_work_orders', arguments={'limit': 1})),
                    dict(id='today', function=dict(name='find_work_orders',
                                                  arguments={'relative_day': 'today', 'q': 'TEST relative day only'})),
                ])
            all_orders, today = [json.loads(message['content']) for message in messages if message['role'] == 'tool']
            assert all_orders['total'] == total > len(all_orders['items'])
            full = all_orders['summary']
            assert full['status_counts'] == {key: counts.get(key, 0) for key in (
                'draft', 'assigned', 'clarification', 'rework', 'in_progress', 'in_review', 'completed', 'cancelled')}
            assert full['today'] == {'date': local_day, 'total': on_day}
            assert today['local_date'] == today['resolved_day'] == local_day
            assert today['timezone'] == 'Asia/Yekaterinburg' and today['total'] == expected_day_total
            assert [item['id'] for item in today['items']] == ([str(task)] if expected_day_total else [])
            return dict(content='Данные проверены.')

    monkeypatch.setenv('FIXRATE_ASSISTANT_AGENT_VERSION', 'v4')
    monkeypatch.delenv('FIXRATE_ASSISTANT_V3_PIPELINE', raising=False)
    monkeypatch.setitem(app.state._state, 'settings', RuntimeSettings.from_environment())
    monkeypatch.setattr(tool_agent, 'datetime', Clock)
    monkeypatch.setattr(app.state, 'assistant_provider_factory', Provider, raising=False)
    with closing(login(app, 'engineer')) as client:
        turn = send(client, thread(client), 'Сколько нарядов за всё время и что запланировано на сегодня?')['turns'][-1]
    assert turn['status'] == 'completed', turn
    assert turn['answer'] == 'Данные проверены.'


def test_v4_default_makes_no_workflow_and_keeps_results_private(monkeypatch, runtime):
    from app.config import RuntimeSettings
    engine, app = runtime
    monkeypatch.delenv('FIXRATE_ASSISTANT_AGENT_VERSION', raising=False)
    monkeypatch.delenv('FIXRATE_ASSISTANT_V3_PIPELINE', raising=False)
    monkeypatch.setitem(app.state._state, 'settings', RuntimeSettings.from_environment())

    class Provider:
        response_model = 'test:transport'

        def tool_chat(self, messages, tools, tokens):
            assert any(tool['function']['name'] == 'find_work_orders' for tool in tools)
            if messages[-1]['role'] == 'tool':
                return dict(content='Ответ на основе найденных нарядов.')
            return dict(tool_calls=[dict(function=dict(name='find_work_orders', arguments={'limit': 2}))])

    monkeypatch.setattr(app.state, 'assistant_provider_factory', Provider, raising=False)
    with closing(login(app, 'engineer')) as client:
        result = send(client, thread(client), 'Покажи работы.')
    turn = result['turns'][-1]
    assert turn['status'] == 'completed', turn
    assert turn['execution_engine'] == 'v4'
    assert turn['prompt_version'] == 'fixrate-tool-calling-v4'
    assert turn['workflow'] is None and 'agent_context' not in turn
    assert turn['model_ref'] == 'test:transport'
    with engine.connect() as db:
        context = db.scalar(text('SELECT agent_context FROM assistant_turns WHERE turn_id=:id'), {'id': turn['turn_id']})
    assert context['results'][0]['result']['total'] >= 2


def test_v4_executor_cannot_read_foreign_order_or_propose_assignment(monkeypatch, jobs):
    from app.config import RuntimeSettings
    _, app, create = jobs
    task = str(create())
    monkeypatch.setenv('FIXRATE_ASSISTANT_AGENT_VERSION', 'v4')
    monkeypatch.delenv('FIXRATE_ASSISTANT_V3_PIPELINE', raising=False)
    monkeypatch.setitem(app.state._state, 'settings', RuntimeSettings.from_environment())

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            assert 'propose_assignment' not in {tool['function']['name'] for tool in tools}
            if messages[-1]['role'] == 'tool':
                assert '"code": 404' in messages[-2]['content']
                assert 'Инструмент недоступен' in messages[-1]['content']
                return dict(content='Наряд недоступен.')
            return dict(tool_calls=[dict(function=dict(name=name, arguments={'task_id': task}))
                        for name in ('read_work_order', 'propose_assignment')])

    monkeypatch.setattr(app.state, 'assistant_provider_factory', Provider, raising=False)
    with closing(login(app, 'executor')) as client:
        result = send(client, thread(client), 'Покажи этот наряд и поменяй исполнителя.')
    assert result['turns'][-1]['answer'] == 'Наряд недоступен.'
    assert result['actions'] == []


@pytest.mark.parametrize('changed', (False, True), ids=('confirm_once', 'stale'))
def test_v4_assignment_card_has_no_effect_until_authenticated_confirmation(monkeypatch, jobs, changed):
    from dataclasses import replace
    engine, app, create = jobs
    task = create()
    monkeypatch.setitem(app.state._state, 'settings', replace(app.state.settings, assistant_agent_version='v4', assistant_v3_pipeline='v3'))

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] == 'tool':
                return dict(content='Проверьте отдельно карточку назначения.')
            return dict(tool_calls=[dict(function=dict(name='propose_assignment',
                arguments=dict(task_id=str(task), reason='Учебное распределение работы')))])

    monkeypatch.setattr(app.state, 'assistant_provider_factory', Provider, raising=False)
    with closing(login(app, 'engineer')) as client, closing(login(app, 'executor')) as executor:
        plan = proposal(client, task)
        with engine.begin() as db:
            db.execute(text('UPDATE work_orders SET planned_start_at=:start, planned_end_at=:end WHERE work_order_id=:id'),
                       dict(id=task, start=plan['start_at'], end=plan['end_at']))
        view = send(client, thread(client), 'Подготовь назначение по этому наряду.')
        assert view['turns'][-1]['status'] == 'completed', view['turns'][-1]
        card, = view['actions']
        assert card['status'] == 'proposed'
        assert confirm(executor, card).status_code == 404
        order = text('SELECT status,revision FROM work_orders WHERE work_order_id=:id')
        with engine.begin() as db:
            assert db.execute(order, {'id': task}).one() == ('draft', 1)
            if changed:
                db.execute(text('UPDATE work_orders SET revision=revision+1 WHERE work_order_id=:id'), {'id': task})
        for _ in range(2):
            response = confirm(client, card)
            assert response.status_code == (409 if changed else 200), response.text
            if not changed:
                assert response.json()['status'] == 'succeeded'
        with engine.connect() as db:
            assert db.execute(order, {'id': task}).one() == ('draft' if changed else 'assigned', 2)
            count = db.scalar(text("SELECT count(*) FROM audit_events WHERE entity_id=:id AND action='assign'"), {'id': task})
        assert count == (0 if changed else 1)


def test_v4_assignment_followup_creates_one_real_card_and_reuses_it(monkeypatch, jobs):
    from dataclasses import replace
    engine, app, create = jobs
    task = create()
    monkeypatch.setitem(app.state._state, 'settings', replace(app.state.settings, assistant_agent_version='v4', assistant_v3_pipeline='v3'))

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] == 'tool':
                return dict(content='Для наряда требуется двое.')
            if messages[-1]['content'] == 'Кого можно отправить?':
                name, args = 'check_assignment', dict(task_id=str(task))
            elif messages[-1]['content'] in ('Только первого', 'Подготовь ещё раз эту же карточку'):
                name, args = 'propose_assignment', dict(task_id=str(task), reason='Учебное распределение')
                if messages[-1]['content'] == 'Только первого':
                    args['executor_ids'] = [plan['executor_ids'][0]]
            else:
                return dict(content='Карточка уже создана.')
            return dict(tool_calls=[dict(function=dict(name=name, arguments=args))])

        def chat(self, messages, schema, tokens):
            decision = {
                'Не назначай, просто объясни выбор': 'discuss',
                'Только первого': 'prepare',
                'обоих тогда': 'prepare',
                'да': 'review',
                'подтверждаю': 'review',
                'Подготовь ещё раз эту же карточку': 'new_assignment',
            }[messages[-1]['content']]
            selected = {'Только первого': [1], 'обоих тогда': [1, 2]}.get(messages[-1]['content'], [])
            return schema.model_validate(dict(decision=decision, selected=selected, answer='Подбор основан на доступности.',
                                              reason='Нужен полный состав на плановую дату.'))

    monkeypatch.setattr(app.state, 'assistant_provider_factory', Provider, raising=False)
    with closing(login(app, 'engineer')) as client:
        plan = proposal(client, task)
        with engine.begin() as db:
            db.execute(text('UPDATE work_orders SET planned_start_at=:start, planned_end_at=:end WHERE work_order_id=:id'),
                       dict(id=task, start=plan['start_at'], end=plan['end_at']))
        chat = thread(client)
        assert send(client, chat, 'Кого можно отправить?')['actions'] == []
        read_only = send(client, chat, 'Не назначай, просто объясни выбор')
        assert read_only['actions'] == []
        assert 'Карточка уже создана' not in read_only['turns'][-1]['answer']
        partial = send(client, chat, 'Только первого')
        assert partial['actions'] == []
        assert partial['turns'][-1]['status'] == 'completed'
        assert '2' in partial['turns'][-1]['answer']
        prepared = send(client, chat, 'обоих тогда')
        card, = prepared['actions']
        assert card['turn_id'] == prepared['turns'][-1]['turn_id']
        assert card['status'] == 'proposed'
        assert card['arguments']['path']['task_id'] == str(task)
        assert set(card['arguments']['body']['executor_ids']) == set(plan['executor_ids'])
        for message in ('да', 'подтверждаю', 'Подготовь ещё раз эту же карточку'):
            assert [action['action_id'] for action in send(client, chat, message)['actions']] == [card['action_id']]
        with engine.connect() as db:
            assert db.scalar(text('SELECT status FROM work_orders WHERE work_order_id=:id'), {'id': task}) == 'draft'
        result = confirm(client, card)
        assert result.status_code == 200 and result.json()['status'] == 'succeeded'


def test_v4_task_context_requires_access_when_chat_is_created(monkeypatch, jobs):
    from dataclasses import replace
    _, app, create = jobs
    task = create()
    monkeypatch.setitem(app.state._state, 'settings', replace(app.state.settings, assistant_agent_version='v4', assistant_v3_pipeline='v3'))
    with closing(login(app, 'engineer')) as engineer, closing(login(app, 'executor')) as executor:
        payload = dict(subject_task_id=str(task))
        allowed = engineer.post(f'{B}/conversations', json=payload)
        assert allowed.status_code == 201 and allowed.json()['subject_task_id'] == str(task)
        assert executor.post(f'{B}/conversations', json=payload).status_code == 404


def test_executor_context_is_not_replayed_after_assignment_is_revoked(monkeypatch, jobs):
    from dataclasses import replace
    from app.integration.demo import demo_id
    engine, app, create = jobs
    task = create()
    monkeypatch.setitem(app.state._state, 'settings', replace(app.state.settings, assistant_agent_version='v4', assistant_v3_pipeline='v3'))
    marker = 'Внутренний регламент задвижки М-91'
    active = {'value': True}

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            joined = '\n'.join(m['content'] for m in messages)
            if active['value']:
                assert marker in joined
                return dict(content=marker)
            assert marker not in joined
            return dict(content='Наряд больше недоступен.')

    monkeypatch.setattr(app.state, 'assistant_provider_factory', Provider, raising=False)
    with engine.begin() as db:
        db.execute(text('''UPDATE work_orders SET operation_snapshot=operation_snapshot||jsonb_build_object('instructions',CAST(:label AS text))
            WHERE work_order_id=:id'''), dict(id=task, label=marker))
        db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
            SELECT site_id,work_order_id,:actor,:assigned_by FROM work_orders WHERE work_order_id=:id'''),
                   dict(id=task, actor=demo_id('user-1'), assigned_by=demo_id('engineer')))
    with closing(login(app, 'executor')) as client:
        chat = client.post(f'{B}/conversations', json={'subject_task_id': str(task)}).json()['conversation_id']
        assert send(client, chat, 'Что в инструкции?')['turns'][-1]['answer'] == marker
        with engine.begin() as db:
            db.execute(text("UPDATE work_assignments SET status='cancelled' WHERE work_order_id=:id"), {'id': task})
        active['value'] = False
        answer = send(client, chat, 'А теперь поясни её подробнее.')['turns'][-1]['answer']
        assert answer == 'Наряд больше недоступен.'
