"""Executor-to-engineer workflow over the regular HTTP and PostgreSQL entry points."""
from contextlib import closing
from datetime import datetime
import json
import os
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.integration.demo import demo_id
from tests.backend.test_assistant import B, confirm, thread
from tests.backend.test_runtime_integration import ASSIGNMENT_TASK, PREFIX, assignment_search, login, runtime


TITLE = 'Контроль давления и температуры ГВС — корпус 2'
PROMPT = ('Новое задание — «{title}». Войдите как исполнитель, начните работу{post}, '
          'заполните чек-лист и отправьте отчёт инженеру на приёмку.')
ITEM = str(demo_id('runtime-checklist'))


@pytest.fixture
def scenario(runtime, monkeypatch):
    engine, app = runtime

    def unexpected_provider():
        pytest.fail('A server-owned task workflow used an inference provider')

    monkeypatch.setattr(app.state, 'assistant_provider_factory', unexpected_provider, raising=False)
    orders = []

    def create(*, title=None, assigned=True, links=True, state='assigned', photo=False, snapshot=None):
        identity = uuid4()
        title = title or f'{TITLE} {identity.hex[:6]}'
        checklist = [{'id': ITEM, 'text': 'Контроль выполнен', 'answerKind': 'boolean',
                      'required': True, 'photoRequired': photo, 'unit': None, 'visualVerifiability': 'visible'}]
        with engine.begin() as conn:
            source = conn.execute(text('SELECT site_id,system_id FROM work_orders WHERE work_order_id=:id'),
                                  {'id': demo_id('runtime-order')}).mappings().one()
            values = dict(source, id=identity, state=state, executor=demo_id('user-1'),
                          dispatcher=demo_id('dispatcher'), equipment=demo_id('equipment-2'),
                          snapshot=json.dumps({'title': title, 'checklist': checklist, **(snapshot or {})}))
            conn.execute(text("""INSERT INTO work_orders(work_order_id,site_id,system_id,origin,status,
                required_people_snapshot,norm_hours_snapshot,operation_snapshot)
                VALUES(:id,:site_id,:system_id,'manual',:state,1,1,CAST(:snapshot AS jsonb))"""), values)
            if assigned:
                conn.execute(text("""INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
                    VALUES(:site_id,:id,:executor,:dispatcher)"""), values)
            if links:
                conn.execute(text("""INSERT INTO work_order_equipment(site_id,system_id,work_order_id,equipment_id)
                    VALUES(:site_id,:system_id,:id,:equipment)"""), values)
            code = conn.scalar(text('SELECT asset_code FROM equipment WHERE equipment_id=:equipment'), values)
        orders.append(identity)
        return str(identity), title, code

    try:
        with closing(login(app, 'executor')) as executor, closing(login(app, 'engineer')) as engineer:
            yield engine, executor, engineer, create
    finally:
        with engine.begin() as conn:
            for table in ('maintenance_notifications', 'acceptance_reviews', 'checklist_results', 'work_readings',
                          'evidence_files', 'work_reports', 'work_assignments', 'work_order_equipment', 'work_orders'):
                conn.execute(text(f'DELETE FROM {table} WHERE work_order_id=ANY(CAST(:ids AS uuid[]))'), {'ids': orders})


class Chat:
    def __init__(self, client):
        self.client = client
        self.identity = thread(client)
        self.turn = None

    def send(self, content='Продолжить сохранённое поручение.', *, resume=False, key=None):
        command = {'content': content, 'idempotency_key': key or str(uuid4()), 'attachment_ids': []}
        if resume:
            command['resume_turn_id'] = self.turn
        response = self.client.post(B + f'/conversations/{self.identity}/messages', json=command)
        assert response.status_code == 202, response.text
        self.turn = response.json()['turn_id']
        turn = next(item for item in self.view()['turns'] if item['turn_id'] == self.turn)
        assert turn['status'] == 'completed', turn
        return turn

    def view(self):
        response = self.client.get(B + '/conversations/' + self.identity)
        assert response.status_code == 200, response.text
        return response.json()

    def proposed(self, tool):
        actions = [a for a in self.view()['actions'] if a['status'] == 'proposed']
        assert len(actions) == 1 and actions[0]['tool_name'] == tool, actions
        return actions[0]

    def approve(self, tool):
        action = self.proposed(tool)
        response = confirm(self.client, action)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['status'] == 'succeeded' and result['result']['verification']['status'] == 'confirmed', result
        return action


