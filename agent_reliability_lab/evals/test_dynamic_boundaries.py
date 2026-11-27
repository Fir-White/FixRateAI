"""Tool-loop boundary checks with the real authorized ASGI and PostgreSQL."""
from dataclasses import replace
import json

from sqlalchemy import text

from app.assistant.dynamic_dialogue import Decision
from agent_reliability_lab.evals.test_agent_v3_e2e import lab
from agent_reliability_lab.evals.test_maintenance_conversation import schedule
from agent_reliability_lab.evals.test_pipeline_comparison import pipeline_fixture
from tests.backend.test_assistant import assistant_case, confirm
from tests.backend.test_assistant_architecture_v2 import stored, turn
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


def test_accepted_history_filter_and_next_order_share_role_and_date_scope(pipeline_fixture):
    _, clients, ledger, days, worker = pipeline_fixture
    workspace = '/api/v1/assistant/workspace'
    chief, executor = clients['chief_engineer'], clients['executor']
    for client, expected, visibility in ((chief, {'КС-62', 'КС-64', 'КС-65', 'КС-66'}, 'site'),
                                         (executor, {'КС-62', 'КС-64', 'КС-65'}, 'assigned_orders')):
        cohort = client.get(workspace+'/equipment', params={'accepted_maintenance': 'none'})
        assert cohort.status_code == 200, cohort.text
        value = cohort.json()
        assert {row['asset_code'] for row in value['items']} == expected, value
        assert value['history_basis']['visibility'] == visibility
        eligible = {row['id'] for row in ledger['equipment'] if row['code'] in expected}
        selected = next(row for row in ledger['tasks'] if row['asset'] in eligible and row['status'] == 'assigned'
                        and row['start'].date() == days['tomorrow'] and (client is chief or row['worker'] == worker))
        order = client.get(workspace+'/tasks', params=dict(equipment_accepted_maintenance='none', state='assigned',
            scheduled_only='true', starts_on=days['tomorrow'], ends_on=days['tomorrow'], limit=1))
        assert order.status_code == 200, order.text
        facts = order.json()
        assert [row['id'] for row in facts['items']] == [selected['id']]
        assert facts['filters']['equipment_accepted_maintenance'] == 'none'
        assert facts['history_basis']['visibility'] == visibility


class Decisions:
    def __init__(self, escalation_attempt=False):
        self.escalation_attempt = escalation_attempt
        self.response_model = 'test:typed-dynamic-decisions'

    def chat(self, messages, schema, budget):
        payload = json.loads(messages[-1]['content'])
        results = payload['results']
        tool, arguments, receipt, help_kind = 'tasks_find', {}, '', ''
        if self.escalation_attempt:
            assert 'task_assign' not in payload['tools']
            tool, help_kind = ('clarify', 'unverified') if payload['failures'] else ('task_assign', '')
            schema = Decision  # Simulate a provider bypassing its advertised tool enum.
        elif not results:
            arguments = dict(query=dict(period='upcoming', state='draft', unassigned_only=True, maintenance_only=True,
                                        starts_on=payload['tomorrow'], ends_on=payload['tomorrow'], limit=1))
        elif results[-1]['tool'] == 'tasks_find':
            tool = 'assignment_context'
            arguments = dict(path=dict(task_id=results[-1]['result']['items'][0]['id']))
        elif results[-1]['tool'] == 'assignment_context':
            tool = 'assignment_preview'
            item = results[0]['result']['items'][0]
            arguments = dict(path=results[-1]['arguments']['path'], body=dict(
                expected_revision=results[-1]['result']['expectedRevision'], start_local=item['scheduledStart'][:19],
                end_local=item['scheduledEnd'][:19]))
        else:
            tool, receipt = 'task_assign', results[-1]['receipt']
        return schema(tool=tool, arguments_json=json.dumps(arguments), presentation='continue',
                      receipt=receipt, clarification=help_kind)


def test_dynamic_reads_cannot_propose_and_verified_preview_confirms_once(assistant_case, request, monkeypatch):
    app = assistant_case[1]
    monkeypatch.setattr(app.state, 'settings', replace(app.state.settings, assistant_agent_version='v3',
                                                      assistant_v3_pipeline='llm_dynamic'))
    lab = request.getfixturevalue('lab')
    fixture, _, _, _, _, _, clients = lab
    engine, app, _, _, ids = fixture
    task_id, _, _, worker = schedule(lab)
    monkeypatch.setattr(app.state, 'assistant_provider_factory', lambda: Decisions(escalation_attempt=True), raising=False)
    chief = clients['chief_engineer']
    attempt, actions, _ = turn(chief, 'Кто свободен для этого наряда? Ничего не меняй.')
    assert not actions and attempt['workflow']['outcome'] == 'blocked', attempt
    assert any(row['tool'] == '__dynamic_denied' and row['code'] == 403 for row in attempt['trace'])

    query = text('SELECT status,revision FROM work_orders WHERE work_order_id=:task')
    with engine.connect() as db:
        before = db.execute(query, dict(task=task_id)).one()
    monkeypatch.setattr(app.state, 'assistant_provider_factory', Decisions)
    proposal, actions, _ = turn(chief, 'Назначь свободного сотрудника на ближайшее свободное ТО завтра')
    assert proposal['workflow']['outcome'] == 'awaiting_confirmation', proposal
    action, = actions
    assert action['arguments']['path']['task_id'] == task_id
    assert action['arguments']['body']['executor_ids'] == [worker]
    state = stored(fixture, proposal['turn_id'])
    assert state['llm_dynamic'] and [row['tool'] for row in state['evidence']] == [
        'tasks_find', 'assignment_context', 'assignment_preview', 'task_assign']
    with engine.connect() as db:
        assert db.execute(query, dict(task=task_id)).one() == before
    assert confirm(clients['executor'], action).status_code in (403, 404)
    for _ in range(2):
        result = confirm(chief, action)
        assert result.status_code == 200 and result.json()['status'] == 'succeeded', result.text
    with engine.connect() as db:
        assert db.execute(query, dict(task=task_id)).one() == ('assigned', before.revision + 1)
        assert db.scalar(text('''SELECT count(*) FROM audit_events
            WHERE site_id=:site AND entity_id=:task AND action='assign' '''), {**ids, 'task': task_id}) == 1
