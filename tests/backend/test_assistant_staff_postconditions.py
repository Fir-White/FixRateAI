"""Staff confirmation proves scoped membership changes and retained dates."""
from copy import deepcopy
import asyncio
import json
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import text

from app.assistant.action_outcomes import verify_action, verify_postcondition
from app.assistant import tools
from tests.backend.test_assistant import assistant_case, B, thread, confirm
from tests.backend.test_assistant_orchestrator import Planner, goal, send
from tests.backend.test_management import managed, join, PREFIX
from tests.backend.test_runtime_integration import runtime


USER = str(uuid4())


def saved_staff(**changes):
    return dict(user_id=USER, full_name='TEST ONLY employee', email='test@example.test',
                role='executor', membership_is_active=True, account_is_active=True,
                is_active=True, revision=2, employed_from='2026-01-01',
                employed_until='2027-01-01', **changes)


def case(change=None):
    before = saved_staff()
    body = dict(expected_revision=2, role='engineer', is_active=True, **(change or {}))
    after = dict(before, revision=3, role='engineer', **(change or {}))
    return dict(path=dict(user_id=USER), body=body), dict(revision=3), before, after


def verify(values):
    arguments, receipt, before, after = values
    return verify_postcondition('staff_edit', arguments, receipt, before, after)


@pytest.mark.parametrize('change', [{}, {'employed_from': None}, {'employed_until': None},
                                   {'employed_from': '2026-02-01', 'employed_until': '2027-03-01'}])
def test_staff_exact_dates_null_and_omission_are_verified(change):
    assert verify(case(change))['status'] == 'confirmed'


def test_combined_account_activity_never_replaces_membership_flag():
    values = case()
    for row in values[2:]:
        row.update(account_is_active=False, is_active=False)
    assert verify(values)['status'] == 'confirmed'
    values[3]['membership_is_active'] = False
    assert verify(values)['status'] == 'failed'


@pytest.mark.parametrize('field,value', [('role', 'dispatcher'), ('membership_is_active', False),
    ('employed_from', None), ('employed_until', None), ('email', 'different@example.test'),
    ('full_name', 'Changed unrelated name'), ('account_is_active', False)])
def test_staff_wrong_change_or_unrelated_erasure_is_not_confirmed(field, value):
    values = case()
    values[3][field] = value
    assert verify(values)['status'] == 'failed'


@pytest.mark.parametrize('target,field,value,reason', [
    (2, 'user_id', str(uuid4()), 'before_identity_missing_or_mismatched'),
    (3, 'user_id', str(uuid4()), 'readback_identity_missing_or_mismatched'),
    (2, 'revision', 1, 'before_revision_mismatch'),
    (1, 'revision', 4, 'receipt_revision_mismatch'),
    (3, 'revision', 4, 'readback_revision_changed'),
    (3, 'membership_is_active', 'true', 'unsupported_result_shape'),
])
def test_staff_unknown_identity_revision_or_shape_stays_unverified(target, field, value, reason):
    values = case()
    values[target][field] = value
    outcome = verify(values)
    assert outcome['status'] == 'unverified' and outcome['reason'] == reason


def test_staff_success_prose_and_missing_preflight_cannot_prove_completion():
    arguments, _, before, after = case()
    assert verify_postcondition('staff_edit', arguments, {'success': True}, before, after)['status'] == 'unverified'
    assert verify_postcondition('staff_edit', arguments, {'revision': 3}, None, after)['status'] == 'unverified'
    absent = deepcopy(after)
    absent.pop('employed_until')
    assert verify_postcondition('staff_edit', arguments, {'revision': 3}, before, absent)['status'] == 'unverified'


