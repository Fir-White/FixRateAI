"""Executor workflow postconditions from the report, checklist and review tables."""
import json
import os

import pytest
from sqlalchemy import text

from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab
from tests.backend.test_assistant import B, assistant_case, confirm
from tests.backend.test_assistant_task_execution import Chat, review
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


def persisted(engine, task):
    with engine.connect() as db:
        return db.execute(text('''SELECT w.status AS task_state,w.revision,r.work_report_id::text AS report_id,
              r.status AS report_state,r.submitted_at,r.comment,r.submitted_by::text AS author,
              (SELECT jsonb_object_agg(c.checklist_template_id::text,c.response_value->>'answer')
               FROM checklist_results c WHERE c.work_report_id=r.work_report_id) AS answers,
              (SELECT a.decision FROM acceptance_reviews a WHERE a.work_report_id=r.work_report_id) AS decision
              FROM work_orders w LEFT JOIN work_reports r USING(site_id,work_order_id)
              WHERE w.work_order_id=:task'''), {'task': task}).mappings().one()


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('mode', ['submit', 'missing-photo', 'missing-act', 'decline-draft', 'accept', 'return'])
def test_executor_report_to_review(lab, mode):
    fixture, _, _, worker, data, _, clients = lab
    engine, _, _, _, ids = fixture
    user = clients['executor']
    title = 'Сверить уставки защиты'
    task = next(row['id'] for row in data['work'].values() if row['snapshot'].get('title') == title)
    with engine.begin() as db:
        item = db.scalar(text('''SELECT c.checklist_template_id::text FROM checklist_templates c
                 JOIN maintenance_rules m USING(site_id,operation_template_id)
                 JOIN rule_equipment b USING(site_id,maintenance_rule_id)
                 WHERE b.site_id=:site AND b.equipment_id=:asset LIMIT 1'''),
                         dict(ids, asset=data['equipment']['КА-21']['id']))
        assert item
        config = {'checklist': [dict(id=item, text='Лампа готовности горит', answerKind='boolean',
                                     required=True, photoRequired=mode == 'missing-photo')]}
        if mode == 'missing-act':
            config['required_acts'] = ['Акт проверки цепей']
        db.execute(text('''UPDATE work_orders SET operation_snapshot=operation_snapshot||CAST(:config AS jsonb)
                           WHERE work_order_id=:task'''), {'task': task, 'config': json.dumps(config)})
    initial = persisted(engine, task)
    chat = Chat(user)
    reply = chat.send(f'Новое задание — «{title}». Начни работу на посту КА-21, '
                      'заполни чек-лист и отправь отчёт инженеру на приёмку.')
    assert reply['execution_engine'] == 'v3' and reply['workflow']['outcome'] == 'awaiting_confirmation'
    assert persisted(engine, task) == initial
    chat.approve('task_start')
    draft = persisted(engine, task)
    assert (draft['task_state'], draft['report_state'], draft['author']) == ('in_progress', 'draft', worker)
    chat.send(resume=True)
    facts = chat.send('Факты:\n1: выполнено\nОписание: Проверка индикации закончена', resume=True)
    assert facts['workflow']['outcome'] == 'awaiting_confirmation'
    proposal = chat.proposed('report_save')
    assert persisted(engine, task) == draft
    if mode == 'decline-draft':
        rejected = user.post(f'{B}/actions/{proposal["action_id"]}/reject')
        assert rejected.status_code == 200 and rejected.json()['status'] == 'rejected'
        assert persisted(engine, task) == draft
        return
    chat.approve('report_save')
    saved = persisted(engine, task)
    assert saved['report_id'] == draft['report_id'] and saved['answers'] == {item: 'done'}
    assert saved['comment'] == 'Проверка индикации закончена' and saved['submitted_at'] is None
    resumed = chat.send(resume=True)
    if mode in ('missing-photo', 'missing-act'):
        assert resumed['workflow']['outcome'] == 'awaiting_input'
        block = 'фото до и после' if mode == 'missing-photo' else 'Акт проверки цепей'
        assert block in resumed['answer']
        assert all(action['tool_name'] != 'report_submit' for action in chat.view()['actions'])
        assert persisted(engine, task) == saved
        return
    submit = chat.approve('report_submit')
    sent = persisted(engine, task)
    assert (sent['task_state'], sent['report_state']) == ('in_review', 'submitted')
    assert sent['report_id'] == saved['report_id'] and sent['submitted_at'] is not None
    assert confirm(user, submit).json()['status'] == 'succeeded' and persisted(engine, task) == sent
    if mode in ('accept', 'return'):
        verdict = 'accepted' if mode == 'accept' else 'rejected'
        review(clients['engineer'], task, verdict)
        reviewed = persisted(engine, task)
        assert reviewed['report_id'] == sent['report_id']
        assert reviewed['decision'] == ('accepted' if mode == 'accept' else 'rework')
        assert reviewed['task_state'] == ('completed' if mode == 'accept' else 'rework')
