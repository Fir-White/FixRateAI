"""Independent oracles for semantic planning, evidence and answer delivery."""
from datetime import date, datetime, timedelta, timezone
from contextlib import closing
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from sqlalchemy import text

from app.assistant import orchestrator, workflow
from app.assistant.analysis_selection import grounded_analysis
from app.assistant.semantic_execution import collection_lines, render
from app.assistant.semantic_plan import RequestedResult, RequestedResults, _subjects, compile_plan
from app.assistant.tools import TOOLS
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import CompoundProvider, add_order, stored, turn
from tests.backend.test_assistant_dependent_analytics import Provider, checksums
from tests.backend.test_assistant_equipment_history import add_report
from tests.backend.test_management import config, join, managed
from tests.backend.test_runtime_integration import runtime


CLOCK = {'local_date': '2026-11-22'}
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def item(intent, *, source=None, subjects=(), **fields):
    return RequestedResult(intent=intent, subjects=list(subjects), source_text=source, **fields)


def inventory(case, code, *, name='Секция охлаждения'):
    engine, _, _, _, ids = case
    identity = str(uuid4())
    with engine.begin() as db:
        db.execute(text('''INSERT INTO equipment (equipment_id, site_id, system_id, equipment_type_id,
                           asset_code, name, commissioned_on)
                           VALUES (:id, :site, :system, :type, :code, :name, DATE '2025-01-01')'''),
                   dict(ids, id=identity, code=code, name=name))
    return dict(equipment_id=identity, asset_code=code, name=name)


def run(assistant_case, question, *results, **kwargs):
    _, app, admin, _, _ = assistant_case
    app.state.assistant_provider_factory = lambda: CompoundProvider(list(results))
    response, actions, chat = turn(admin.chief, question, **kwargs)
    return response['answer'], stored(assistant_case, response['turn_id']), actions, chat


def test_s07_delivers_requested_identity_from_verified_card(assistant_case):
    card = inventory(assistant_case, 'KT-49', name='Камера теплообмена')
    question = 'Найди KT-49. Сообщи UUID и наименование.'
    answer, state, actions, _ = run(assistant_case, question, item('equipment_details', subjects=['KT-49']))
    assert card['equipment_id'] in answer and card['name'] in answer and not actions
    assert state['outcome'] == 'completed'
    requirement = state['request_spec']['requirements'][0]
    assert requirement['fields'] == ['id', 'name']
    assert requirement['delivery_status'] == 'delivered' and requirement['evidence_ids']
    without, _, _, _ = run(assistant_case, 'Покажи наименование KT-49 без идентификатора.', item('equipment_details'))
    assert card['equipment_id'] not in without


def test_s08_empty_registry_does_not_repeat_operand(assistant_case):
    question = 'Существует ли оборудование AZ-909? Оно есть в старой выгрузке ревизии 3. Проверь точный код по актуальному реестру.'
    answer, state, actions, _ = run(assistant_case, question, item('equipment_details'), item('equipment_exists'))
    assert 'не найдено в доступном актуальном реестре' in answer and 'выгрузка отсутствует' in answer
    assert 'Уточните' not in answer and not actions and state['outcome'] == 'completed'
    assert {proof['status'] for proof in state['evidence']} == {'EMPTY'}


def test_s09_card_delivery_satisfies_redundant_identity_check(assistant_case):
    asset = inventory(assistant_case, 'KF-673')
    answer, state, _, _ = run(assistant_case, 'Проверь карточку KF-673 и сообщи точный инвентарный код и название.',
                              item('equipment_details'), item('equipment_exists', subjects=['KF-673']))
    assert asset['asset_code'] in answer and asset['name'] in answer
    assert [goal['tool'] for goal in state['goals']] == ['equipment_read']
    assert state['outcome'] == 'completed'


