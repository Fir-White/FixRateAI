"""Drive the experimental operator through the public chat and confirmation routes."""
from dataclasses import replace
import json

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from agent_reliability_lab.evals.test_agent_v3_e2e import lab
from agent_reliability_lab.evals.test_maintenance_conversation import schedule
from agent_reliability_lab.evals.test_pipeline_comparison import pipeline_fixture
from tests.backend.test_assistant import assistant_case, confirm
from tests.backend.test_assistant_architecture_v2 import stored, turn
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


def configure(app, monkeypatch, provider):
    monkeypatch.setattr(app.state, 'settings', replace(app.state.settings, assistant_agent_version='v3',
                                                      assistant_v3_pipeline='erp_operator'))
    monkeypatch.setattr(app.state, 'assistant_provider_factory', provider, raising=False)


class Scripted:
    response_model = 'test:erp-operator'

    def __init__(self, decide):
        self.decide = decide

    def chat(self, messages, schema, _budget):
        result = {'arguments_json': '{}', 'presentation': 'continue',
                  'result_source': '', **self.decide(json.loads(messages[-1]['content']))}
        # A provider could return a tool outside the advertised enum.
        return (schema.__base__ if result['tool'] == 'task_assign' else schema).model_validate(result)


def test_task_patch_keeps_scope_and_local_day_in_later_messages(pipeline_fixture, monkeypatch):
    fixture, clients, _, days, _ = pipeline_fixture
    target_day = str(days['tomorrow'])
    next_day = str(days['next_day'])
    mutations = []

    def decide(ctx):
        question = ctx['question']
        if question == 'Какие установки без принятого ТО?':
            return dict(tool='equipment_find', result_source='equipment_find', presentation='items',
                        task_delta=dict(mode='new', source='equipment_find', set={'accepted_maintenance': 'none'}))
        selected_delta = dict(source='tasks_find')
        issued = {}
        if question == 'На завтра покажи назначенные по этой группе.':
            selected_delta.update(set=dict(period='all', state='assigned', starts_on=target_day,
                                           ends_on=target_day, scheduled_only=True))
        elif question == 'Оставь только один самый ранний.':
            selected_delta.update(set=dict(limit=1))
            if not ctx['failures']:
                # A model attempts to broaden the scope and replace a saved date.
                issued = dict(query=dict(equipment_accepted_maintenance='present', starts_on=next_day))
            else:
                mutations.append(ctx['failures'][-1]['status'])
        elif question == 'На день позже.':
            selected_delta.update(set=dict(starts_on=next_day, ends_on=next_day))
        else:
            assert question == 'Новая задача: посчитай черновики на завтра.'
            selected_delta.update(mode='new', set=dict(period='all', state='draft',
                                                       starts_on=target_day, ends_on=target_day))
        return dict(tool='tasks_find', result_source='tasks_find',
                    task_delta=selected_delta if ctx['task'] is None else None, arguments_json=json.dumps(issued),
                    presentation='count' if selected_delta.get('mode') == 'new' else 'items')

    configure(fixture[1], monkeypatch, lambda: Scripted(decide))
    client = clients['chief_engineer']
    first, _, chat = turn(client, 'Какие установки без принятого ТО?')
    second, _, _ = turn(client, 'На завтра покажи назначенные по этой группе.', chat=chat)
    third, _, _ = turn(client, 'Оставь только один самый ранний.', chat=chat)
    fourth, _, _ = turn(client, 'На день позже.', chat=chat)
    fifth, _, _ = turn(client, 'Новая задача: посчитай черновики на завтра.', chat=chat)
    assert mutations == [422]
    states = [stored(fixture, result['turn_id']) for result in (first, second, third, fourth, fifth)]
    assert all(result['outcome'] == 'completed' for result in states)
    identities = [state['erp_operator']['task']['task_id'] for state in states]
    assert len(set(identities[:4])) == 1 and identities[4] != identities[0]
    for state, day in ((states[2], target_day), (states[3], next_day)):
        proof = state['evidence'][0]
        query = proof['arguments']['query']
        assert query == dict(limit=1, period='all', state='assigned', starts_on=day, ends_on=day,
                             equipment_accepted_maintenance='none', scheduled_only=True)
        # Compute the expected row by querying the test ledger's underlying data.
        with fixture[0].connect() as database:
            first_id = database.scalar(text('''
                SELECT o.work_order_id FROM work_orders o JOIN work_order_equipment l USING(site_id,work_order_id)
                JOIN equipment e USING(site_id,equipment_id)
                WHERE o.site_id=:site AND o.status='assigned'
                AND (o.planned_start_at AT TIME ZONE 'Asia/Yekaterinburg')::date=CAST(:day AS date)
                AND e.asset_code IN ('КС-62','КС-64','КС-65','КС-66')
                ORDER BY o.planned_start_at,o.work_order_id LIMIT 1
            '''), dict(site=fixture[-1]['site'], day=day))
        assert [item['id'] for item in proof['result']['items']] == [str(first_id)]
    assert 'equipment_accepted_maintenance' not in states[4]['evidence'][0]['arguments']['query']