def task(client, identity):
    result = client.get(PREFIX + f'/ui/tasks/{identity}')
    assert result.status_code == 200, result.text
    return result.json()


def workflow_step(turn, phase):
    return next(goal for goal in turn['workflow']['goals'] if goal['id'] == phase)


def begin(executor, create, **kwargs):
    identity, title, code = create(**kwargs)
    return identity, open_task_workflow(executor, identity, title, code)


def open_task_workflow(executor, identity, title, code):
    chat = Chat(executor)
    initial = chat.send(PROMPT.format(title=title, post=f' на посту {code}' if code else ''))
    assert [g['id'] for g in initial['workflow']['goals']] == ['task', 'start', 'checklist', 'draft', 'submit']
    assert initial['workflow']['outcome'] == 'awaiting_confirmation', initial
    assert task(executor, identity)['task']['state'] == 'assigned'
    return chat


def start(chat):
    chat.approve('task_start')
    resumed = chat.send(resume=True)
    assert resumed['workflow']['outcome'] == 'awaiting_input', resumed
    assert 'Контроль выполнен' in resumed['answer']
    return resumed


def review(engineer, identity, verdict):
    bundle = task(engineer, identity)
    assert bundle['task']['state'] == 'submitted'
    assert 'review' not in bundle['allowedActions']
    route = PREFIX + f'/tasks/{identity}/review'
    payload = {
        'expected_revision': bundle['task']['revision'], 'execution_id': bundle['execution']['id'],
        'verdict': verdict, 'reason': 'Проверка согласованного результата',
    }
    assert engineer.post(route, json=payload).status_code == 403
    assert task(engineer, identity)['task']['revision'] == bundle['task']['revision']
    with closing(login(engineer.app, 'chief_engineer')) as chief:
        assert 'review' in task(chief, identity)['allowedActions']
        result = chief.post(route, json=payload)
        assert result.status_code == 200, result.text
        return result.json()


def assign_fresh_order(engine, app, identity):
    """Reuse the disposable qualified crew and apply the actual preview command as dispatcher."""
    today = datetime.now(ZoneInfo('Asia/Yekaterinburg')).date().isoformat()
    with engine.begin() as conn:
        conn.execute(text("""UPDATE work_orders AS target SET
            maintenance_rule_id=source.maintenance_rule_id,required_people_snapshot=source.required_people_snapshot,
            norm_hours_snapshot=source.norm_hours_snapshot,norm_hours_basis_snapshot=source.norm_hours_basis_snapshot,
            regulatory_deadline_at=source.regulatory_deadline_at,
            operation_snapshot=source.operation_snapshot || target.operation_snapshot ||
                jsonb_build_object('earliest_date',CAST(:today AS text))
            FROM work_orders AS source WHERE source.work_order_id=:source AND target.work_order_id=:task"""),
            {'source': ASSIGNMENT_TASK, 'task': identity, 'today': today})
    with closing(login(app, 'dispatcher')) as dispatcher:
        _, body = assignment_search(dispatcher)
        preview = dispatcher.post(PREFIX + f'/tasks/{identity}/assignment-preview', json=body)
        assert preview.status_code == 200 and preview.json()['command'], preview.text
        assigned = dispatcher.post(PREFIX + f'/tasks/{identity}/assign',
                                   json={**preview.json()['command'], 'crew_id': preview.json()['crewId']})
        assert assigned.status_code == 200, assigned.text