@pytest.mark.parametrize('draft', [item('general_explanation'), item('equipment_exists', subjects=['«  Компрессор «Север»  »']), item('equipment_exists')])
def test_s10_quoted_ambiguous_request_lists_candidates(assistant_case, draft):
    name = 'Компрессор Север'
    cards = [inventory(assistant_case, f'KP-{i}3', name=name) for i in range(2)]
    prompt = f'Найди «  {name}  ». Уточни, если название неоднозначно.'
    answer, state, actions, _ = run(assistant_case, prompt, draft)
    assert all(card['equipment_id'] in answer and card['asset_code'] in answer for card in cards)
    assert 'несколько' in answer and state['outcome'] == 'awaiting_input' and not actions
    assert {proof['tool'] for proof in state['evidence']} == {'equipment_find'}


def test_s11_literal_id_is_authorized_in_domain_and_never_substituted(assistant_case):
    case = assistant_case
    _, app, _, login, _ = case
    asset = inventory(case, 'GV-614', name='Фильтр магистрали')
    target = asset['equipment_id']
    question = f'Открой оборудование с ID {target} и покажи название.'
    answer, state, _, _ = run(case, question, item('equipment_details'))
    assert asset['name'] in answer and state['outcome'] == 'completed'
    assert state['evidence'][0]['arguments']['path'] == {'equipment_id': target}
    unknown = str(uuid4())
    answer, state, _, _ = run(case, question.replace(target, unknown), item('equipment_details'))
    assert asset['name'] not in answer and state['outcome'] != 'completed'
    assert state['evidence'][0]['arguments']['path']['equipment_id'] == unknown
    _, email = join(case)
    app.state.assistant_provider_factory = lambda: CompoundProvider([item('equipment_details')])
    with closing(login(email)) as executor:
        response, actions, _ = turn(executor, question)
    assert not actions and asset['name'] not in response['answer']
    state = stored(case, response['turn_id'])
    assert state['evidence'][0]['status'] in ('FORBIDDEN', 'UNAVAILABLE')


@pytest.mark.parametrize('count', [0, 1, 24, 25, 26, 30, 100, 101, 153])
def test_s12_complete_rendering_keeps_every_verified_row(count):
    rows = [dict(id=str(uuid5(NAMESPACE_URL, f'fixrate/new-task/{index}')), title=f'Сверка канала {index}')
            for index in range(count)]
    goal = dict(tool='tasks_find', status='completed', semantic=dict(intent='equipment_tasks', period='all', fields=['name']))
    delivery = {}
    answer = render(goal, [dict(tool='tasks_find', result=dict(items=rows, total=count), complete=True)], delivery=delivery)
    if count:
        assert all(row['id'] in answer for row in rows)
        assert len(answer.splitlines()) == count + 1 and delivery['rows'] == count and delivery['complete']
    else:
        assert 'Подходящих заданий нет.' == answer


def test_s12_multipage_postgres_read_delivers_full_cohort_and_sources(assistant_case):
    asset = inventory(assistant_case, 'LC-754', name='Шкаф регулирования')
    before = datetime.now(timezone.utc) - timedelta(days=3)
    expected = [add_order(assistant_case, [asset], f'Диагностика {i}', 'assigned', before, None) for i in range(101)]
    answer, state, actions, _ = run(assistant_case, 'Перечисли все незавершённые задания LC-754 со сроками.',
                                   item('equipment_tasks', subjects=['LC-754'], period='all'))
    assert not actions and state['outcome'] == 'completed', json.dumps({
        'goals': [(goal['status'], goal['reason'], goal.get('answer_delivery')) for goal in state['goals']],
        'coverage': [requirement['status'] for requirement in state['request_spec']['requirements']],
        'evidence': [(proof['tool'], proof['limitations']) for proof in state['evidence']],
    })
    assert all(identity in answer for identity in expected)
    proof = next(proof for proof in state['evidence'] if proof['tool'] == 'tasks_find')
    assert proof['complete'] and proof['result']['pagination']['coverage_complete']
    assert {row['id'] for row in proof['result']['items']} == set(expected)


def test_s14_new_card_supersedes_history_and_code_check(assistant_case):
    old = inventory(assistant_case, 'TC-781', name='Прежняя станция')
    new = inventory(assistant_case, 'TC-782', name='Новая станция')
    _, _, _, chat = run(assistant_case, 'Покажи карточку TC-781.', item('equipment_details'))
    answer, state, _, _ = run(assistant_case, 'Каково наименование TC-782? Проверь, что код соответствует карточке.',
                              item('equipment_details'), item('other', source='Проверь, что код соответствует карточке.'), chat=chat)
    assert new['name'] in answer and new['asset_code'] in answer and old['name'] not in answer
    assert state['outcome'] == 'completed' and 'Уточните' not in answer