def test_operator_assignment_requires_user_confirmation_and_rechecks(assistant_case, request, monkeypatch):
    app = assistant_case[1]
    # The lab needs the v3 graph/checkpointer at startup.
    monkeypatch.setattr(app.state, 'settings', replace(app.state.settings, assistant_agent_version='v3'))
    fixture_data = request.getfixturevalue('lab')
    fixture, _, _, _, _, _, clients = fixture_data
    task_id, _, _, worker = schedule(fixture_data)

    def decide(ctx):
        results = ctx['results']
        if 'Ничего не меняй' in ctx['question']:
            return dict(tool='task_assign', task_delta=dict(mode='new', operation='change')) if not ctx['failures'] else dict(tool='clarify')
        if not results:
            return dict(tool='tasks_find', task_delta=dict(mode='new', operation='change', source='tasks_find',
                set=dict(state='draft', maintenance_only=True, unassigned_only=True, starts_on=ctx['tomorrow'],
                         ends_on=ctx['tomorrow'], limit=1)))
        order = results[0]['result']['items'][0]
        path = dict(task_id=order['id'])
        if len(results) == 1:
            return dict(tool='assignment_context', arguments_json=json.dumps(dict(path=path)))
        if len(results) == 2:
            return dict(tool='assignment_preview', arguments_json=json.dumps(dict(path=path,
                body=dict(expected_revision=results[1]['result']['expectedRevision'],
                          start_local=order['scheduledStart'][:19], end_local=order['scheduledEnd'][:19]))))
        return dict(tool='task_assign', receipt=results[-1]['receipt'])

    configure(app, monkeypatch, lambda: Scripted(decide))
    chief = clients['chief_engineer']
    denied, cards, _ = turn(chief, 'Кто свободен для этого наряда? Ничего не меняй.')
    assert not cards and denied['workflow']['outcome'] == 'blocked'
    assert stored(fixture, denied['turn_id'])['erp_operator']['errors'][0]['status'] == 403
    proposal, cards, _ = turn(chief, 'Назначь свободного сотрудника на ближайшее свободное ТО завтра.')
    assert proposal['workflow']['outcome'] == 'awaiting_confirmation'
    action, = cards
    assert action['arguments']['path']['task_id'] == task_id
    assert action['arguments']['body']['executor_ids'] == [worker]
    engine, _, _, _, ids = fixture
    query = text('SELECT status,revision FROM work_orders WHERE work_order_id=:task')
    with engine.connect() as db:
        before = db.execute(query, dict(task=task_id)).one()
    assert before.status == 'draft'
    assert confirm(clients['executor'], action).status_code in (403, 404)
    monkeypatch.setenv('FIXRATE_ASSISTANT_V3_PIPELINE', 'v3')
    with TestClient(create_app(engine), cookies=chief.cookies,
                    headers={'X-CSRF-Token': chief.headers['X-CSRF-Token']}) as restarted:
        for _ in range(2):
            result = confirm(restarted, action)
            assert result.status_code == 200 and result.json()['status'] == 'succeeded', result.text
            assert result.json()['result']['verification']['status'] == 'confirmed'
    with engine.connect() as db:
        assert db.execute(query, dict(task=task_id)).one() == ('assigned', before.revision + 1)
        assert db.scalar(text('''SELECT count(*) FROM audit_events
            WHERE site_id=:site AND entity_id=:task AND action='assign' '''), {**ids, 'task': task_id}) == 1


def test_bounded_cohort_transfer_uses_sql_and_preserves_role_visibility(pipeline_fixture):
    _, clients, ledger, days, worker = pipeline_fixture
    workspace = '/api/v1/assistant/workspace/tasks'
    hidden = next(item['id'] for item in ledger['equipment'] if item['code'] == 'КС-66')
    visible = next(item['id'] for item in ledger['equipment'] if item['code'] == 'КС-62')
    day = days['tomorrow']
    expected = next(row['id'] for row in ledger['tasks'] if row['asset'] == visible and
                    row['status'] == 'assigned' and row['start'].date() == day and row['worker'] == worker)
    common = dict(state='assigned', starts_on=day, ends_on=day, period='all', sort='latest', limit=1)
    executor = clients['executor']
    for filters in (dict(equipment_ids=[visible, hidden]), dict(equipment_asset_code='КС-62'),
                    dict(equipment_q='Шкаф Рубин')):
        response = executor.get(workspace, params={**common, **filters})
        assert response.status_code == 200, response.text
        assert [row['id'] for row in response.json()['items']] == [expected]
    empty = executor.get(workspace, params={**common, 'equipment_ids': [hidden]})
    assert empty.status_code == 200 and empty.json()['total'] == 0
    conflict = executor.get(workspace, params={**common, 'equipment_id': visible, 'equipment_ids': [visible]})
    assert conflict.status_code == 422