@pytest.mark.parametrize('verdict', ['accepted', 'rejected'])
def test_full_task_to_engineer(scenario, verdict):
    engine, executor, engineer, create = scenario
    with closing(TestClient(executor.app)) as newly_assigned:
        if verdict == 'accepted':
            identity, title, code = create(assigned=False, state='draft')
            assert executor.get(PREFIX + f'/ui/tasks/{identity}').status_code == 404
            assign_fresh_order(engine, executor.app, identity)
            signed_in = newly_assigned.post('/api/v1/auth/login', json={
                'email': 'fixrate-assignment-1@example.test', 'password': os.environ['FIXRATE_TEST_PASSWORD'],
            })
            assert signed_in.status_code == 200, signed_in.text
            newly_assigned.headers['X-CSRF-Token'] = signed_in.json()['csrfToken']
            complete_task_to_engineer(engine, newly_assigned, engineer, identity,
                                      open_task_workflow(newly_assigned, identity, title, code), verdict)
        else:
            identity, chat = begin(executor, create)
            complete_task_to_engineer(engine, executor, engineer, identity, chat, verdict)


def complete_task_to_engineer(engine, executor, engineer, identity, chat, verdict):
    start(chat)
    entered = chat.send('Факты:\n1: выполнено\nОписание: Результат испытательного осмотра', resume=True)
    assert entered['workflow']['outcome'] == 'awaiting_confirmation'
    proposal = chat.proposed('report_save')
    assert proposal['arguments']['body']['answers'] == {ITEM: 'done'}
    assert task(executor, identity)['execution']['checklist'][0]['answer'] is None
    chat.approve('report_save')
    submission = chat.send(resume=True)
    assert submission['workflow']['outcome'] == 'awaiting_confirmation'
    assert task(executor, identity)['task']['state'] == 'in_progress'
    chat.approve('report_submit')
    final = chat.view()['turns'][-1]
    assert final['workflow']['outcome'] == 'completed'
    assert 'на приёмке' in final['answer']
    assert task(engineer, identity)['task']['state'] == 'submitted'
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT status FROM work_orders WHERE work_order_id=:id'), {'id': identity}) == 'in_review'
    reviewed = review(engineer, identity, verdict)
    assert reviewed['task']['state'] == ('accepted' if verdict == 'accepted' else 'rework_required')


@pytest.mark.parametrize(('case', 'reason'), [
    ('wrong_role', 'executor_role_required'),
    ('unassigned_executor', 'task_not_visible'),
    ('unknown_id', 'task_not_visible'),
    ('unknown_title', 'task_not_visible'),
    ('duplicate_title', 'task_ambiguous'),
    ('wrong_post', 'equipment_mismatch'),
    ('missing_equipment', 'equipment_mismatch'),
    ('id_title_mismatch', 'task_title_mismatch'),
    ('missing_selector', 'task_selection_required'),
    ('explicit_site_switch', 'task_selection_required'),
    ('negated_submission', 'task_selection_required'),
    ('conditional_start', 'task_selection_required'),
    ('empty_checklist', 'task_start_unavailable'),
    ('cancelled_order', 'task_start_unavailable'),
])
def test_task_workflow_stops_before_writes(scenario, case, reason):
    _, executor, engineer, create = scenario
    identity, title, code = create(
        assigned=case != 'unassigned_executor', links=case != 'missing_equipment',
        state='cancelled' if case == 'cancelled_order' else 'assigned',
        snapshot={'checklist': []} if case == 'empty_checklist' else None,
    )
    if case == 'duplicate_title':
        create(title=title)
    command = PROMPT.format(title='Чужое название' if case in ('unknown_title', 'id_title_mismatch') else title,
                            post=f' на посту {code}')
    if case == 'wrong_post':
        command = command.replace(code, 'ПР-999')
    if case == 'unknown_id':
        command = command.replace(f'«{title}»', str(uuid4()))
    if case == 'id_title_mismatch':
        command = f'{identity}. {command}'
    if case == 'missing_selector':
        command = command.replace(f'«{title}»', '')
    if case == 'explicit_site_switch':
        command = 'Переключитесь на другое здание. ' + command
    if case == 'negated_submission':
        command = command.replace('и отправьте', 'и не отправляйте')
    if case == 'conditional_start':
        command = command.replace('начните работу', 'если возможно, начните работу')
    chat = Chat(engineer if case == 'wrong_role' else executor)
    turn = chat.send(command)
    assert turn['workflow']['outcome'] == 'blocked', turn
    stopped = [goal for goal in turn['workflow']['goals'] if goal['status'] == 'blocked']
    assert len(stopped) == 1 and stopped[0]['reason'] == reason and stopped[0]['message'], stopped
    assert not chat.view()['actions']
    assert task(engineer, identity)['execution'] is None


