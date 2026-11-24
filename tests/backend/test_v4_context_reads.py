"""Read-only v4 follow-ups preserve source identity, role and selection date."""
from contextlib import closing
from datetime import datetime
from uuid import uuid4
import json

import pytest
from sqlalchemy import text

from tests.backend.test_assignment_save import jobs
from tests.backend.test_assistant import thread
from tests.backend.test_assistant_tool_agent import send
from tests.backend.test_runtime_integration import runtime, login


def v4(monkeypatch, app, provider):
    from app.config import RuntimeSettings
    monkeypatch.setenv('FIXRATE_ASSISTANT_AGENT_VERSION', 'v4')
    monkeypatch.delenv('FIXRATE_ASSISTANT_V3_PIPELINE', raising=False)
    monkeypatch.setitem(app.state._state, 'settings', RuntimeSettings.from_environment())
    monkeypatch.setattr(app.state, 'assistant_provider_factory', provider, raising=False)


def call(name, **args):
    return dict(tool_calls=[dict(function=dict(name=name, arguments=args))])


@pytest.fixture
def report_jobs(jobs):
    engine, app, create = jobs
    orders = []
    def new_order():
        order = create()
        orders.append(order)
        return order
    try:
        yield engine, app, new_order
    finally:
        with engine.begin() as db:
            for order in orders:
                db.execute(text('DELETE FROM acceptance_reviews WHERE work_order_id=:id'), {'id': order})


def test_previous_day_uses_last_resolved_date_not_wall_clock(monkeypatch, runtime):
    from app.assistant import tool_agent
    _, app = runtime
    questions = {
        'Дата 26 ноября': (dict(on_date='2026-11-26'), '2026-11-26'),
        'День перед выбранным': (dict(day_offset_from_last_selection=-1), '2026-11-25'),
        'Вчера по часам': (dict(relative_day='yesterday'), '2026-11-23'),
    }

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat('2026-11-24T18:40:00+05:00').astimezone(tz)

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role']=='user':
                self.question = messages[-1]['content']
                return call('find_work_orders', limit=1, **questions[self.question][0])
            result = json.loads(messages[-1]['content'])
            return dict(content=result.get('resolved_day') or f"Код {result.get('code')}")

    monkeypatch.setattr(tool_agent, 'datetime', Clock)
    v4(monkeypatch, app, Provider)
    with closing(login(app,'engineer')) as c:
        chat = thread(c)
        assert send(c,thread(c),'День перед выбранным')['turns'][-1]['answer']=='Код 422'
        for question, (_,expected) in questions.items():
            assert send(c,chat,question)['turns'][-1]['answer']==expected


def test_list_result_from_regulations_does_not_break_followup(monkeypatch, jobs):
    engine, app, create = jobs
    task = create()
    with engine.connect() as db:
        asset = db.scalar(text('SELECT equipment_id FROM work_order_equipment WHERE work_order_id=:task'), {'task': task})

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role']=='tool':
                assert isinstance(json.loads(messages[-1]['content']), list)
                return dict(content='Регламенты прочитаны.')
            if messages[-1]['content']=='Прочитай регламенты':
                return call('read_regulations', equipment_id=str(asset))
            return dict(content='Могу продолжить.')

    v4(monkeypatch, app, Provider)
    with closing(login(app,'engineer')) as c:
        chat = thread(c)
        assert send(c,chat,'Прочитай регламенты')['turns'][-1]['answer']=='Регламенты прочитаны.'
        followup=send(c,chat,'Продолжим?')['turns'][-1]
        assert followup['status']=='completed',followup
        assert followup['answer']=='Могу продолжить.'


def test_draft_read_shows_saved_checklist_and_linked_asset_without_execution(monkeypatch, jobs):
    engine, app, create = jobs
    task = create()
    with engine.begin() as db:
        asset = db.scalar(text('SELECT equipment_id FROM work_order_equipment WHERE work_order_id=:task'), {'task': task})
        db.execute(text("""UPDATE work_orders SET operation_snapshot=operation_snapshot ||
            jsonb_build_object('checklist',jsonb_build_array(jsonb_build_object(
                'id',CAST(:point AS text),'text','Сверить бирку','required',true,'answerKind','checkbox')))
            WHERE work_order_id=:task"""), {'task': task, 'point': uuid4()})

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] == 'user':
                return call('read_work_order', task_id=str(task))
            data = json.loads(messages[-1]['content'])
            assert data['execution'] is None
            assert data['task']['regulation_equipment_ids'] == [str(asset)]
            assert [item['text'] for item in data['plannedChecklist']] == ['Сверить бирку']
            return dict(content='Инструкция прочитана.')

    v4(monkeypatch, app, Provider)
    with closing(login(app, 'engineer')) as c:
        assert send(c,thread(c),'Что проверить перед отчётом?')['turns'][-1]['answer']=='Инструкция прочитана.'


def test_reviewing_current_image_does_not_mix_in_archived_photos(monkeypatch, jobs):
    from tests.backend.test_assistant_message_files import image, send as send_image
    from tests.backend.test_assistant import B
    _, app, create = jobs
    task = create()

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] == 'user':
                assert len(messages[-1]['images']) == 1
                return call('read_report_photos', task_id=str(task))
            data = json.loads(messages[-1]['content'])
            if data.get('ok') is False:
                assert data['code'] == 422
                return call('read_report_photos', task_id=str(task), compare_with_attachment=True)
            assert data['images_supplied'] == 0 and data['total_available'] == 0
            return dict(content='Источники разделены.')

    v4(monkeypatch, app, Provider)
    with closing(login(app,'engineer')) as c:
        chat = thread(c)
        attached = image(c, chat)
        assert send_image(c, chat, [attached['attachment_id']], 'Оцени приложенный кадр.').status_code == 202
        value = c.get(B+'/conversations/'+chat).json()['turns'][-1]
    assert value['answer']=='Источники разделены.'
    events = [row for row in value['trace'] if row['tool']=='read_report_photos']
    assert [event['status'] for event in events] == ['denied', 'completed']


