"""Intent routing through real chat endpoints with a controlled inference provider."""
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.assistant.dialogue_routing import DialogueRoute, asks_about_previous, grounded_limits, mixed_read_portion
from app.assistant.semantic_plan import RequestedResult, RequestedResults
from app.assistant.tools import TOOLS
from app.schemas.assistant import GoalSpec, ToolSelection
from tests.backend.test_assistant import B, assistant_case, managed, runtime, thread


class RoutedProvider:
    supports_dialogue_routing = True
    supports_semantic_plan = True

    def __init__(self, route, reply='Обычный ответ с объяснением.', results=()):
        self.route = route
        self.reply = reply
        self.results = results
        self.calls = []

    def chat(self, messages, schema, _budget):
        self.calls.append((schema, json.loads(messages[-1]['content'])))
        if schema is DialogueRoute:
            return self.route
        if schema is RequestedResults:
            return RequestedResults(results=list(self.results))
        pytest.fail(f'Unexpected planner call {schema.__name__}')

    def text(self, messages, _budget):
        self.calls.append((str, json.loads(messages[-1]['content'])))
        return self.reply


def send(client, conversation, question):
    response = client.post(B + f'/conversations/{conversation}/messages', json={
        'idempotency_key': str(uuid4()), 'content': question, 'attachment_ids': [],
    })
    assert response.status_code == 202, response.text
    view = client.get(B + f'/conversations/{conversation}').json()
    turn = next(row for row in view['turns'] if row['turn_id'] == response.json()['turn_id'])
    assert turn['status'] == 'completed', turn
    return turn, view['actions']


def test_v3_replans_a_site_request_misclassified_as_conversation(assistant_case, monkeypatch):
    _, app, admin, _, _ = assistant_case

    class NoVerifiedSource(RoutedProvider):
        def chat(self, messages, schema, budget):
            if schema is ToolSelection:
                self.calls.append((schema, json.loads(messages[-1]['content'])))
                return ToolSelection(tools=[], goals=[GoalSpec(id='reply', title='Придуманный ответ', tool='', kind='conversation')])
            return super().chat(messages, schema, budget)

    provider = NoVerifiedSource(DialogueRoute(kind='conversation'), results=[
        RequestedResult(intent='general_explanation', source_text='Объясни сведения о сменах'),
    ])
    monkeypatch.setitem(app.state._state, 'settings', replace(app.state.settings, assistant_agent_version='v3'))
    monkeypatch.setattr(app.state, 'assistant_provider_factory', lambda: provider, raising=False)
    result, actions = send(admin.chief, thread(admin.chief), 'Какие сведения о сменах есть на нашем объекте?')
    assert not actions and result['workflow']['outcome'] == 'blocked'
    assert 'не удалось подтвердить' in result['answer'] and provider.reply not in result['answer']
    assert [item[0] for item in provider.calls] == [DialogueRoute, RequestedResults, ToolSelection]
    assert provider.calls[-1][1]['context']['tools']


@pytest.mark.parametrize(('reply', 'blocked'), [
    ('На объекте есть три вида технического обслуживания.', True),
    ('Техническое обслуживание включает регулярные проверки и плановые работы.', False),
])
def test_v3_response_only_cannot_claim_unread_site_data(assistant_case, monkeypatch, reply, blocked):
    _, app, admin, _, _ = assistant_case
    provider = RoutedProvider(DialogueRoute(kind='conversation'), reply=reply)
    monkeypatch.setitem(app.state._state, 'settings', replace(app.state.settings, assistant_agent_version='v3'))
    monkeypatch.setattr(app.state, 'assistant_provider_factory', lambda: provider, raising=False)
    result, actions = send(admin.chief, thread(admin.chief), 'Что такое техническое обслуживание?')
    assert not actions and result['workflow'] is None
    assert (reply not in result['answer']) == blocked
    assert ('не удалось подтвердить' in result['answer']) == blocked


@pytest.mark.parametrize(('kind','prompt'), [
    ('conversation', 'Как устроена система отопления?'),
    ('system_question', 'Как посмотреть свои задания?'),
    ('clarification', 'Он будет там?'),
])
def test_dialogue_keeps_history_without_creating_workflow(assistant_case, monkeypatch, kind, prompt):
    engine, app, admin, _, _ = assistant_case
    provider = RoutedProvider(DialogueRoute(kind=kind))
    monkeypatch.setattr(app.state, 'assistant_provider_factory', lambda: provider, raising=False)
    conversation = thread(admin)
    first, _ = send(admin, conversation, 'Будем называть это «Лазурь».')
    second, actions = send(admin, conversation, prompt)
    assert not actions and second['workflow'] is None
    assert [call[0] for call in provider.calls] == [DialogueRoute, str, DialogueRoute, str]
    assert provider.calls[-1][1]['history'][0]['user'] == first['content']
    assert provider.calls[-1][1]['history'][0]['answer'] == first['answer']
    assert all(row['tool'].startswith('__') for row in second['trace'])
    with engine.connect() as db:
        assert db.scalar(text('SELECT workflow IS NULL FROM assistant_turns WHERE turn_id=:id'), {'id': second['turn_id']})
    if kind == 'system_question':
        assert 'available_operations' in provider.calls[-1][1]
    else:
        assert 'available_operations' not in provider.calls[-1][1]