@pytest.mark.parametrize(('case', 'reason'), [
    ('reject', 'action_rejected'), ('expired', 'action_expired_request_fresh_proposal'),
    ('stale', 'action_stale'), ('uncertain', 'read_only_reconciliation_required'),
])
def test_start_proposal_is_never_replayed(scenario, case, reason):
    engine, executor, _, create = scenario
    identity, chat = begin(executor, create)
    proposal = chat.proposed('task_start')
    if case == 'reject':
        response = executor.post(B + f"/actions/{proposal['action_id']}/reject")
        assert response.status_code == 200, response.text
    elif case == 'stale':
        with engine.begin() as db:
            db.execute(text('UPDATE work_orders SET revision=revision+1 WHERE work_order_id=:id'), {'id': identity})
        assert confirm(executor, proposal).status_code == 409
    else:
        with engine.begin() as db:
            if case == 'expired':
                db.execute(text("UPDATE assistant_actions SET expires_at=now()-interval '1 minute' WHERE action_id=:id"), {'id': proposal['action_id']})
            else:
                db.execute(text("UPDATE assistant_actions SET status='uncertain' WHERE action_id=:id"), {'id': proposal['action_id']})
    turn = chat.send(resume=True)
    assert workflow_step(turn, 'start')['reason'] == reason
    assert len(chat.view()['actions']) == 1
    assert task(executor, identity)['task']['state'] == 'assigned'


@pytest.mark.parametrize(('facts', 'reason'), [
    ('Факты:\n4: выполнено', 'invalid_report_facts'),
    ('Факты:\n1: сделай сам', 'invalid_report_facts'),
    ('Факты:\n1: выполнено\n1: не выполнено', 'invalid_report_facts'),
    ('Факты: {"answers":{"1":"выполнено"},"photos":[]}', 'invalid_report_facts'),
])
def test_invalid_or_ambiguous_facts_do_not_create_action(scenario, facts, reason):
    _, executor, _, create = scenario
    identity, chat = begin(executor, create)
    start(chat)
    turn = chat.send(facts, resume=True)
    assert workflow_step(turn, 'draft')['reason'] == reason
    assert len(chat.view()['actions']) == 1
    assert task(executor, identity)['execution']['checklist'][0]['answer'] is None


def test_repeated_confirmation_and_additional_facts(scenario):
    _, executor, _, create = scenario
    identity, chat = begin(executor, create)
    first = chat.approve('task_start')
    first_revision = task(executor, identity)['task']['revision']
    repeated = confirm(executor, first)
    assert repeated.status_code == 200 and repeated.json()['status'] == 'succeeded'
    assert task(executor, identity)['task']['revision'] == first_revision
    chat.send(resume=True)
    chat.send('Факты:\n1: не выполнено', resume=True)
    chat.approve('report_save')
    pending = chat.send(resume=True)
    assert workflow_step(pending, 'draft')['status'] == 'awaiting_input'
    assert task(executor, identity)['execution']['checklist'][0]['answer'] == 'not_done'
    chat.send('Факты:\n1: выполнено', resume=True)
    chat.approve('report_save')
    chat.send(resume=True)
    chat.approve('report_submit')
    assert task(executor, identity)['task']['state'] == 'submitted'


