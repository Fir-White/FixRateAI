"""Verbatim user scenarios through FastAPI, LangGraph and PostgreSQL."""
from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.assistant import service
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import CompoundProvider, add_order, inventory, item, stored, turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_assistant_equipment_history import add_report
from tests.backend.test_assistant_graph_v3 import graph_case
from tests.backend.test_management import config, join, managed
from tests.backend.test_runtime_integration import runtime


PROMPTS = json.loads((Path(__file__).parents[1] / 'fixtures/assistant-v3-user-audit-20261123.json').read_text(encoding='utf-8'))


def fixture(case):
    engine, app, admin, _, ids = case
    first = inventory(admin, ids, 'ИТП-21', name='Тепловой пункт')
    second = inventory(admin, ids, 'КА-21', name='Шкаф каскадной автоматики')
    other = inventory(admin, ids, 'ПУ-01', name='Отдельная установка')
    worker, _ = join(case)
    other_worker, _ = join(case)
    now = datetime.now(timezone.utc)
    archived = datetime(2026, 10, 29, 13, tzinfo=timezone.utc)
    future = datetime(2026, 12, 29, 13, tzinfo=timezone.utc)
    overdue = [add_order(case, [asset], 'Задание с ранним сроком', 'assigned', archived, None)
               for asset in (first, second)]
    for asset in (first, second):
        for number in range(10):
            add_order(case, [asset], f'Дальнейшая заявка {number}', 'assigned', future, None)
        add_order(case, [asset], 'Завершённая работа', 'completed', archived, None)
    assignments = [add_order(case, [other], f'Открытая работа {number:02}', 'in_progress' if number % 2 else 'assigned',
                             future, None) for number in range(53)]
    closed = add_order(case, [other], 'Закрытое назначение', 'completed', archived, None)
    selected = min((first, second), key=lambda record: record['equipment_id'])
    rejected = max((first, second), key=lambda record: record['equipment_id'])
    _, accepted = add_report(case, selected, actual=(now-timedelta(days=5)).isoformat(), submitted=now-timedelta(days=4))
    _, unrelated = add_report(case, rejected, actual=(now-timedelta(days=5)).isoformat(), submitted=now-timedelta(days=4))
    rules = admin.chief.post(f'/api/v1/maintenance/equipment/{selected["equipment_id"]}/service-configurations',
                             json=config(date(2026,12,29), title='Регламент испытания', valid_from='2025-01-01'))
    assert rules.status_code == 201, rules.text
    with engine.begin() as conn:
        conn.execute(text("UPDATE equipment SET location='Корпус 3, ИТП' WHERE equipment_id=:id"),
                     dict(id=second['equipment_id']))
        conn.execute(text('UPDATE acceptance_reviews SET reviewed_at=:time WHERE work_report_id IN (:first,:second)'),
                     dict(time=now-timedelta(days=3),first=accepted,second=unrelated))
        snapshot = dict(required_acts=['Акт испытания'], checklist=[
            dict(id=str(uuid4()), text='Контрольный замер', required=True, answerKind='boolean', photoRequired=True)])
        conn.execute(text("""UPDATE work_orders SET operation_snapshot=operation_snapshot||CAST(:snapshot AS jsonb)
            WHERE work_order_id=:id"""), dict(id=min(overdue),snapshot=json.dumps(snapshot)))
        for order, person in [(order,worker) for order in [*assignments,closed,min(overdue)]] + [(assignments[0],other_worker)]:
            conn.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
               VALUES (:site,:task,:person,:chief)'''), dict(ids,task=order,person=person))
    return dict(first=first,second=second,worker=worker,selected=selected,accepted=accepted,unrelated=unrelated,
                bindings=rules.json()['binding_id'],assignment_ids=sorted([*assignments,min(overdue)]),
                overdue=min(overdue),closed=closed)


@pytest.mark.parametrize('live', [
    False,
    pytest.param(True, marks=pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE')!='1', reason='Pinned local Qwen run only')),
], ids=['controlled-planner','local-qwen'])
def test_original_user_dialogue(graph_case, live, monkeypatch, caplog):
    case = graph_case
    _, app, admin, _, _ = case
    data = fixture(case)
    if live:
        monkeypatch.setattr(app.state, 'assistant_provider_factory', service.provider)
    else:
        provider = CompoundProvider([item('equipment_details', PROMPTS['1'][:150], subject='КА-21',
            fields=['id','code','name','state','location'])])
        monkeypatch.setattr(app.state, 'assistant_provider_factory', lambda: provider)
    caplog.set_level(logging.INFO, logger='app.assistant.service')
    before = checksums(case)
    chat = None
    results = {}
    for number in ('1','2','3','5','6'):
        result, actions, chat = turn(admin.chief, PROMPTS[number], chat=chat)
        state = stored(case, result['turn_id'])
        assert result['execution_engine'] == 'v3' and not actions
        assert result['status'] == 'completed' and state['outcome'] == 'completed', (number, result['answer'], state)
        assert all(req['status'] in ('completed','no_tool_required') for req in state['request_spec']['requirements'])
        assert any(f"turn={result['turn_id']} node=quality_gate" in record.getMessage() for record in caplog.records)
        if live:
            assert result['model_ref'].startswith('ollama:qwen3.5:4b-q4_K_M@sha256:')
            if number == '1':
                assert state['metrics']['llm_calls'] > 0
        if number != '1':
            assert state['metrics']['llm_calls'] == 0
        results[number] = result, state

    found, found_state = results['1']
    assert all(value in found['answer'] for value in (data['second']['equipment_id'],'КА-21',
        'Шкаф каскадной автоматики','Корпус 3, ИТП','в эксплуатации','Источник e2 · equipment_read'))
    assert [proof['tool'] for proof in found_state['evidence']] == ['equipment_find','equipment_read']

    comparison, comparison_state = results['2']
    receipt = comparison_state['evidence'][0]['result']
    assert receipt['query']['as_of'] == '2026-11-22' and not receipt['query']['windows']
    assert {(row['id'],row['unfinished'],row['overdue']) for row in receipt['groups']} == {
        (data['first']['equipment_id'],11,1),(data['second']['equipment_id'],11,1)}
    assert 'Равенство: по 1' in comparison['answer'] and 'Исторический статус заданий' in comparison['answer']

    followup, followup_state = results['3']
    assert data['selected']['equipment_id'] in followup['answer'] and 'Выбран меньший UUID' in followup['answer']
    assert data['accepted'] in followup['answer'] and data['unrelated'] not in followup['answer']
    assert data['bindings'] in followup['answer'] and 'версия' in followup['answer'] and '2026-11-22' in followup['answer']
    assert {p['tool'] for p in followup_state['evidence']} == {'equipment_service_history','regulations_read'}
    assert {p['entity']['equipment_id'] for p in followup_state['evidence']} == {data['selected']['equipment_id']}

    load, load_state = results['5']
    work = next(p['result'] for p in load_state['evidence']
                if p['goal_id']=='analysis-staff_assignments' and p.get('output_type')=='staff_assignments')
    assert load_state['evidence'][0]['result']['groups'][0]['id'] == str(data['worker'])
    assert work['total'] == len(data['assignment_ids'])
    assert sorted(row['task_id'] for row in work['items']) == data['assignment_ids']
    assert 'Показано 1–20' in load['answer'] and 'нормативный срок' in load['answer'] and 'назначено' in load['answer']
    assert work['items'][20]['task_id'] not in load['answer']
    for page in (2,3):
        result, actions, _ = turn(admin.chief, f'Покажи страницу {page} назначений', chat=chat)
        expected = work['items'][(page-1)*20:page*20]
        assert not actions and all(row['task_id'] in result['answer'] for row in expected)

    acceptance, acceptance_state = results['6']
    assert [proof['tool'] for proof in acceptance_state['evidence']] == [
        'work_order_analytics','task_read','task_acceptance_evidence']
    report = acceptance_state['evidence'][-1]['result']
    assert report['task_id'] == data['overdue'] and report['submission_ready'] is False
    assert 'Фактический отчёт отсутствует' in acceptance['answer'] and 'Акт испытания' in acceptance['answer']
    assert 'Контрольный замер · обязательный · ответ отсутствует' in acceptance['answer']
    assert report['linked_equipment'][0]['id'] in acceptance['answer'] and str(data['worker']) in acceptance['answer']
    assert checksums(case) == before


def test_followup_rechecks_pair_when_legacy_answer_had_no_comparison_receipt(graph_case):
    case = graph_case
    engine, _, admin, _, _ = case
    data = fixture(case)
    compared, _, chat = turn(admin.chief, PROMPTS['2'])
    legacy = stored(case, compared['turn_id'])
    legacy['evidence'] = []
    legacy['outcome'] = 'partial'
    with engine.begin() as conn:
        conn.execute(text('UPDATE assistant_turns SET workflow=CAST(:workflow AS jsonb) WHERE turn_id=:id'),
                     dict(workflow=json.dumps(legacy), id=compared['turn_id']))
    followup, actions, _ = turn(admin.chief, PROMPTS['3'], chat=chat)
    state = stored(case, followup['turn_id'])
    assert not actions and state['outcome']=='completed', followup['answer']
    assert [proof['tool'] for proof in state['evidence']] == [
        'work_order_analytics','equipment_service_history','regulations_read']
    assert data['selected']['equipment_id'] in followup['answer'] and data['unrelated'] not in followup['answer']
    assert data['accepted'] in followup['answer'] and 'проверка исходной пары' in followup['answer']


def test_unavailable_comparison_card_never_yields_winner(graph_case):
    _, _, admin, _, ids = graph_case
    inventory(admin, ids, 'ИТП-21')
    compared, actions, chat = turn(admin.chief, PROMPTS['2'])
    state = stored(graph_case, compared['turn_id'])
    assert not actions and state['outcome'] == 'partial'
    assert any(req['intent']=='aggregate_comparison' and req['status']!='completed'
               for req in state['request_spec']['requirements'])
    followup, actions, _ = turn(admin.chief, PROMPTS['3'], chat=chat)
    saved = stored(graph_case, followup['turn_id'])
    assert not actions and saved['outcome']!='completed'
    assert {proof['tool'] for proof in saved['evidence']} == {'work_order_analytics'}


def test_followup_finishes_when_authorized_regulation_list_is_empty(graph_case):
    _, _, admin, _, ids = graph_case
    first = inventory(admin, ids, 'ИТП-21')
    second = inventory(admin, ids, 'КА-21')
    _, _, chat = turn(admin.chief, PROMPTS['2'])
    answer, actions, _ = turn(admin.chief, PROMPTS['3'], chat=chat)
    saved = stored(graph_case, answer['turn_id'])
    assert not actions and saved['outcome']=='completed', answer
    assert 'Среди опубликованных сейчас записей регламент на 2026-11-22 не найден' in answer['answer']
    assert min(first['equipment_id'],second['equipment_id']) in answer['answer']
    assert next(p['status'] for p in saved['evidence'] if p['tool']=='regulations_read')=='EMPTY'
