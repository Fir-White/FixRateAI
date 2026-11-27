"""HTTP/PostgreSQL regression tests for the LangGraph driver and checkpoints."""
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from tests.backend.test_assistant import B, assistant_case, thread
from tests.backend.test_assistant_architecture_v2 import add_order, inventory, stored, turn
from tests.backend.test_assistant_equipment_history import add_report
from tests.backend.test_assistant_dependent_analytics import Provider
from tests.backend.test_management import config, join, managed
from tests.backend.test_runtime_integration import runtime


class UnexpectedInference:
    def chat(self, *_):
        pytest.fail('A deterministic v3 plan must not call the language model')


@pytest.fixture
def graph_case(assistant_case, monkeypatch):
    app = assistant_case[1]
    monkeypatch.setitem(app.state._state, 'settings', replace(app.state.settings, assistant_agent_version='v3'))
    monkeypatch.setitem(app.state._state, 'assistant_provider_factory', UnexpectedInference)
    return assistant_case


def checkpoint_rows(engine, chat, kind):
    with engine.connect() as db:
        return db.execute(text("""
            SELECT c.checkpoint, c.metadata
              FROM assistant_checkpoints.checkpoints c JOIN assistant_graph_threads t USING (thread_id)
             WHERE t.conversation_id=:chat AND split_part(c.thread_id, ':', 6)=:kind
             ORDER BY c.checkpoint_id
        """), dict(chat=chat, kind=kind)).all()


@pytest.mark.parametrize('tie', [False, True])
def test_comparison_and_followup_use_only_selected_equipment(graph_case, tie):
    engine, _, admin, _, ids = graph_case
    first = inventory(admin, ids, 'ИТП-21', name='Тепловой пункт')
    second = inventory(admin, ids, 'КА-21', name='Компрессор')
    today = datetime.now(timezone.utc)
    add_order(graph_case, [first, second], 'Общая работа', 'in_progress', today-timedelta(days=2), None)
    if not tie:
        add_order(graph_case, [second], 'Неполадки компрессора', 'assigned', today-timedelta(days=1), None)
    add_order(graph_case, [first], 'Поздняя работа', 'assigned', today+timedelta(days=1), None)
    add_order(graph_case, [first], 'Закрытая работа', 'completed', today-timedelta(days=9), None)
    winner, other = sorted([first, second], key=lambda row: row['equipment_id']) if tie else (second, first)
    _, accepted = add_report(graph_case, winner)
    _, foreign = add_report(graph_case, other)
    rule = admin.chief.post(f'/api/v1/maintenance/equipment/{winner["equipment_id"]}/service-configurations',
        json=config(date.today()+timedelta(days=4), title='Инструкция победителя', valid_from='2025-01-01'))
    assert rule.status_code == 201, rule.text

    found, _, chat = turn(admin.chief, 'Найди КА-21')
    assert found['status'] == 'completed'
    assert second['equipment_id'] in found['answer'] and 'Компрессор' in found['answer']
    assert found['workflow']['metrics']['llm_calls'] == 0

    compared, _, _ = turn(admin.chief, 'Сравни ИТП-21 и КА-21 по состоянию, незавершённым заданиям и просрочкам.', chat=chat)
    assert compared['workflow']['outcome'] == 'completed', (compared['answer'], compared['workflow'])
    assert f'{first["equipment_id"]} · незавершённых 2 · просроченных 1' in compared['answer']
    second_count = 1 if tie else 2
    assert f'{second["equipment_id"]} · незавершённых {second_count} · просроченных {second_count}' in compared['answer']
    assert compared['workflow']['metrics']['llm_calls'] == 0
    assert sum(item['tool'] == 'equipment_find' for item in compared['trace']) == 2

    followup, _, _ = turn(admin.chief, 'Теперь проверь оборудование с большим числом просрочек: покажи историю ТО и действующий регламент.', chat=chat)
    assert followup['workflow']['outcome'] == 'completed', followup
    assert accepted in followup['answer'] and foreign not in followup['answer']
    assert rule.json()['binding_id'] in followup['answer']
    evidence = stored(graph_case, followup['turn_id'])['evidence']
    assert {item['entity']['equipment_id'] for item in evidence} == {winner['equipment_id']}
    assert checkpoint_rows(engine, chat, 'turn')
    assert admin.chief.delete(f'{B}/conversations/{chat}').status_code == 200
    assert not checkpoint_rows(engine, chat, 'turn')


