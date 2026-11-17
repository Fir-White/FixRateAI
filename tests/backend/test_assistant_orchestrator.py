"""Goal outcomes rather than a prescribed sequence of model-selected calls."""
import copy
from datetime import date
import json
from uuid import uuid4
import pytest
from sqlalchemy import text
from app.schemas.assistant import ToolSelection, GoalSpec
from app.assistant import workflow as wf
from tests.backend.test_assistant import assistant_case, B, thread, confirm
from tests.backend.test_management import managed, equipment as create_equipment, config
from tests.backend.test_runtime_integration import runtime


def equipment(client, ids):
    return create_equipment(client, {**ids, 'marker': uuid4().hex})


class Planner:
    response_model = 'TEST-ONLY-scripted-planning'
    def __init__(self, goals, steps):
        self.goals, self.steps, self.seen = goals, iter(steps), []
    def chat(self, messages, schema, tokens):
        self.seen.append(copy.deepcopy(messages))
        if schema.__name__ == 'ToolSelection':
            return schema.model_validate(dict(tools=list(dict.fromkeys(g['tool'] for g in self.goals if g['tool']))[:8], goals=self.goals))
        return schema.model_validate(next(self.steps))


def goal(identity, tool, **values):
    return dict(id=identity, title=identity, tool=tool, **values)


def step(tool, arguments=None, identity=None):
    return dict(answer='', calls=[dict(tool=tool, arguments_json=json.dumps(arguments or {}),
                                      explanation='TEST ONLY requested operation', goal_id=identity)])


def send(client, chat, content, **extra):
    response = client.post(B+f'/conversations/{chat}/messages',
                           json=dict(idempotency_key=str(uuid4()), content=content, **extra))
    assert response.status_code == 202, response.text
    return client.get(B+'/conversations/'+chat).json()


def test_plan_requires_dependency_order_and_never_completes_from_a_search():
    from types import SimpleNamespace
    tools = {'equipment_find': SimpleNamespace(mode='read'), 'equipment_edit': SimpleNamespace(mode='write')}
    selection = ToolSelection(goals=[GoalSpec(**goal('rename', 'equipment_edit'))], tools=[])
    state = wf.create_plan(selection, 'rename equipment', tools, {})
    wf.record_result(state, state['goals'][0], 'equipment_find', {}, {'items': [], 'total': 0})
    assert state['goals'][0]['status'] == 'planned'
    assert state['outcome'] != 'completed'
    selection.goals = [GoalSpec(**goal('later', 'equipment_edit', depends_on=['missing']))]
    with pytest.raises(ValueError):
        wf.create_plan(selection, 'TEST', tools, {})


@pytest.mark.parametrize('payload', [
    {'items': [1], 'total': 117}, {'complete': False}, {'has_more': True},
    {'configurations': [{'status': 'blocked'}]}, {'nested': {'truncated': True}},
])
def test_partial_evidence_cannot_complete_a_goal(payload):
    from types import SimpleNamespace
    state = wf.create_plan(ToolSelection(tools=[], goals=[GoalSpec(**goal('all', 'equipment_find'))]),
                           'all', {'equipment_find': SimpleNamespace(mode='read')}, {})
    wf.record_result(state, state['goals'][0], 'equipment_find', {}, payload)
    assert state['goals'][0]['status'] == 'partial'
    assert state['outcome'] == 'partial'


def test_undecomposed_request_and_model_answer_do_not_prove_completion():
    state = wf.create_plan(ToolSelection(tools=[]), 'several objectives', {}, {})
    state['goals'][0]['status'] = 'completed'
    assert wf.update_outcome(state) != 'completed'
    assert wf.safe_evidence({'nested': {'api_key': 'PRIVATE', 'name': 'Visible'}}) == {'nested': {'api_key': '[redacted]', 'name': 'Visible'}}


def test_resume_never_replays_an_action_even_when_receipt_is_uncertain():
    state = wf.create_plan(ToolSelection(tools=[]), 'TEST', {}, {})
    state['goals'][0].update(status='uncertain', action_id=str(uuid4()))
    resumed = wf.resume(state)
    assert resumed['goals'][0]['status'] == 'uncertain'
    assert resumed['goals'][0]['action_id'] == state['goals'][0]['action_id']