def test_required_photos_measurement_act_and_time(scenario):
    _, executor, _, create = scenario
    identity, chat = begin(executor, create, photo=True, snapshot={
        'methodology_ref': 'Проверочная методика',
        'required_acts': ['Акт проверки'],
        'measurement_requirements': [{'parameter_code': 'pressure', 'unit': 'bar', 'phases': ['after']}],
    })
    start(chat)
    chat.send('Факты:\n1: выполнено', resume=True)
    chat.approve('report_save')
    turn = chat.send(resume=True)
    assert turn['workflow']['outcome'] == 'awaiting_input'
    for expected in ('фото до и после', 'Акт проверки', 'pressure (bar)', 'Фактические трудозатраты'):
        assert expected in turn['answer']
    assert task(executor, identity)['task']['state'] == 'in_progress'
    assert not any(action['tool_name'] == 'report_submit' for action in chat.view()['actions'])


def test_native_form_and_resumed_submission(scenario):
    _, executor, _, create = scenario
    identity, chat = begin(executor, create)
    start(chat)
    draft = task(executor, identity)
    saved = executor.put(PREFIX + f'/tasks/{identity}/report', json=dict(
        expected_revision=draft['task']['revision'], narrative='Внесено в карточке', answers={ITEM: 'done'}))
    assert saved.status_code == 200, saved.text
    resumed = chat.send(resume=True)
    assert workflow_step(resumed, 'draft')['status'] == 'completed'
    chat.approve('report_submit')
    assert task(executor, identity)['execution']['narrative'] == 'Внесено в карточке'
    assert [a['tool_name'] for a in chat.view()['actions']] == ['task_start', 'report_submit']


def test_existing_draft_and_partial_requested_workflow(scenario):
    _, executor, _, create = scenario
    identity, _, _ = create()
    initial = task(executor, identity)
    started = executor.post(PREFIX + f'/tasks/{identity}/start', json={'expected_revision': initial['task']['revision']})
    assert started.status_code == 200, started.text
    chat = Chat(executor)
    result = chat.send(f'Начните задание {identity} и заполните чек-лист.')
    assert [g['id'] for g in result['workflow']['goals']] == ['task', 'start', 'checklist', 'draft']
    assert workflow_step(result, 'start')['status'] == 'completed'
    chat.send('Факты:\n1: выполнено', resume=True)
    chat.approve('report_save')
    assert chat.send(resume=True)['workflow']['outcome'] == 'completed'
    final = task(executor, identity)
    assert final['task']['state'] == 'in_progress' and final['execution']['checklist'][0]['answer'] == 'done'


def test_resume_retry_keeps_one_turn_and_proposal(scenario):
    _, executor, _, create = scenario
    identity, chat = begin(executor, create)
    start(chat)
    root = chat.turn
    key = str(uuid4())
    content = 'Факты:\n1: выполнено'
    saved = chat.send(content, resume=True, key=key)
    chat.turn = root
    repeated = chat.send(content, resume=True, key=key)
    assert repeated['turn_id'] == saved['turn_id']
    assert len(chat.view()['turns']) == 3
    assert chat.proposed('report_save')
    assert task(executor, identity)['execution']['checklist'][0]['answer'] is None


def test_another_role_cannot_continue_or_confirm(scenario):
    _, executor, engineer, create = scenario
    identity, chat = begin(executor, create)
    action = chat.proposed('task_start')
    denied = engineer.post(B + f'/conversations/{chat.identity}/messages', json={
        'content': 'Продолжить сохранённое поручение.', 'idempotency_key': str(uuid4()), 'resume_turn_id': chat.turn,
    })
    assert denied.status_code == 404
    assert confirm(engineer, action).status_code == 404
    assert task(engineer, identity)['task']['state'] == 'assigned'
    start(chat)
