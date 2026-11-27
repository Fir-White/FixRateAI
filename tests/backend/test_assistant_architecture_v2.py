"""Compound request coverage and fact oracles over disposable PostgreSQL."""
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.assistant import orchestrator, workflow
from app.assistant.analysis_scope import selectors
from app.assistant.dialogue_routing import DialogueRoute
from app.assistant.semantic_plan import RequestedResult, RequestedResults, RequestCoverageReview
from tests.backend.test_assistant import B, assistant_case, thread
from tests.backend.test_assistant_equipment_history import add_report
from tests.backend.test_management import config, managed
from tests.backend.test_runtime_integration import runtime


QUESTION = """Привет! Представь, что я главный инженер и только что приступил к работе.

Сначала коротко объясни, почему своевременное техническое обслуживание насосного оборудования важно для безопасности и надёжности системы.

Затем проверь оборудование НС-01 на моём текущем объекте: какое у него состояние, есть ли незавершённые или просроченные задания, когда проводилось последнее фактически подтверждённое обслуживание и какие действующие регламенты к нему относятся.

На основании полученных данных предложи три наиболее разумных следующих действия для инженера, расположив их по приоритету.

Отделяй подтверждённые факты от рекомендаций. Ничего не изменяй."""


def inventory(client, ids, code, *, name='Насос контура'):
    result = client.post('/api/v1/maintenance/equipment', json=dict(
        system_id=str(ids['system']), equipment_type_id=str(ids['type']),
        asset_code=code, name=name, commissioned_on='2025-01-01'))
    assert result.status_code == 201, result.text
    return result.json()