def test_confirmation_survives_rebuilding_app_and_dispatches_once(graph_case, monkeypatch):
    engine, _, admin, _, ids = graph_case
    asset = inventory(admin, ids, 'КА-21')
    work = add_order(graph_case, [asset], 'Задание для отмены', 'assigned', None, None)
    from app.assistant.semantic_plan import RequestedResults

    class SemanticProvider:
        supports_semantic_plan = True

        def chat(self, _, schema, __):
            assert schema is not RequestedResults
            pytest.fail(f'Unexpected provider call: {schema}')

    graph_case[1].state.assistant_provider_factory = SemanticProvider
    result, actions, chat = turn(admin.chief, f'Отмени задание {work}, причина: стендовая проверка.')
    assert result['workflow']['outcome'] == 'awaiting_confirmation', result
    action, = actions
    assert checkpoint_rows(engine, chat, 'action')
    url = f'{B}/actions/{action["action_id"]}/confirm'
    approval = dict(confirmed=True, payload_sha256=action['payload_sha256'])
    assert admin.post(url, json=approval).status_code == 404
    monkeypatch.setenv('FIXRATE_ASSISTANT_AGENT_VERSION', 'v2')
    with TestClient(create_app(engine), cookies=admin.chief.cookies,
                    headers={'X-CSRF-Token': admin.chief.headers['X-CSRF-Token']}) as restarted:
        assert restarted.post(url, json=dict(approval, payload_sha256='0'*64)).status_code == 409
        confirmed = restarted.post(url, json=approval)
        assert confirmed.status_code == 200 and confirmed.json()['status'] == 'succeeded', confirmed.text
        assert restarted.post(url, json=approval).json() == confirmed.json()
    with engine.connect() as db:
        assert db.scalar(text('SELECT status FROM work_orders WHERE work_order_id=:id'), dict(id=work)) == 'cancelled'
        assert db.scalar(text("""
            SELECT count(*) FROM audit_events WHERE entity_id=:id AND action='confirmed'
        """), dict(id=action['action_id'])) == 1


def test_resume_uses_checkpoint_after_worker_loss(graph_case, monkeypatch):
    engine, app, admin, _, ids = graph_case
    inventory(admin, ids, 'ИТП-21')
    inventory(admin, ids, 'КА-21')
    graph = app.state.assistant_turn_graph
    original = graph.astream

    def interrupted(*args, **kwargs):
        return original(*args, **kwargs, interrupt_after=['read'])

    monkeypatch.setattr(graph, 'astream', interrupted)
    chat = thread(admin.chief)
    response = admin.chief.post(f'{B}/conversations/{chat}/messages', json=dict(
        content='Сравни ИТП-21 и КА-21', attachment_ids=[], idempotency_key=str(uuid4())))
    assert response.status_code == 202, response.text
    initial = response.json()['turn_id']
    saved = stored(graph_case, initial)
    assert [goal['status'] for goal in saved['goals']].count('completed') == 1
    with engine.begin() as db:
        db.execute(text("UPDATE assistant_turns SET deadline_at=now()-interval '1 second' WHERE turn_id=:id"),
                   dict(id=initial))
    monkeypatch.setenv('FIXRATE_ASSISTANT_AGENT_VERSION', 'v2')
    with TestClient(create_app(engine), cookies=admin.chief.cookies,
                    headers={'X-CSRF-Token': admin.chief.headers['X-CSRF-Token']}) as restarted:
        restarted.app.state.assistant_provider_factory = UnexpectedInference
        result, actions, _ = turn(restarted, 'Продолжи', chat=chat, resume=initial)
    assert result['workflow']['outcome'] == 'completed' and not actions, result
    assert result['execution_engine'] == 'v3'
    assert sum(row['tool'] == 'equipment_read' for row in result['trace']) == 1
    assert stored(graph_case, result['turn_id'])['root_turn_id'] == initial


