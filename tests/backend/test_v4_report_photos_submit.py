"""One authenticated v4 confirmation, not a chat reply, changes the report."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.backend.test_assignment_save import jobs
from tests.backend.test_assistant import B, confirm, rpc, thread
from tests.backend.test_assistant_message_files import image, send
from app.storage import safe_storage_path
from tests.backend.test_runtime_integration import PREFIX, login, runtime
from tests.backend.test_v4_context_reads import call, v4


@pytest.fixture
def draft(jobs, request):
    engine, app, create = jobs
    task, attempt, point = create(), uuid4(), uuid4()
    params = dict(task=task, attempt=attempt, point=point, items=json.dumps([
        dict(id=str(point), text='Сверить бирку', answerKind='boolean', required=True, photoRequired=True)
    ]))
    with engine.begin() as db:
        db.execute(text("""UPDATE work_orders SET status='in_progress',
            operation_snapshot=operation_snapshot-'methodology_ref'-'measurement_requirements'-'required_acts'
            WHERE work_order_id=:task"""), params)
        db.execute(text("""INSERT INTO checklist_templates(checklist_template_id,site_id,operation_template_id,
            item_code,prompt,input_kind)
            SELECT :point,c.site_id,c.operation_template_id,CAST(:point AS text),'Сверить бирку','checkbox'
            FROM checklist_templates c JOIN work_orders w ON w.site_id=c.site_id
            WHERE w.work_order_id=:task ORDER BY c.checklist_template_id LIMIT 1"""), params)
        db.execute(text("""INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
            SELECT w.site_id,w.work_order_id,u.user_id,u.user_id FROM work_orders w CROSS JOIN users u
            WHERE work_order_id=:task AND u.email='fixrate-demo-1@example.test'"""), params)
        db.execute(text("""INSERT INTO work_reports(work_report_id,site_id,work_order_id,revision_no,submitted_by,checklist_snapshot)
            SELECT :attempt,site_id,work_order_id,1,user_id,CAST(:items AS jsonb)
            FROM work_assignments WHERE work_order_id=:task"""), params)
        if request.param:
            db.execute(text("""INSERT INTO checklist_results(site_id,work_order_id,work_report_id,checklist_template_id,
                question_snapshot,response_value) SELECT site_id,work_order_id,work_report_id,:point,
                'Сверить бирку','{"answer":"done"}'::jsonb FROM work_reports WHERE work_report_id=:attempt"""), params)
    yield engine, app, task, attempt, point
    with engine.begin() as db:
        for relation in ('evidence_files', 'checklist_results', 'ai_quality_checks'):
            db.execute(text(f'DELETE FROM {relation} WHERE work_report_id=:attempt'), params)
        db.execute(text('DELETE FROM checklist_templates WHERE checklist_template_id=:point'), params)


@pytest.mark.parametrize(('draft','mode'), [
    (True,'submit'), (False,'save'), (True,'stale'), (True,'foreign'), (True,'changed_file'),
    (True,'revoked'), (True,'parallel'), (True,'switch_in_flight'), (True,'ambiguous_chat'),
    (True,'named_chat'), (True,'followup'), (True,'ambiguous_phases'), (True,'wrong_phases'), (True,'two_tasks'),
    (True,'deadline_not_phase'),
], indirect=['draft'])
def test_confirm_photos_and_conditionally_submit(monkeypatch, draft, jobs, mode):
    engine, app, task, attempt, point = draft
    class Provider:
        def tool_chat(self, messages, tools, tokens):
            if messages[-1]['role'] == 'user':
                if 'Сначала посмотри эти кадры' in messages[-1]['content']:
                    return dict(content='Снимки получены.')
                assert 'propose_report_attach_and_submit' in {t['function']['name'] for t in tools}
                if mode in ('named_chat','ambiguous_chat','two_tasks'):
                    return dict(tool_calls=[*call('read_work_order',task_id=str(task))['tool_calls'],
                                            *call('propose_report_attach_and_submit',task_id=str(task),**payload)['tool_calls']])
                return call('propose_report_attach_and_submit', task_id=str(task), **payload)
            return dict(content='Проверьте действие.')

    v4(monkeypatch, app, Provider)
    monkeypatch.setitem(app.state._state, 'automatic_photo_review', lambda *_: None)
    with closing(login(app, 'executor')) as client, closing(login(app, 'engineer')) as engineer:
        url = f'{PREFIX}/ui/tasks/{task}'
        initial = client.get(url).json()
        assert initial['execution']['id'] == str(attempt)
        created = client.post(B+'/conversations', json={} if mode in ('named_chat','ambiguous_chat','two_tasks') else {'subject_task_id':str(task)})
        assert created.status_code==201, created.text
        chat = created.json()['conversation_id']
        sent = [image(client, chat, 'before.png', 'red'), image(client, chat, 'after.png', 'blue')]
        other_id = image(client, thread(client), 'foreign.png')['attachment_id'] if mode == 'foreign' else None
        ids = [row['attachment_id'] for row in sent]
        payload = dict(expected_revision=initial['task']['revision'], execution_id=str(attempt), photos=[
            dict(attachment_id=identity, checklist_item_id=str(point), phase=phase, view_key='front')
            for identity, phase in zip([other_id or ids[0], ids[1]],
                                       ('after','before') if mode=='wrong_phases' else ('before','after'))
        ])

        if mode=='followup':
            assert send(client,chat,ids,'Сначала посмотри эти кадры').status_code==202
            assert not client.get(f'{B}/conversations/{chat}').json()['actions']
        question=('Прикрепи эти фото до и после и сдай отчёт.' if mode=='ambiguous_phases' else
                  'Прикрепи фото 1 — до работы, фото 2 — после работы, и сдай отчёт.')
        if mode=='deadline_not_phase':
            question='Прикрепи фото 1 и сдай отчёт до пятницы, фото 2 — после работы.'
        if mode=='named_chat':
            question+=f" Код наряда: {initial['task']['code']}."
        if mode=='two_tasks':
            another=jobs[2]()
            with engine.begin() as db:
                db.execute(text("""INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
                    SELECT site_id,:another,user_id,assigned_by FROM work_assignments WHERE work_order_id=:task"""),
                    {'another':another,'task':task})
            question+=f" Коды нарядов: {initial['task']['code']}, {str(another)[:8]}."
        assert send(client, chat, [] if mode=='followup' else ids, question).status_code == 202
        history = client.get(f'{B}/conversations/{chat}').json()
        assert history['turns'][-1]['status'] == 'completed', history['turns'][-1]
        assert not client.get(url).json()['execution']['photos']
        if mode in ('foreign','ambiguous_chat','ambiguous_phases','wrong_phases','two_tasks','deadline_not_phase'):
            assert history['actions'] == []
            return
        action, = history['actions']
        assert action['tool_name'] == 'report_attach_and_submit'
        assert action['status'] == 'proposed' and 'before.png' in action['explanation']
        direct = client.post(f'{B}/workspace/tasks/{task}/attach-and-submit', json=payload)
        assert direct.status_code == 403
        if mode == 'stale':
            with engine.begin() as db:
                db.execute(text('UPDATE work_orders SET revision=revision+1 WHERE work_order_id=:task'), dict(task=task))
            assert confirm(client, action).status_code == 409
            assert not client.get(url).json()['execution']['photos']
            return
        if mode == 'revoked':
            with engine.begin() as db:
                db.execute(text("UPDATE work_assignments SET status='cancelled' WHERE work_order_id=:task"), {'task':task})
            assert confirm(client,action).status_code in (403,404)
            assert not engineer.get(url).json()['execution']['photos']
            return
        if mode == 'changed_file':
            with engine.connect() as db:
                key=db.scalar(text('SELECT storage_key FROM assistant_attachments WHERE attachment_id=:id'), {'id':ids[1]})
            safe_storage_path(app.state.settings.photo_storage_root,key).write_bytes(b'changed')
            rejected=confirm(client,action).json()
            assert rejected['status']=='failed', rejected
            assert not client.get(url).json()['execution']['photos']
            return
        if mode == 'switch_in_flight':
            from app import main
            from app.security.sessions import COOKIE, digest
            original=main.validate_upload
            def revoke_during_photo_validation(*args):
                with engine.begin() as db:
                    db.execute(text('DELETE FROM fixrate_sessions WHERE token_hash=:token'),
                               {'token':digest(client.cookies[COOKIE])})
                return original(*args)
            monkeypatch.setattr(main,'validate_upload',revoke_during_photo_validation)
            rejected=confirm(client,action).json()
            assert rejected['status']=='failed', rejected
            assert not engineer.get(url).json()['execution']['photos']
            return
        if mode == 'parallel':
            gate=Barrier(2)
            def confirm_at_once(worker):
                gate.wait(timeout=10)
                return confirm(worker, action)
            with closing(login(app,'executor')) as second_client, ThreadPoolExecutor(max_workers=2) as pool:
                responses=list(pool.map(confirm_at_once,(client,second_client)))
            assert all(r.status_code==200 for r in responses)
            assert {r.json()['status'] for r in responses} <= {'executing','succeeded'}
            first=confirm(client,action)
        else:
            first = confirm(client, action)
        assert first.status_code == 200, first.text
        done = first.json()
        assert done['status'] == 'succeeded', done
        assert done['result']['verification']['status'] == 'confirmed', done
        assert confirm(client, action).json() == done
        result = engineer.get(url).json()
        assert result['task']['revision'] == initial['task']['revision'] + 1
        assert result['task']['state'] == ('in_progress' if mode == 'save' else 'submitted')
        assert result['execution']['id'] == str(attempt)
        assert sorted(p['phase'] for p in result['execution']['photos']) == ['after', 'before']
        assert done['result']['data']['submission'] == ('draft_incomplete' if mode == 'save' else 'submitted')
        if mode == 'save':
            assert 'чек-лист' in done['result']['data']['submission_block'].lower()
        if mode == 'submit':
            public_tools=rpc(client,'tools/list').json()['result']['tools']
            assert 'report_attach_and_submit' not in {tool['name'] for tool in public_tools}
            class ArchiveProvider:
                def tool_chat(self, messages, tools, tokens):
                    if not any(m['role']=='tool' for m in messages):
                        return call('read_report_photos',task_id=str(task))
                    return dict(content='Снимки отчёта.')
            monkeypatch.setitem(app.state._state,'assistant_provider_factory',ArchiveProvider)
            archive_chat=thread(engineer)
            assert send(engineer, archive_chat, [], 'Покажи фото отчёта.').status_code==202
            trace=engineer.get(f'{B}/conversations/{archive_chat}').json()['turns'][-1]['trace']
            assert {row['resource']['url'] for row in trace if row.get('resource')}=={
                f"{PREFIX}/photos/{photo['id']}/content" for photo in result['execution']['photos']}