@pytest.mark.parametrize('via_passport', [False, True], ids=['history', 'passport'])
def test_v4_last_accepted_service_reads_exact_equipment_history(monkeypatch, report_jobs, via_passport):
    engine, app, create = report_jobs
    order, report = create(), uuid4()
    with engine.begin() as db:
        asset=db.execute(text('SELECT equipment_id FROM work_order_equipment WHERE work_order_id=:o'),{'o':order}).scalar_one()
        db.execute(text("""INSERT INTO work_reports(work_report_id,site_id,work_order_id,submitted_by,
            status,submitted_at,execution_context)
            SELECT :r,w.site_id,w.work_order_id,m.user_id,'reviewed','2026-11-21 09:00+00',
                   '{"performed_at":"2026-11-20T12:00:00+05:00"}'
            FROM work_orders w JOIN site_memberships m ON m.site_id=w.site_id AND m.role='engineer'
            WHERE w.work_order_id=:o"""),{'r':report,'o':order})
        db.execute(text("""INSERT INTO acceptance_reviews(site_id,work_order_id,work_report_id,reviewer_user_id,decision,reviewed_at)
            SELECT site_id,work_order_id,work_report_id,submitted_by,'accepted','2026-11-22 09:00+00'
            FROM work_reports WHERE work_report_id=:r"""),{'r':report})

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role']=='user':
                tool = 'read_equipment' if via_passport else 'read_equipment_service_history'
                return call(tool, equipment_id=str(asset))
            result=json.loads(messages[-1]['content'])
            if via_passport:
                result = result['latestAcceptedService']
            assert result['latest_only'] and result['complete'] and result['matched_reports']==1
            assert result['items'][0]['report_id']==str(report)
            assert datetime.fromisoformat(result['items'][0]['performed_at'])==datetime.fromisoformat('2026-11-20T12:00:00+05:00')
            assert result['items'][0]['actual_date_verified']
            return dict(content='Принятое обслуживание проверено.')

    v4(monkeypatch, app, Provider)
    with closing(login(app,'engineer')) as c:
        answer=send(c,thread(c),'Когда его обслуживали?')['turns'][-1]
    assert answer['answer']=='Принятое обслуживание проверено.'


def test_v4_acceptance_distinguishes_previous_return_and_current_block(monkeypatch, report_jobs):
    engine, app, create = report_jobs
    task, older, current=create(),uuid4(),uuid4()
    with engine.begin() as db:
        params={'task':task,'older':older,'current':current}
        db.execute(text("""UPDATE work_orders SET status='in_review',regulatory_deadline_at='2020-01-01 00:00+00',
                    operation_snapshot=operation_snapshot || '{"required_acts":["Протокол"]}'::jsonb
                    WHERE work_order_id=:task"""),params)
        db.execute(text("""INSERT INTO work_reports(work_report_id,site_id,work_order_id,revision_no,submitted_by,status,submitted_at)
            SELECT t.id,w.site_id,w.work_order_id,t.n,m.user_id,t.status, CAST(t.stamp AS timestamptz)
            FROM work_orders w JOIN site_memberships m ON m.site_id=w.site_id AND m.role IN ('technician','executor')
            CROSS JOIN (VALUES (CAST(:older AS uuid),1,'reviewed','2019-12-31 11:00+00'),
                               (CAST(:current AS uuid),2,'submitted','2019-12-31 15:00+00')) AS t(id,n,status,stamp)
            WHERE w.work_order_id=:task AND m.user_id=(SELECT user_id FROM site_memberships WHERE site_id=w.site_id
                 AND role IN ('technician','executor') ORDER BY user_id LIMIT 1)"""),params)
        db.execute(text("""INSERT INTO acceptance_reviews(site_id,work_order_id,work_report_id,reviewer_user_id,decision,comment,reviewed_at)
            SELECT r.site_id,r.work_order_id,r.work_report_id,m.user_id,'rework','Нужен новый снимок','2019-12-31 12:00+00'
            FROM work_reports r JOIN site_memberships m ON m.site_id=r.site_id AND m.role='engineer'
            WHERE r.work_report_id=:older"""),params)

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role']=='user':
                return call('read_work_order',task_id=str(task))
            result=json.loads(messages[-1]['content'])
            if 'task' in result:
                assert result['decision'] is None
                assert result['previousDecision']['executionId']==str(older)
                assert result['execution']['id']==str(current)
                assert result['task']['lateAcceptanceBlocked'] is True
                ground = result['readiness']
                assert ground['execution_id'] == str(current) and ground['revision'] == result['task']['revision']
                assert ground['ready'] is False and 'Акт или протокол — Протокол' in ground['missing_materials']
                assert any('главного инженера' in message for message in ground['acceptance_blocks'])
                return call('check_acceptance_readiness',task_id=str(task),expected_revision=result['task']['revision'],
                            execution_id=str(current))
            assert result['execution_id']==str(current)
            assert result['ready'] is False and any('главного инженера' in s for s in result['acceptance_blocks'])
            return dict(content='Для приёмки нужно разрешение главного инженера.')

    v4(monkeypatch, app, Provider)
    with closing(login(app,'engineer')) as c:
        answer=send(c,thread(c),'Можно принять текущую попытку?')['turns'][-1]
    assert answer['answer']=='Для приёмки нужно разрешение главного инженера.'