def test_two_independent_renames_keep_exact_values_and_separate_confirmations(assistant_case):
    engine, app, admin, _, ids = assistant_case
    first, second = equipment(admin, ids), equipment(admin, ids)
    goals = [goal('first', 'equipment_edit'), goal('second', 'equipment_edit')]
    provider = Planner(goals, [step('equipment_edit', dict(path=dict(equipment_id=first['equipment_id']), body=dict(name='FIRST NEW'))),
                               step('equipment_edit', dict(path=dict(equipment_id=second['equipment_id']), body=dict(name='SECOND NEW')))])
    app.state.assistant_provider_factory = lambda: provider
    chat = thread(admin)
    view = send(admin, chat, 'Rename first to FIRST NEW and second to SECOND NEW. Prepare both; do not apply.')
    turn = view['turns'][-1]
    assert turn['status'] == 'completed', view
    assert turn['workflow']['outcome'] == 'awaiting_confirmation'
    cards = view['actions']
    assert len(cards) == 2
    assert {card['arguments']['body']['name'] for card in cards} == {'FIRST NEW', 'SECOND NEW'}
    with engine.connect() as db:
        assert db.scalar(text('SELECT name FROM equipment WHERE equipment_id=:id'), dict(id=first['equipment_id'])) == first['name']
        assert db.scalar(text('SELECT name FROM equipment WHERE equipment_id=:id'), dict(id=second['equipment_id'])) == second['name']
    response = confirm(admin, cards[0])
    assert response.status_code == 200, response.text
    assert response.json()['result']['verification']['status'] == 'confirmed'
    assert confirm(admin, cards[0]).json() == response.json()
    view = admin.get(B+'/conversations/'+chat).json()
    assert [g['status'] for g in view['turns'][-1]['workflow']['goals']] == ['completed', 'awaiting_confirmation']
    assert view['turns'][-1]['workflow']['outcome'] != 'completed'


def test_inventory_includes_orphans_and_can_continue_to_calendar(assistant_case):
    _, app, admin, _, ids = assistant_case
    eq = equipment(admin, ids)
    orphan = equipment(admin, ids)
    dated=admin.patch('/api/v1/maintenance/equipment/'+eq['equipment_id'],json=dict(expected_revision=eq['revision'],commissioned_on='2023-11-16'))
    assert dated.status_code==200,dated.text
    eq=dated.json()
    saved = admin.chief.post(f"/api/v1/maintenance/equipment/{eq['equipment_id']}/service-configurations",
                       json=config(date(2023,11,16),pattern=dict(frequency='yearly_count', interval=1, count_per_year=5,
                                                anchor_date='2023-11-16', annual_policy='from_anchor', weekend_policy='next_workday'), valid_from='2023-11-16'))
    assert saved.status_code == 201, saved.text
    provider = Planner([goal('inventory', 'inventory_read', requires_full_list=True), goal('calendar', 'calendar_evidence')],
        [step('inventory_read'), step('calendar_evidence', dict(path=dict(equipment_id=eq['equipment_id']), query=dict(starts_on='2026-11-16', ends_on='2027-11-15')))])
    app.state.assistant_provider_factory = lambda: provider
    view = send(admin, thread(admin), 'Check inventory including orphans and explain five services per year.')
    turn = view['turns'][-1]
    assert turn['workflow']['outcome'] == 'completed', turn
    assert eq['asset_code'] in turn['answer'] and orphan['asset_code'] in turn['answer']
    assert '2027-01-28' in turn['answer'] and '2027-09-06' in turn['answer']
    assert 'производителя' in turn['answer']


def test_full_page_request_fetches_all_without_model_pagination(assistant_case):
    _, app, admin, _, ids = assistant_case
    assets = [equipment(admin, ids) for _ in range(31)]
    provider = Planner([goal('all', 'equipment_find', requires_full_list=True)], [step('equipment_find')])
    app.state.assistant_provider_factory = lambda: provider
    chat = thread(admin)
    view = send(admin, chat, 'List all equipment completely.')
    turn = view['turns'][-1]
    assert turn['workflow']['outcome'] == 'completed', turn
    assert len(provider.seen) == 2  # semantic plan + execution, no per-page inference
    with app.state.factory() as session:
        state = session.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'), dict(id=turn['turn_id']))
    assert state['evidence'][-1]['result']['returned_count'] == 31
    assert {item['equipment_id'] for item in state['evidence'][-1]['result']['items']} == {asset['equipment_id'] for asset in assets}


def test_model_stop_after_prerequisite_preserves_unfinished_goal(assistant_case):
    _, app, admin, _, ids = assistant_case
    equipment(admin, ids)
    provider = Planner([goal('change', 'equipment_edit')], [step('equipment_find'), dict(answer='Everything is done.', calls=[])])
    app.state.assistant_provider_factory = lambda: provider
    view = send(admin, thread(admin), 'Rename equipment after resolving it.')
    turn = view['turns'][-1]
    assert turn['status'] == 'completed'
    assert turn['workflow']['outcome'] == 'partial'
    assert turn['workflow']['goals'][0]['status'] == 'partial'
    assert not view['actions']
    assert 'Незавершённые пункты' in turn['answer']


def test_denied_specialist_call_does_not_prevent_independent_goal(assistant_case):
    _, app, admin, _, ids = assistant_case
    eq = equipment(admin, ids)
    provider = Planner([goal('wrong', 'equipment_read'), goal('valid', 'equipment_read')],
        [step('task_cancel', dict(path=dict(task_id=str(uuid4())), body=dict(reason='unasked'))),
         dict(answer='Cannot.', calls=[]), step('equipment_read', dict(path=dict(equipment_id=eq['equipment_id'])))])
    app.state.assistant_provider_factory = lambda: provider
    view = send(admin, thread(admin), 'Read two independently requested resources, do not mutate.')
    state = view['turns'][-1]['workflow']
    assert [g['status'] for g in state['goals']] == ['blocked', 'completed']
    assert state['outcome'] == 'partial'
    assert not view['actions']
