"""Server evidence contracts that must not depend on the model doing arithmetic."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import text

from tests.backend.test_assignment_save import jobs
from tests.backend.test_assistant_tool_agent import send
from tests.backend.test_assistant import B, thread
from tests.backend.test_runtime_integration import runtime, login, PREFIX


@pytest.mark.parametrize(('at', 'remaining', 'overdue'), [
    ('2026-11-24T10:01:00+05:00', 599, False),
    ('2026-11-24T20:00:00+05:00', 0, True),
])
def test_expired_planned_window_is_not_deadline_breach(monkeypatch, jobs, at, remaining, overdue):
    from app.assistant import tool_agent
    from app.config import RuntimeSettings
    from app.integration import assistant_workspace, projections

    engine, app, create = jobs
    task = create()
    with engine.begin() as db:
        db.execute(text("""UPDATE work_orders SET planned_start_at='2026-11-24 04:00+00',
            planned_end_at='2026-11-24 05:00+00', regulatory_deadline_at='2026-11-24 15:00+00',
            operation_snapshot=operation_snapshot || '{"title":"TEST exact timing"}'::jsonb
            WHERE work_order_id=:id"""), dict(id=task))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(at).astimezone(tz)

    def assert_timing(item):
        assert item['plannedWindowEnded'] is True
        assert item['mandatoryDeadlineAt'] == '2026-11-24T20:00:00+05:00'
        assert item['deadlineRemainingMinutes'] == remaining
        assert item['isOverdue'] is overdue

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] != 'tool':
                return dict(tool_calls=[dict(function=dict(name='find_work_orders',
                    arguments=dict(q='TEST exact timing', attention_only=True)))])
            data = json.loads(messages[-1]['content'])
            assert data['total'] == len(data['items']) == 1
            assert data['items'][0]['id'] == str(task)
            assert_timing(data['items'][0])
            return dict(content='Срок проверен.')

    monkeypatch.setenv('FIXRATE_ASSISTANT_AGENT_VERSION', 'v4')
    monkeypatch.delenv('FIXRATE_ASSISTANT_V3_PIPELINE', raising=False)
    monkeypatch.setitem(app.state._state, 'settings', RuntimeSettings.from_environment())
    monkeypatch.setattr(app.state, 'assistant_provider_factory', Provider, raising=False)
    for module in (tool_agent, assistant_workspace, projections):
        monkeypatch.setattr(module, 'datetime', Clock)
    with closing(login(app, 'engineer')) as client:
        item = client.get(f'{PREFIX}/ui/tasks/{task}').json()['task']
        assert_timing(item)
        overdue_page = client.get(B+'/workspace/tasks', params=dict(period='overdue', active_only=False,
                                  use_planned_date=True, q='TEST exact timing')).json()
        assert overdue_page['total'] == int(overdue)
        answer = send(client, thread(client), 'Проверь обязательный срок.')['turns'][-1]
        assert answer['status'] == 'completed', answer
        assert answer['answer'] == 'Срок проверен.'


def test_missing_deadline_and_plan_window_do_not_become_expired(monkeypatch, jobs):
    engine, app, create = jobs
    task = create()
    with engine.begin() as db:
        db.execute(text('UPDATE work_orders SET regulatory_deadline_at=NULL WHERE work_order_id=:id'), dict(id=task))
    with closing(login(app,'engineer')) as client:
        item=client.get(f'{PREFIX}/ui/tasks/{task}').json()['task']
    assert item['mandatoryDeadlineAt'] is None
    assert item['plannedWindowEnded'] is None
    assert item['deadlineRemainingMinutes'] is None
    assert not item['isOverdue']


def test_manual_order_deadline_day_is_not_earliest_start_day(jobs):
    engine, app, create = jobs
    task = create()
    with engine.begin() as db:
        db.execute(text("""UPDATE work_orders SET regulatory_deadline_at='2026-11-25 15:00+00',
            operation_snapshot=operation_snapshot || '{"earliest_date":"2026-11-24"}'::jsonb
            WHERE work_order_id=:task"""), dict(task=task))
    with closing(login(app,'engineer')) as c:
        item = c.get(f'{PREFIX}/ui/tasks/{task}').json()['task']
    assert item['mandatoryDeadlineAt'] == '2026-11-25T20:00:00+05:00'
    assert item['mandatoryDueDate'] == '2026-11-25'


def test_attention_counts_unique_orders_and_keeps_all_reasons(jobs):
    engine, app, create = jobs
    task, cancelled = create(), create()
    with engine.begin() as db:
        db.execute(text("""UPDATE work_orders SET regulatory_deadline_at='2020-01-01 00:00+00',
            operation_snapshot=operation_snapshot || '{"title":"TEST unique attention"}'::jsonb
            WHERE work_order_id IN (:task,:cancelled)"""), dict(task=task,cancelled=cancelled))
        db.execute(text("UPDATE work_orders SET status='cancelled' WHERE work_order_id=:id"), dict(id=cancelled))
    with closing(login(app,'engineer')) as c:
        args = dict(period='all', attention_only=True, q='TEST unique attention', limit=1)
        result = c.get(B+'/workspace/tasks', params=args).json()
        assert result['total'] == 1 and result['page_complete']
        item, = result['items']
        assert item['id'] == str(task)
        assert set(item['attentionReasons']) == {'unassigned', 'overdue'}
        closed = c.get(f'{PREFIX}/ui/tasks/{cancelled}').json()['task']
        assert not closed['isOverdue'] and closed['deadlineRemainingMinutes'] is None


def test_selected_day_totals_use_planned_windows_before_pagination(jobs):
    engine, app, create = jobs
    ids=[create() for _ in range(3)]
    with engine.begin() as db:
        for task,start,end in zip(ids,('08:10','10:10','11:10'),('08:40','11:10',None),strict=True):
            db.execute(text("""UPDATE work_orders SET planned_start_at=:starts,planned_end_at=:ends,
                operation_snapshot=operation_snapshot || '{"title":"TEST day totals"}'::jsonb
                WHERE work_order_id=:task"""),
                dict(task=task,starts=f'2026-11-24 {start}+00',ends=f'2026-11-24 {end}+00' if end else None))
    with closing(login(app,'engineer')) as c:
        args=dict(period='all',use_planned_date=True,starts_on='2026-11-24',ends_on='2026-11-24',q='TEST day totals',limit=1)
        result=c.get(B+'/workspace/tasks',params=args).json()
    assert result['total']==3 and not result['page_complete']
    assert result['planned_duration']=={'known_minutes':90,'unknown_count':1,'complete':False}


def test_v4_work_order_pages_keep_totals_and_resume_without_skipping_rows(monkeypatch, jobs):
    from tests.backend.test_v4_context_reads import call, v4

    engine, app, create = jobs
    expected = [str(create()) for _ in range(15)]
    with engine.begin() as db:
        for index, identity in enumerate(expected):
            db.execute(text("""UPDATE work_orders SET
                planned_start_at='2026-12-02 08:00+00'::timestamptz + :i * interval '1 hour',
                planned_end_at='2026-12-02 08:30+00'::timestamptz + :i * interval '1 hour',
                regulatory_deadline_at='2026-12-04 00:00+00',
                operation_snapshot=operation_snapshot || jsonb_build_object('title',
                    'TEST page ' || repeat('Описание операции. ', 90))
                WHERE work_order_id=:identity"""), dict(i=index, identity=identity))

    seen = []

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            args = dict(q='TEST page', limit=15)
            if messages[-1]['role'] != 'tool':
                return call('find_work_orders', **args)
            payload = messages[-1]['content']
            assert len(payload) <= 10500
            page = json.loads(payload)
            assert page.get('total') == 15
            assert page['offset'] == len(seen)
            seen.extend(item['id'] for item in page['items'])
            assert not page['page_complete']
            if page['next_offset'] is not None:
                assert page['next_offset'] == len(seen)
                return call('find_work_orders', offset=page['next_offset'], **args)
            assert seen == expected
            return dict(content='Выборка прочитана.')

    v4(monkeypatch, app, Provider)
    with closing(login(app, 'engineer')) as client:
        assert send(client, thread(client), 'Покажи длинные названия работ.')['turns'][-1]['answer'] == 'Выборка прочитана.'


def test_late_acceptance_boundary_matches_order_overdue():
    from types import SimpleNamespace
    from uuid import uuid4

    from app.integration.analyst import late_acceptance_needs_chief

    deadline = datetime.fromisoformat('2026-11-24T20:00:00+05:00')
    order = SimpleNamespace(regulatory_deadline_at=deadline, exception_context={})
    report_id = uuid4()
    assert not late_acceptance_needs_chief(order, report_id, deadline - timedelta(microseconds=1))
    assert late_acceptance_needs_chief(order, report_id, deadline)
    order.exception_context = {'late_acceptance': {'report_id': str(report_id)}}
    assert not late_acceptance_needs_chief(order, report_id, deadline)
    assert late_acceptance_needs_chief(order, uuid4(), deadline)


def test_v4_engineer_analysis_reports_total_and_does_not_offer_roster_to_executor(monkeypatch, jobs):
    from tests.backend.test_v4_context_reads import v4, call
    engine, app, create = jobs
    task = create()
    day = datetime.now(timezone.utc).date() + timedelta(days=366)
    with engine.begin() as db:
        db.execute(text("""UPDATE work_orders SET planned_start_at=:starts,
            regulatory_deadline_at=:deadline WHERE work_order_id=:task"""), {
                'task': task, 'starts': f'{day} 08:00+00', 'deadline': f'{day} 10:00+00'})
    args = dict(starts_on=day.isoformat(), ends_on=day.isoformat())

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            names = {tool['function']['name'] for tool in tools}
            if messages[-1]['role'] == 'user':
                if messages[-1]['content'] == 'Запрос исполнителя':
                    assert 'read_work_order_analysis' not in names
                else:
                    assert 'read_work_order_analysis' in names
                return call('read_work_order_analysis', **args)
            data = json.loads(messages[-1]['content'])
            if data.get('ok') is False:
                return dict(content='Нет такого доступа.')
            assert data['complete'] is True and data['selected_tasks'] == 1
            assert data['scheduled']['future'] == 1
            return dict(content='Подтверждён один наряд.')

    v4(monkeypatch, app, Provider)
    with closing(login(app,'engineer')) as engineer, closing(login(app,'executor')) as executor:
        assert send(engineer,thread(engineer),'Загрузка по выбранному дню')['turns'][-1]['answer']=='Подтверждён один наряд.'
        assert send(executor,thread(executor),'Запрос исполнителя')['turns'][-1]['answer']=='Нет такого доступа.'