def test_external_repository_request_has_grounded_limit_and_no_plan(assistant_case, monkeypatch):
    _, app, admin, _, _ = assistant_case
    provider = RoutedProvider(DialogueRoute(kind='unsupported_request', unavailable=['repository', 'shell']))
    monkeypatch.setattr(app.state, 'assistant_provider_factory', lambda: provider, raising=False)
    turn, actions = send(admin, thread(admin), 'Проведи аудит репозитория, открой git diff и запусти тесты.')
    assert turn['workflow'] is None and not actions
    assert 'Git' in turn['answer'] and 'тесты' in turn['answer'] and 'Пришлите diff' in turn['answer']
    assert [call[0] for call in provider.calls] == [DialogueRoute]
    assert not {'shell', 'git', 'repository'}.intersection(tool.name for tool in TOOLS)


def test_mixed_dialogue_uses_scoped_read_and_explains_external_limit(assistant_case, monkeypatch):
    _, app, admin, _, _ = assistant_case
    provider = RoutedProvider(DialogueRoute(kind='data_query', explain=True, unavailable=['shell']),
                              results=[RequestedResult(intent='self_profile', fields=['role'])])
    monkeypatch.setattr(app.state, 'assistant_provider_factory', lambda: provider, raising=False)
    turn, actions = send(admin, thread(admin), 'Назови мою текущую роль в FixRate, объясни простыми словами и запусти тесты.')
    assert not actions and turn['workflow']['display_plan'] is False
    assert [item['tool'] for item in turn['trace'] if not item['tool'].startswith('__')] == ['profile_read']
    assert 'Роль:' in turn['answer'] and 'тесты' in turn['answer'] and provider.reply in turn['answer']
    model_payload = provider.calls[-1][1]
    assert 'Роль:' in model_payload['verified_results'] and model_payload['read_evidence']


def test_route_cannot_grant_a_write_from_read_only_request(assistant_case, monkeypatch):
    _, app, admin, _, _ = assistant_case
    provider = RoutedProvider(DialogueRoute(kind='data_query'), results=[
        RequestedResult(intent='read_notifications'),
    ])
    monkeypatch.setattr(app.state, 'assistant_provider_factory', lambda: provider, raising=False)
    turn, actions = send(admin, thread(admin), 'Проверь смысл термина «прочитанные уведомления».')
    assert not actions and turn['workflow']['display_plan'] is False
    assert not [row for row in turn['trace'] if row['tool'] == 'notifications_read_all']


@pytest.mark.parametrize(('source', 'expected'), [
    ('Посмотри мои задания и помоги написать письмо инженеру.', 'Посмотри мои задания'),
    ('Назови мою текущую роль и запусти тесты репозитория.', 'Назови мою текущую роль'),
    ('Посмотри мои задания и отмени ближайшее.', None),
    ('Назови мою текущую роль, запусти тесты репозитория и отмени ближайший наряд.', None),
    ('Отредактируй «Посмотри мои задания и запусти тесты».', None),
])
def test_only_grounded_read_portion_is_passed_to_planner(source, expected):
    assert mixed_read_portion(source, DialogueRoute(kind='multi_step_task', unavailable=['shell'])) == expected


def test_capability_limits_require_literal_support():
    route = DialogueRoute(kind='data_query', unavailable=['repository','external_message','shell'])
    assert grounded_limits(route, 'Посмотри мои задания и помоги написать черновик инженеру.').unavailable == []
    assert grounded_limits(route, 'Назови мою роль и запусти pytest.').unavailable == ['shell']


def test_diagnostic_follow_up_is_not_a_new_execution_request():
    history = [{'workflow': {'root_turn_id': 'original'}}]
    assert asks_about_previous('Почему ты остановился и не отправил отчёт? Что сделать дальше?', history)
    assert not asks_about_previous('Почему ты остановился? Отправь отчёт сейчас.', history)
    assert not asks_about_previous('Почему ты остановился?', [])