def test_s15_latest_fact_ignores_unrequested_writes_and_planning(assistant_case):
    asset = inventory(assistant_case, 'MX-552', name='Распределитель потока')
    _, report = add_report(assistant_case, asset)
    before = checksums(assistant_case)
    question = 'Когда последнее фактически подтверждённое ТО MX-552 с 2025-01-01 по 2026-12-31? Отдели фактическое ТО от будущего плана.'
    answer, state, actions, _ = run(assistant_case, question, item('latest_maintenance', period='all'),
                                    item('edit_equipment'), item('read_notifications'), item('general_explanation'),
                                    item('equipment_tasks'), item('maintenance_calendar'), item('other'))
    assert report in answer and 'Уточните' not in answer
    assert state['outcome'] == 'completed' and not actions and checksums(assistant_case) == before
    assert {goal['tool'] for goal in state['goals']} == {'equipment_service_history'}


@pytest.mark.parametrize('expression,limit,all_groups', [
    ('исполнителя', 1, False), ('одного исполнителя', 1, False), ('двух исполнителей', 2, False),
    ('пять исполнителей', 5, False), ('первых десять исполнителей', 10, False),
    ('11 исполнителей', 11, False), ('всех исполнителей', None, True),
])
def test_s20_quantity_is_read_from_user_request(expression, limit, all_groups):
    prompt = f'Покажи {expression} с наибольшим числом незавершённых назначений.'
    request = grounded_analysis(prompt, RequestedResults(results=[item('task_list')]), CLOCK)
    assert request.group_by == 'assignee' and request.metric == 'unfinished'
    assert request.limit == limit and request.all_groups is all_groups


@pytest.mark.parametrize('case', ['x01', 'c-s23'])
def test_missing_analytic_sources_are_restored_from_literal_request(assistant_case, case):
    engine, app, admin, _, _ = assistant_case
    first = inventory(assistant_case, 'SR-34', name='Редуктор линии Б')
    second = inventory(assistant_case, 'SP-80', name='Регулятор давления')
    now = datetime.now(timezone.utc)
    add_order(assistant_case, [first, second], 'Контроль отсечки', 'assigned', now-timedelta(days=10), None)
    add_order(assistant_case, [first], 'Проверка линии', 'assigned', now-timedelta(days=9), None)
    _, report = add_report(assistant_case, first, actual=(now-timedelta(days=40)).isoformat())
    with engine.begin() as db:
        db.execute(text('UPDATE acceptance_reviews SET reviewed_at=:at WHERE work_report_id=:report'),
                   {'at': now-timedelta(days=39), 'report': report})
    obligation = date.today()+timedelta(days=10)
    rule = admin.chief.post(f'/api/v1/maintenance/equipment/{first["equipment_id"]}/service-configurations',
                            json=config(obligation, title='Замер редуктора', valid_from='2025-01-01'))
    assert rule.status_code == 201, rule.text
    question = 'Сравни две единицы оборудования с наибольшим числом просрочек. Проверь регламент каждой.'
    wants = {'active_regulations'}
    if case == 'x01':
        question += ' Укажи ID и состояние, проверь историю принятого ТО за последние 12 месяцев и календарь следующего ТО. Только чтение.'
        wants |= {'equipment_details', 'maintenance_history', 'maintenance_calendar'}
    app.state.assistant_provider_factory = lambda: Provider(question, group_by='equipment', metric='overdue', limit=2, projections=[])
    response, actions, _ = turn(admin, question)
    state = stored(assistant_case, response['turn_id'])
    answer = response['answer']
    assert not actions and state['outcome'] == 'completed', answer
    assert rule.json()['binding_id'] in answer
    if case == 'x01':
        assert report in answer and obligation.isoformat() in answer
    assert {req['intent'] for req in state['request_spec']['requirements']} >= wants
    for goal in state['goals'][1:]:
        assert goal['answer_delivery']['complete'] and len(goal['bindings']) == 2


