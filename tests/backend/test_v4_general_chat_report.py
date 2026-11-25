"""A name in the general chat must select exactly one authorized work order."""
from contextlib import closing
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.backend.test_assignment_save import jobs
from tests.backend.test_assistant import B, confirm, thread
from tests.backend.test_assistant_message_files import image, send
from tests.backend.test_runtime_integration import PREFIX, login, runtime
from tests.backend.test_v4_context_reads import call, v4
from tests.backend.test_v4_report_photos_submit import draft


@pytest.mark.parametrize(('draft', 'mode'), [
    (True, 'submit'), (False, 'save'), (True, 'revoked'), (True, 'duplicate'),
    (True, 'foreign'), (True, 'no_target'), (True, 'two_titles'),
    (True, 'model_exact_title'), (True, 'model_target_mismatch'),
], indirect=['draft'])
def test_general_chat_photo_proposal_by_exact_title(monkeypatch, draft, jobs, mode):
    engine, app, task, attempt, point = draft
    title = f'Контроль учебной бирки {uuid4().hex[:8]}'
    duplicate = jobs[2]() if mode == 'duplicate' else None
    with engine.begin() as db:
        db.execute(text("""UPDATE work_orders
            SET operation_snapshot=operation_snapshot || jsonb_build_object('title',CAST(:title AS text))
            WHERE work_order_id=:task"""), dict(task=task, title=title))
        if mode == 'duplicate':
            db.execute(text("""UPDATE work_orders
                SET operation_snapshot=operation_snapshot || jsonb_build_object('title',CAST(:title AS text))
                WHERE work_order_id=:duplicate"""), dict(duplicate=duplicate, title=title))
            db.execute(text("""INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
                SELECT site_id,:duplicate,user_id,assigned_by FROM work_assignments WHERE work_order_id=:task"""),
                dict(duplicate=duplicate, task=task))
        if mode == 'foreign':
            db.execute(text("UPDATE work_assignments SET status='cancelled' WHERE work_order_id=:task"), dict(task=task))

    model_calls = []

    class Provider:
        def tool_chat(self, messages, tools, tokens):
            model_calls.append(True)
            if mode in ('model_exact_title', 'model_target_mismatch') and messages[-1]['role'] != 'tool':
                return dict(tool_calls=[*call('read_work_order', task_id=str(task))['tool_calls'],
                                        *call('propose_report_attach_and_submit', task_id=str(task), **payload)['tool_calls']])
            return dict(content='Карточку не подготовил.')

    v4(monkeypatch, app, Provider)
    monkeypatch.setitem(app.state._state, 'automatic_photo_review', lambda *_: None)
    with closing(login(app, 'executor')) as worker, closing(login(app, 'engineer')) as engineer:
        endpoint = f'{PREFIX}/ui/tasks/{task}'
        original = engineer.get(endpoint).json()
        chat = thread(worker)
        ids = [image(worker, chat, 'before.png', 'red')['attachment_id'],
               image(worker, chat, 'after.png', 'blue')['attachment_id']]
        payload = dict(expected_revision=original['task']['revision'], execution_id=str(attempt), photos=[
            dict(attachment_id=photo_id, checklist_item_id=str(point), phase=phase, view_key='front')
            for photo_id, phase in zip(ids, ('before','after'), strict=True)
        ])
        command = 'Добавь эти фото в его отчёт и отправь на проверку.'
        question = f'Наряд «{title}». {command}'
        if mode == 'no_target':
            question = 'Добавь эти фото в отчёт и отправь на проверку.'
        elif mode == 'two_titles':
            question = f'Наряд «{title}» или наряд «Другой наряд». {command}'
        elif mode in ('model_exact_title', 'model_target_mismatch'):
            named = title if mode == 'model_exact_title' else 'Другое точное название'
            question = f'Прикрепи к отчёту приложенное по наряду «{named}» и отправь его на проверку.'
        assert send(worker, chat, ids, question).status_code == 202
        history = worker.get(f'{B}/conversations/{chat}').json()
        assert history['turns'][-1]['status'] == 'completed'
        assert not engineer.get(endpoint).json()['execution']['photos']
        if mode in ('duplicate', 'foreign', 'no_target', 'two_titles', 'model_target_mismatch'):
            assert history['actions'] == []
            if mode != 'model_target_mismatch':
                assert not model_calls
                assert 'наряд' in history['turns'][-1]['answer'].casefold()
            return
        assert bool(model_calls) == (mode == 'model_exact_title')
        action, = history['actions']
        assert action['arguments']['path']['task_id'] == str(task)
        assert action['status'] == 'proposed'
        assert [(p['attachment_id'], p['phase']) for p in action['arguments']['body']['photos']] == list(
            zip(ids, ('before', 'after'), strict=True))
        assert confirm(engineer, action).status_code in (403, 404)
        if mode == 'revoked':
            with engine.begin() as db:
                db.execute(text("UPDATE work_assignments SET status='cancelled' WHERE work_order_id=:task"), dict(task=task))
            assert confirm(worker, action).status_code in (403, 404)
            assert not engineer.get(endpoint).json()['execution']['photos']
        else:
            confirmed = confirm(worker, action).json()
            assert confirmed['status'] == 'succeeded'
            assert confirm(worker, action).json() == confirmed
            complete = mode in ('submit', 'model_exact_title')
            assert confirmed['result']['data']['submission'] == ('submitted' if complete else 'draft_incomplete')
            result = engineer.get(endpoint).json()
            assert result['task']['state'] == ('submitted' if complete else 'in_progress')
            assert sorted(p['phase'] for p in result['execution']['photos']) == ['after', 'before']
            assert result['decision'] is None