def add_order(case, assets, title, state, deadline, start):
    identity = str(uuid4())
    engine, _, _, _, ids = case
    with engine.begin() as db:
        db.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,origin,status,
            required_people_snapshot,norm_hours_snapshot,operation_snapshot,planned_start_at,regulatory_deadline_at)
            VALUES (:task,:site,:system,'manual',:state,1,1,CAST(:snapshot AS jsonb),:start,:deadline)"""),
            dict(task=identity, site=ids['site'], system=ids['system'], state=state, start=start, deadline=deadline,
                 snapshot=json.dumps({'title': title})))
        for asset in assets:
            db.execute(text("""INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id)
                VALUES (:site,:system,:task,:asset)"""),
                dict(task=identity, site=ids['site'], system=ids['system'], asset=asset['equipment_id']))
    return identity


@pytest.fixture
def engineering_case(assistant_case):
    engine, app, admin, _, ids = assistant_case
    with engine.begin() as db:
        db.execute(text("UPDATE sites SET timezone='Asia/Yekaterinburg' WHERE site_id=:site"), ids)
    asset = inventory(admin, ids, 'НС-01')
    other = inventory(admin, ids, 'НС-77', name='Другая насосная группа')
    empty = inventory(admin, ids, 'МН-09', name='Резервный манометр')
    now = datetime.now(timezone.utc)
    before, after = now - timedelta(days=2), now + timedelta(days=2)
    overdue = add_order(assistant_case, [asset, other], 'Проверка утечки корпуса', 'in_progress', before, None)
    upcoming = add_order(assistant_case, [asset], 'Ревизия сетчатого фильтра', 'assigned', after, None)
    foreign = add_order(assistant_case, [other], 'Проверка чужой установки', 'assigned', before, None)
    date_scope = date.today() + timedelta(days=7)
    _, accepted = add_report(assistant_case, asset)
    _, unaccepted = add_report(assistant_case, asset, actual='2026-01-02T14:30:00+00:00', acceptance=None)
    _, other_report = add_report(assistant_case, other, actual='2026-01-02T14:40:00+00:00')
    rule = admin.chief.post(f"/api/v1/maintenance/equipment/{asset['equipment_id']}/service-configurations",
        json=config(date_scope, title='Сверка уплотнения', valid_from='2025-01-01'))
    assert rule.status_code == 201, rule.text
    return dict(case=assistant_case, app=app, admin=admin, asset=asset, other=other, empty=empty, overdue=overdue,
                upcoming=upcoming, foreign=foreign, accepted=accepted, unaccepted=unaccepted, other_report=other_report,
                obligation=date_scope.isoformat(), rule=rule.json()['binding_id'])


class CompoundProvider:
    supports_dialogue_routing = True
    supports_semantic_plan = True
    supports_request_coverage = True

    def __init__(self, results, missing=()):
        self.results = results
        self.missing = missing
        self.calls = []

    def chat(self, messages, schema, _budget):
        self.calls.append(schema)
        if schema is DialogueRoute:
            return DialogueRoute(kind='data_query', explain=True)
        if schema is RequestedResults:
            return RequestedResults(results=self.results)
        if schema is RequestCoverageReview:
            return RequestCoverageReview(missing=list(self.missing))
        pytest.fail(f'Unexpected schema: {schema}')

    def text(self, messages, _budget):
        self.calls.append(str)
        payload = json.loads(messages[-1]['content'])
        assert payload['history'] == []
        return 'Плановое обслуживание помогает вовремя обнаружить износ и утечки.'


def turn(client, question, *, chat=None, resume=None):
    chat = chat or thread(client)
    response = client.post(f'{B}/conversations/{chat}/messages',
        json=dict(content=question, idempotency_key=str(uuid4()), attachment_ids=[], resume_turn_id=resume))
    assert response.status_code == 202, response.text
    view = client.get(f'{B}/conversations/{chat}').json()
    result = next(item for item in view['turns'] if item['turn_id'] == response.json()['turn_id'])
    return result, view['actions'], chat


def stored(case, turn_id):
    with case[0].connect() as db:
        return db.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'), {'id': turn_id})


def item(intent, source, *, subject='НС-01', **options):
    return RequestedResult(intent=intent, subjects=[subject] if subject else [], source_text=source, **options)


def compound_results():
    return [
        item('general_explanation', 'почему своевременное техническое обслуживание насосного оборудования важно для безопасности и надёжности системы', subject=None),
        item('equipment_details', 'какое у него состояние', fields=['state']),
        item('equipment_tasks', 'незавершённые или просроченные задания', period='all'),
        item('active_regulations', 'какие действующие регламенты к нему относятся'),
        item('recommend_actions', 'предложи три наиболее разумных следующих действия', subject=None, recommendation_count=3),
    ], [
        item('equipment_tasks', 'просроченные задания', period='overdue'),
        item('latest_maintenance', 'последнее фактически подтверждённое обслуживание'),
    ]


def assert_compound(data, result, actions):
    assert result['status'] == 'completed', result
    assert not actions
    answer = result['answer']
    assert 'Проверка утечки корпуса' in answer and 'Ревизия сетчатого фильтра' in answer
    for identity in ('foreign', 'unaccepted', 'other_report'):
        assert data[identity] not in answer
    assert data['accepted'] in answer and data['rule'] in answer
    state = stored(data['case'], result['turn_id'])
    assert state['read_only'] is True
    assert [proof['result']['items'][0]['id'] for proof in state['evidence']
            if proof['tool'] == 'tasks_find' and proof['result']['period'] == 'overdue'] == [data['overdue']]
    assert len(state['request_spec']['requirements']) == 7
    assert {row['status'] for row in state['request_spec']['requirements']} <= {'completed', 'no_tool_required'}
    assert state['outcome'] == 'completed', state['goals']
    return state


def test_compound_review_recovers_dropped_requirements(engineering_case, monkeypatch):
    data = engineering_case
    draft, missing = compound_results()
    provider = CompoundProvider(draft, missing)
    monkeypatch.setattr(data['app'].state, 'assistant_provider_factory', lambda: provider, raising=False)
    result, actions, _ = turn(data['admin'].chief, QUESTION)
    state = assert_compound(data, result, actions)
    assert state['request_spec']['reviewed'] is True
    assert provider.calls == [DialogueRoute, RequestedResults, RequestCoverageReview, str]


def test_scoped_task_query_filters_membership_and_normative_deadline(engineering_case):
    data = engineering_case
    args = dict(equipment_id=data['asset']['equipment_id'], unfinished_only=True, period='overdue')
    first = data['admin'].get(B + '/workspace/tasks', params=args)
    assert first.status_code == 200, first.text
    assert {row['id'] for row in first.json()['items']} == {data['overdue']}
    assert data['asset']['equipment_id'] in first.json()['items'][0]['equipmentIds']
    with data['case'][0].begin() as db:
        db.execute(text("UPDATE work_orders SET regulatory_deadline_at=now()+interval '5 days' WHERE work_order_id=:id"),
                   {'id': data['overdue']})
    second = data['admin'].get(B + '/workspace/tasks', params=args)
    assert second.json()['items'] == [] and second.json()['page_complete'] is True


def test_latest_date_and_server_calendar_are_independent_of_plan_and_submission(engineering_case):
    data = engineering_case
    url = B + f"/workspace/equipment/{data['asset']['equipment_id']}"
    latest = data['admin'].get(url + '/history', params=dict(latest_only=True)).json()
    assert latest['complete'] is True and latest['items'][0]['report_id'] == data['accepted']
    calculation = data['admin'].get(url + '/calendar-evidence', params=dict(
        approved_only=True, starts_on=data['obligation'], ends_on=data['obligation'])).json()
    assert calculation['complete'] is True and calculation['configurations'][0]['occurrences'] == [
        {'source_date': data['obligation'], 'effective_date': data['obligation'], 'shifted': False}]
    assert latest['items'][0]['performed_at'][:10] != data['obligation']
    add_report(data['case'], data['asset'], actual=None)
    uncertain = data['admin'].get(url + '/history', params=dict(latest_only=True)).json()
    assert uncertain['complete'] is False and uncertain['actual_date_unknown_count'] == 1


@pytest.mark.parametrize(('status', 'disposition'), [(403, 'FORBIDDEN'), (404, 'UNAVAILABLE'),
                                                     (422, 'MISSING_INPUT'), (503, 'UNAVAILABLE'), (500, 'ERROR')])
def test_failed_history_keeps_error_disposition_and_no_empty_claim(engineering_case, monkeypatch, status, disposition):
    data = engineering_case
    provider = CompoundProvider([item('latest_maintenance', 'последнее фактическое ТО')])
    monkeypatch.setattr(data['app'].state, 'assistant_provider_factory', lambda: provider, raising=False)
    original = orchestrator.read_tool

    async def failed_read(app, tool, arguments, *args, **kwargs):
        if tool.name == 'equipment_service_history':
            raise HTTPException(status, 'Контрольный сбой источника.')
        return await original(app, tool, arguments, *args, **kwargs)

    monkeypatch.setattr(orchestrator, 'read_tool', failed_read)
    result, actions, _ = turn(data['admin'].chief, 'Проверь последнее фактическое ТО оборудования НС-01.')
    assert result['status'] == 'completed' and not actions
    assert 'Контрольный сбой' in result['answer'] and 'нет' not in result['answer']
    state = stored(data['case'], result['turn_id'])
    proof = state['evidence'][-1]
    assert proof['status'] == disposition and not proof['complete'] and proof['result'] is None


def test_rolling_12_months_resolves_leap_day_using_object_clock():
    assert selectors('последние 12 месяцев', {'local_date': '2028-02-29'}) == {
        'starts_on': '2027-02-28', 'ends_on': '2028-02-29'}


def test_expired_claim_can_resume_without_polling_first(engineering_case, monkeypatch):
    data = engineering_case
    draft, missing = compound_results()
    provider = CompoundProvider(draft, missing)
    monkeypatch.setattr(data['app'].state, 'assistant_provider_factory', lambda: provider, raising=False)
    initial, _, chat = turn(data['admin'].chief, QUESTION)
    state = stored(data['case'], initial['turn_id'])
    unfinished = next(goal for goal in state['goals'] if goal['tool'] == 'equipment_service_history')
    unfinished.update(status='running')
    with data['case'][0].begin() as db:
        db.execute(text("""UPDATE assistant_turns SET status='running', finished_at=NULL,
            deadline_at=now()-interval '1 second', workflow=CAST(:workflow AS jsonb)
            WHERE turn_id=:id AND worker_claimed_at IS NOT NULL"""),
            dict(id=initial['turn_id'], workflow=json.dumps(state)))
    result, actions, _ = turn(data['admin'].chief, 'Продолжи сохранённое поручение.', chat=chat, resume=initial['turn_id'])
    assert result['status'] == 'completed' and not actions
    saved = stored(data['case'], result['turn_id'])
    assert saved['root_turn_id'] == initial['turn_id']
    assert any(proof['status'] == 'STALE' for proof in saved['evidence'] if proof['goal_id'] == unfinished['id'])
    assert [proof['status'] for proof in saved['evidence'] if proof['tool'] == 'equipment_service_history'] == ['STALE', 'FOUND']
    assert [entry['tool'] for entry in result['trace']] == ['equipment_find', 'equipment_service_history']


def test_discussion_of_saved_task_uses_evidence_after_read(engineering_case, monkeypatch):
    data = engineering_case
    identity = data['overdue']
    question = (f'Открой задание {identity}, объясни, что известно о просрочке, '
                'и предложи варианты для обсуждения.')
    provider = CompoundProvider([
        item('equipment_tasks', f'Открой задание {identity}', subject=None),
        item('general_explanation', 'объясни, что известно о просрочке', subject=None),
        item('other', 'предложи варианты для обсуждения', subject=None),
    ])
    monkeypatch.setattr(data['app'].state, 'assistant_provider_factory', lambda: provider, raising=False)
    result, actions, _ = turn(data['admin'].chief, question)
    assert result['status'] == 'completed' and not actions
    assert [event['tool'] for event in result['trace'] if not event['tool'].startswith('__')] == ['task_read']
    assert 'Карточка подтверждает просрочку' in result['answer']
    assert 'текущим исполнителем' in result['answer'] and 'допущенная бригада' in result['answer']
    assert str not in provider.calls


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Pinned local Qwen run only')
def test_live_nc01(engineering_case, monkeypatch):
    from app.assistant import service

    data = engineering_case
    client = service.provider()
    monkeypatch.setattr(data['app'].state, 'assistant_provider_factory', lambda: client, raising=False)
    started = perf_counter()
    result, actions, _ = turn(data['admin'].chief, QUESTION)
    state = stored(data['case'], result['turn_id'])
    output = Path(os.environ['FIXRATE_AGENT_AUDIT_OUTPUT'])
    output.mkdir(parents=True, exist_ok=True)
    (output / 'nc01-v2.json').write_text(json.dumps(dict(
        elapsed=perf_counter() - started, answer=result['answer'], status=result['status'], trace=result['trace'],
        metrics=state.get('metrics') if state else None, model_metrics=client.metrics,
        request_spec=state.get('request_spec') if state else None,
        expected={key: data[key] for key in ('overdue', 'upcoming', 'foreign', 'accepted', 'unaccepted', 'other_report', 'rule')},
    ), ensure_ascii=False, indent=2), encoding='utf-8')
    assert_compound(data, result, actions)