@pytest.mark.parametrize('question', [
    'Сопоставь открытые работы PR-24 и актуальный регламент объекта.',
    'Сравни список незавершённых заданий PR-24 с утверждённым регламентом объекта.',
])
def test_fixed_equipment_comparison_restores_regulation_omitted_by_model(assistant_case, question):
    _, _, admin, _, _ = assistant_case
    equipment = inventory(assistant_case, 'PR-24', name='Опрессовочная установка')
    obligation = date.today() + timedelta(days=10)
    rule = admin.chief.post(f'/api/v1/maintenance/equipment/{equipment["equipment_id"]}/service-configurations',
                            json=config(obligation, title='Испытание на герметичность', valid_from='2025-01-01'))
    assert rule.status_code == 201, rule.text
    deadline = datetime.now(timezone.utc) + timedelta(days=3)
    task = add_order(assistant_case, [equipment], 'Проверка клапана', 'assigned', deadline, deadline)
    before = checksums(assistant_case)
    answer, state, actions, _ = run(assistant_case, question, item('equipment_tasks', subjects=['PR-24']),
                                    item('other', source=question))
    assert not actions and checksums(assistant_case) == before and state['outcome'] == 'completed', answer
    assert task in answer and rule.json()['binding_id'] in answer
    assert {proof['tool'] for proof in state['evidence']} >= {'tasks_find', 'regulations_read'}
    assert {requirement['intent'] for requirement in state['request_spec']['requirements']} == {
        'equipment_tasks', 'active_regulations'}


@pytest.mark.parametrize('name', ['«  Холодильный контур  »', '"Клапан северной ветки"', '“Модуль 70-А”'])
def test_reference_normalization_preserves_internal_spelling(name):
    result = item('equipment_exists', subjects=[name])
    assert len(_subjects(result, f'Найди оборудование {name}.')) == 1
    assert all(mark not in _subjects(result, f'Найди оборудование {name}.')[0] for mark in '«»"“”')


def test_quote_with_example_id_does_not_supply_equipment_operand():
    identity = str(uuid4())
    assert _subjects(item('equipment_details'), f'Объясни пример «Открой оборудование с ID {identity}».') == []


@pytest.mark.parametrize('projection_intent', ['other', 'equipment_details', 'equipment_exists'])
def test_task_card_field_fragment_is_delivered_by_the_same_goal(assistant_case, projection_intent):
    asset = inventory(assistant_case, 'TX-490')
    task = add_order(assistant_case, [asset], 'Осмотр компенсатора', 'assigned', datetime.now(timezone.utc), None)
    fragment = 'сообщи его ID и название'
    answer, state, actions, _ = run(assistant_case, f'Открой задание {task} и {fragment}.',
                                     item('task_details'), item(projection_intent, source=fragment))
    assert not actions and task in answer and 'Осмотр компенсатора' in answer
    assert state['outcome'] == 'completed' and len(state['goals']) == 1
    assert all(result['delivery_status'] == 'delivered' for result in state['request_spec']['requirements'])


def test_saved_task_start_time_survives_misclassified_write_intent(assistant_case):
    from app.assistant.dialogue_routing import DialogueRoute

    _, app, admin, _, _ = assistant_case
    equipment = inventory(assistant_case, 'UV-113')
    scheduled = datetime(2026, 10, 31, 9, 35, tzinfo=timezone.utc)
    task = add_order(assistant_case, [equipment], 'Проверка редуктора хода', 'assigned', scheduled, scheduled)
    question = f'Напиши плановое начало наряда {task}. Другие даты не нужны.'

    class MisroutedStart(CompoundProvider):
        def chat(self, messages, schema, budget):
            if schema is DialogueRoute:
                return DialogueRoute(kind='single_action')
            return super().chat(messages, schema, budget)

    app.state.assistant_provider_factory = lambda: MisroutedStart([item('start_task')])
    before = checksums(assistant_case)
    response, actions, _ = turn(admin.chief, question)
    state = stored(assistant_case, response['turn_id'])
    assert not actions and checksums(assistant_case) == before and state['outcome'] == 'completed'
    assert 'Плановое начало: 31.10.2026' in response['answer']
    assert [proof['tool'] for proof in state['evidence']] == ['task_read']