def test_staff_uses_actual_authorized_readback_and_does_not_bypass_revoked_rights(monkeypatch):
    arguments, receipt, before, after = case()
    descriptor = next(tool for tool in tools.TOOLS if tool.name == 'staff_edit')
    reads = []
    monkeypatch.setattr(tools, 'validate_arguments', lambda app, tool, args: args)
    async def read(app, tool, args, headers):
        reads.append((tool.name, args, headers))
        return after
    monkeypatch.setattr(tools, 'invoke', read)
    outcome = asyncio.run(verify_action(object(), descriptor, arguments, receipt, {'cookie': 'TEST PRIVATE'}, before))
    assert outcome['status'] == 'confirmed'
    assert reads == [('staff_read', {'path': {'user_id': USER}}, {'cookie': 'TEST PRIVATE'})]
    async def denied(*args, **kwargs):
        raise HTTPException(403, 'TEST PRIVATE revoked session')
    monkeypatch.setattr(tools, 'invoke', denied)
    outcome = asyncio.run(verify_action(object(), descriptor, arguments, receipt, {}, before))
    assert outcome['status'] == 'unverified' and outcome['reason'] == 'authorized_readback_failed'
    assert 'PRIVATE' not in json.dumps(outcome)


@pytest.mark.parametrize('change,expected', [
    ({}, ('2026-01-01', '2027-01-01')),
    ({'employed_from': None}, (None, '2027-01-01')),
    ({'employed_from': '2026-02-01', 'employed_until': None}, ('2026-02-01', None)),
])
def test_staff_role_dates_confirm_replay_and_completed_workflow(assistant_case, change, expected):
    engine, app, admin, _, ids = assistant_case
    identity, _ = join(assistant_case)
    setup = admin.put(PREFIX + f'/management/staff/{identity}', json=dict(
        expected_revision=1, role='executor', is_active=True,
        employed_from='2026-01-01', employed_until='2027-01-01'))
    assert setup.status_code == 200, setup.text
    changes = dict(role='engineer', is_active=True, **change)
    spec = dict(goal('membership', 'staff_edit'), title='Change selected employee role and employment dates',
                kind='change', selector=dict(user_id=str(identity)), changes=changes)
    app.state.assistant_provider_factory = lambda: Planner([spec], [])
    chat = thread(admin)
    question = f'Change employee user_id={identity} to role=engineer and keep membership active. Apply exactly these employment date changes: {json.dumps(change)}. Preserve all other fields and prepare a proposal for confirmation.'
    view = send(admin, chat, question)
    turn = view['turns'][-1]
    assert turn['status'] == 'completed', turn
    assert turn['workflow']['outcome'] == 'awaiting_confirmation'
    assert len(view['actions']) == 1
    card = view['actions'][0]
    assert card['arguments']['body'] == dict(changes, expected_revision=2)
    with engine.connect() as db:
        before = db.execute(text('SELECT role,revision FROM site_memberships WHERE site_id=:site AND user_id=:id'),
                            dict(site=ids['site'], id=identity)).one()
    assert before == ('executor', 2)
    applied = confirm(admin, card)
    assert applied.status_code == 200, applied.text
    assert applied.json()['result']['verification']['status'] == 'confirmed'
    assert confirm(admin, card).json() == applied.json()
    reloaded = admin.get(B + '/conversations/' + chat).json()['turns'][-1]
    assert reloaded['workflow']['outcome'] == 'completed'
    assert reloaded['workflow']['goals'][0]['status'] == 'completed'
    with engine.connect() as db:
        member = db.execute(text('SELECT role,is_active,employed_from,employed_until,revision FROM site_memberships WHERE site_id=:site AND user_id=:id'),
                            dict(site=ids['site'], id=identity)).one()
        assert member.role == 'engineer' and member.is_active is True and member.revision == 3
        assert tuple(day.isoformat() if day else None for day in member[2:4]) == expected
        durable = db.execute(text('SELECT status,result FROM assistant_actions WHERE action_id=:id'),
                             dict(id=card['action_id'])).one()
        checkpoint = db.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'), dict(id=turn['turn_id']))
    assert durable.status == 'succeeded'
    assert durable.result['verification']['status'] == 'confirmed'
    assert checkpoint['goals'][0]['action_id'] == card['action_id']
    # The workflow JSON is a checkpoint, not the authoritative action receipt.
    # A new scoped HTTP request reconstructs completion from the durable sources
    # without inference or a competing checkpoint write during confirmation.
    def no_inference():
        raise AssertionError('Reading persisted completion must not invoke a model')
    app.state.assistant_provider_factory = no_inference
    reopened = admin.get(B + '/conversations/' + chat)
    assert reopened.status_code == 200, reopened.text
    recovered = reopened.json()['turns'][-1]['workflow']
    assert recovered['outcome'] == 'completed'
    assert recovered['goals'][0]['status'] == 'completed'