def test_top_three_and_four_recommendations_have_bound_evidence(graph_case):
    engine, app, admin, _, ids = graph_case
    assets = [inventory(admin, ids, f'КА-{index}', name=f'Компрессор {index}') for index in range(1, 5)]
    now = datetime.now(timezone.utc)
    reports, bindings = [], []
    for asset, count in zip(assets[:3], (2, 4, 1), strict=True):
        for _ in range(count):
            add_order(graph_case, [asset], 'Работа с истёкшим сроком', 'assigned', now-timedelta(days=2), None)
        _, report = add_report(graph_case, asset, actual=(now-timedelta(days=5)).isoformat(),
                               submitted=now-timedelta(days=4))
        with engine.begin() as db:
            db.execute(text('UPDATE acceptance_reviews SET reviewed_at=:time WHERE work_report_id=:report'),
                       dict(time=now-timedelta(days=3), report=report))
        reports.append(report)
        rule = admin.chief.post(f'/api/v1/maintenance/equipment/{asset["equipment_id"]}/service-configurations',
                                json=config(date.today()+timedelta(days=9), code=asset['asset_code'], valid_from='2025-01-01'))
        assert rule.status_code == 201, rule.text
        bindings.append(rule.json()['binding_id'])
    add_order(graph_case, [assets[3]], 'Плановая работа', 'assigned', now+timedelta(days=2), None)
    question = ('Найди три оборудования с максимальным количеством просроченных работ. '
                'Для каждого проверь карточку, действующий регламент, историю ТО и календарь. '
                'Предложи четыре обоснованных действия.')
    app.state.assistant_provider_factory = lambda: Provider(question, group_by='equipment', metric='overdue', limit=3,
        projections=['equipment_details', 'active_regulations', 'maintenance_history', 'maintenance_calendar'],
        recommendations=4)
    result, actions, _ = turn(admin.chief, question)
    assert not actions and result['workflow']['outcome'] == 'completed', (result['answer'], result['workflow'])
    state = stored(graph_case, result['turn_id'])
    ranking = next(proof['result'] for proof in state['evidence'] if proof.get('output_type') == 'aggregate')
    expected = [(assets[1]['equipment_id'], 4), (assets[0]['equipment_id'], 2), (assets[2]['equipment_id'], 1)]
    assert [(row['id'], row['overdue']) for row in ranking['groups']] == expected
    assert all([link['entity_id'] for link in goal['bindings']] == [identity for identity, _ in expected]
               for goal in state['goals'] if goal['depends_on'])
    assert all(identity in result['answer'] for identity in [*reports, *bindings])
    assert assets[3]['equipment_id'] not in result['answer']
    recommendations = result['answer'].split('## Рекомендуемые действия')[1].splitlines()
    assert len([line for line in recommendations if line[:2] in ('1.', '2.', '3.', '4.') and 'Источник' in line]) == 4


def test_executor_today_and_overdue_keep_own_tasks_and_site_day(graph_case):
    engine, _, admin, login, ids = graph_case
    worker, email = join(graph_case)
    colleague, _ = join(graph_case)
    asset = inventory(admin, ids, 'КА-21')
    now = datetime.now(timezone.utc)
    today = add_order(graph_case, [asset], 'Моё задание на сегодня', 'assigned', None, now)
    overdue = add_order(graph_case, [asset], 'Моё просроченное', 'assigned', now-timedelta(days=3), None)
    other = add_order(graph_case, [asset], 'Назначение коллеги', 'assigned', None, now)
    with engine.begin() as db:
        for identity, assignee in ((today, worker), (overdue, worker), (other, colleague)):
            db.execute(text("""
                INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
                VALUES (:site,:task,:worker,:actor)
            """), dict(site=ids['site'], task=identity, worker=assignee, actor=ids['chief']))

    with closing(login(email)) as client:
        for question, expected in [('Какие у меня сегодня задания?', today),
                                   ('Что из моих работ просрочено?', overdue)]:
            result, actions, _ = turn(client, question)
            assert not actions and result['workflow']['outcome'] == 'completed', (result['answer'], result['workflow'])
            assert result['workflow']['metrics']['llm_calls'] == 0
            facts = [row['result'] for row in stored(graph_case, result['turn_id'])['evidence']]
            assert {task['id'] for read in facts for task in read['items']} == {expected}
            assert other not in result['answer']