def test_delivery_budget_reports_partial_and_retains_offset_source():
    delivery = {}
    lines = collection_lines(['a'*1500 for _ in range(29)], total=30, complete=False, delivery=delivery)
    assert delivery == {'complete': False, 'rows': 21, 'total': 30}
    assert '21' in lines[-1] and '30' in lines[-1]


def test_completion_requires_an_answer_receipt_after_tool_success():
    result = RequestedResults(results=[item('equipment_details', subjects=['DL-95'])])
    question = 'Покажи ID оборудования DL-95.'
    selection, metadata = compile_plan(result, question, TOOLS_BY_NAME, CLOCK, [])
    scope = {'user_id': str(uuid4()), 'site_id': str(uuid4()), 'role': 'chief_engineer'}
    state = workflow.create_plan(selection, question, TOOLS_BY_NAME, scope)
    goal = state['goals'][0]
    goal.update(semantic=metadata[goal['id']], status='completed')
    from app.assistant.request_coverage import bind_requirements
    bind_requirements(state, result, reviewed=True, review_required=False)
    assert workflow.update_outcome(state) == 'partial'
    assert 'Не удалось подтвердить' in orchestrator._render(state)
    assert workflow.update_outcome(state) == 'partial'
    assert state['request_spec']['requirements'][0]['delivery_status'] == 'partial'


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Pinned local Qwen run only')
@pytest.mark.parametrize('scenario', ['exact_id', 'selection', 'registry', 'list', 'task'])
def test_live_hardening_smoke(assistant_case, scenario):
    _, _, admin, _, _ = assistant_case
    asset = inventory(assistant_case, 'SV-815', name='Испаритель обратной линии')
    expected = []
    if scenario == 'exact_id':
        prompt = 'Покажи точный UUID, название и состояние оборудования SV-815. Только чтение.'
        expected = [asset['equipment_id'], asset['name'], 'в эксплуатации']
    elif scenario == 'selection':
        second = inventory(assistant_case, 'SV-816', name=asset['name'])
        prompt = f'Найди оборудование «{asset["name"]}». Если название неоднозначно, уточни запись.'
        expected = [asset['asset_code'], second['asset_code'], 'несколько']
    elif scenario == 'registry':
        prompt = 'Существует ли оборудование RX-701 на текущем объекте? Проверь точный код в реестре.'
        expected = ['RX-701', 'не найдено']
    else:
        deadline = datetime.now(timezone.utc)-timedelta(days=3)
        count = 27 if scenario == 'list' else 1
        expected = [add_order(assistant_case, [asset], f'Проверка испарителя {index}', 'assigned', deadline, None)
                    for index in range(count)]
        prompt = ('Перечисли все незавершённые задания SV-815 с нормативными сроками. Ничего не меняй.'
                  if scenario == 'list' else f'Открой задание {expected[0]} и сообщи его ID и название.')
    before = checksums(assistant_case)
    started = perf_counter()
    response, actions, _ = turn(admin.chief, prompt)
    elapsed = perf_counter()-started
    outcome = 'awaiting_input' if scenario == 'selection' else 'completed'
    state = stored(assistant_case, response['turn_id'])
    findings = {'expected_facts': expected, 'expected_outcome': outcome,
                'observed_outcome': state['outcome'] if state else None, 'read_only': not actions and checksums(assistant_case) == before}
    if folder := os.environ.get('FIXRATE_AGENT_AUDIT_OUTPUT'):
        output = Path(folder) / ('hardening-' + scenario + '.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(dict(prompt=prompt, answer=response['answer'], trace=response['trace'],
                               seconds=elapsed, findings=findings, model=response.get('model_ref')),
                               ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert response['status'] == 'completed' and findings['read_only']
    assert findings['observed_outcome'] == outcome, response['answer']
    assert all(fact in response['answer'] for fact in expected), response['answer']
