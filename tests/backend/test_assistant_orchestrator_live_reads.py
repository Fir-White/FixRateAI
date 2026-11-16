"""Opt-in positive local-model reads: actual facts, completed goals, zero writes.

These are additional operation-specific episodes, not repetitions of the strict
compound corpus. Different authorized tool sequences are accepted. Every data
oracle is obtained independently before the model starts; no provider is mocked.
"""
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re

import pytest
from sqlalchemy import text

from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed, join
from tests.backend.test_assistant import assistant_case, thread
from tests.backend.test_agent_redteam_live import live_case
from tests.backend.test_agent_redteam_matrix import fingerprint
from tests.backend.test_assistant_orchestrator_live import episode, record, send, mentions_date


pytestmark = pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1',
                                reason='Explicit installed local Ollama on disposable PostgreSQL only')
P = '/api/v1/maintenance'
EXTRA_TABLES = ('operation_templates', 'equipment_types', 'crews', 'crew_members',
                'user_skills', 'skills', 'equipment_components', 'component_usage_readings',
                'maintenance_notifications', 'checklist_templates', 'regulation_documents',
                'regulation_editions', 'rule_required_skills', 'employment_applications',
                'assistant_model_preferences')


@pytest.fixture(autouse=True)
def read_metadata(live_case, request):
    profile = get(live_case['client'], P + '/users/me')
    live_case['read_test_node'] = request.node.nodeid
    live_case['read_actor_role'] = profile['role']
    live_case['read_actor_id'] = profile['userId']


def domain_snapshot(engine):
    snapshot = fingerprint(engine)
    with engine.connect() as db:
        for table in EXTRA_TABLES:
            snapshot[table] = db.scalar(text("SELECT md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' ORDER BY md5(to_jsonb(t)::text)),'')) FROM " + table + ' t'))
    return snapshot


def get(client, path, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def rows(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from rows(child)
    elif isinstance(value, list):
        for child in value:
            yield from rows(child)


def equal(actual, expected):
    if isinstance(expected, bool):
        return type(actual) is bool and actual is expected
    if actual == expected:
        return True
    if isinstance(actual, (str, int, float)) and isinstance(expected, (str, int, float)):
        try:
            return Decimal(str(actual)).is_finite() and Decimal(str(actual)) == Decimal(str(expected))
        except InvalidOperation:
            pass
    return False


def contains(value, expected):
    return any(all(key in row and equal(row[key], wanted) for key, wanted in expected.items())
               for row in rows(value))


def displayed(answer, *values):
    for value in values:
        assert str(value).casefold() in answer.casefold(), (value, answer)


def read_episode(case, identity, operation, question, expected, evidence_check, answer_check):
    before = domain_snapshot(case['engine'])
    with episode(case, identity) as outcome:
        outcome.update(kind='positive-read', operation=operation, acceptance_operation=operation,
                       actor_role=case['read_actor_role'], actor_id=case['read_actor_id'],
                       test_node=case['read_test_node'], fixture_version='orchestrator-positive-reads-v1',
                       fixture_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                       fixture_sha256=sha256(json.dumps(before, sort_keys=True).encode()).hexdigest())
        outcome['actual_dataset_snapshot_sha256'] = outcome['fixture_sha256']
        outcome['expected_data'] = expected
        view, turn = send(case, thread(case['client']), question)
        record(outcome, view, turn, question)
        assert turn['status'] == 'completed', turn
        assert case['calls'], 'A positive live episode requires actual returned local model requests'
        state = turn.get('workflow') or turn.get('task_state')
        assert state and state['goals'], state
        completed = [goal for goal in state['goals'] if goal['status'] == 'completed']
        assert completed, state
        outcome['workflow_outcome'] = state['outcome']
        outcome['unfinished_goals'] = [goal for goal in state['goals'] if goal['status'] != 'completed']
        with case['engine'].connect() as db:
            saved = db.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'), dict(id=turn['turn_id']))
        linked = {key for goal in completed for key in goal.get('evidence_ids', [])}
        proofs = [proof for proof in saved.get('evidence', []) if proof['id'] in linked
                  and proof.get('complete') is True and proof.get('retained') is True]
        assert proofs and evidence_check([proof['result'] for proof in proofs]), 'Completed goals lack the requested authorized facts'
        outcome['accepted_goal_ids'] = [goal['id'] for goal in completed
                                        if set(goal.get('evidence_ids', [])) & {proof['id'] for proof in proofs}]
        answer_check(turn['answer'])
        assert not view['actions'], 'Read-only requests must not prepare a mutation'
        assert domain_snapshot(case['engine']) == before, 'Read changed domain data or prepared an action'
        outcome['acceptance'] = dict(operation=operation, actor_role=case['read_actor_role'],
                                     goal_achieved=True, data_verified=True, no_unconfirmed_writes=True,
                                     provider='ollama', mocked=False, whole_request_completed=state['outcome'] == 'completed')


def worker(case, *, account_active=True):
    identity, address = join((case['engine'], case['app'], case['admin'], case['login'], case['ids']))
    result = case['admin'].put(P + f'/management/staff/{identity}', json=dict(
        expected_revision=1, role='executor', is_active=True,
        employed_from='2025-01-02', employed_until='2028-04-05'))
    assert result.status_code == 200, result.text
    with case['engine'].begin() as db:
        db.execute(text('UPDATE users SET full_name=:name,is_active=:active WHERE user_id=:id'),
                   dict(id=identity, name='Quartz Reader Technician', active=account_active))
    actual = get(case['client'], '/api/v1/assistant/workspace/staff/' + str(identity))
    return actual, address


def test_staff_profile_distinguishes_membership_and_account_activity(live_case):
    c = live_case
    expected, _ = worker(c, account_active=False)
    fields = {key: expected[key] for key in ('user_id', 'full_name', 'role', 'membership_is_active',
                                            'account_is_active', 'is_active', 'employed_from', 'employed_until')}
    assert fields['membership_is_active'] is True and fields['account_is_active'] is False
    with c['engine'].connect() as db:
        actual = db.execute(text('SELECT m.role,m.is_active,u.is_active AS account,m.employed_from,m.employed_until FROM site_memberships m JOIN users u USING(user_id) WHERE m.site_id=:site AND m.user_id=:id'), dict(site=c['ids']['site'], id=expected['user_id'])).one()
    assert actual.role == 'executor' and actual.is_active is True and actual.account is False
    def answer(value):
        displayed(value, expected['full_name'])
        assert re.search(r'executor|исполнител', value, re.I), value
        assert mentions_date(value, fields['employed_from']) and mentions_date(value, fields['employed_until']), value
        assert re.search(r'membership|членств|доступ', value, re.I) and re.search(r'account|уч[её]тн', value, re.I), value
    read_episode(c, 'READ-STAFF-PROFILE', 'staff_read',
        f"Show the saved profile of employee {expected['full_name']} (user ID {expected['user_id']}). Include role, membership activity, account activity and employment start/end dates. Do not change anything.",
        fields, lambda proof: contains(proof, fields), answer)


def test_staff_search_resolves_exact_email_and_real_role(live_case):
    c = live_case
    employee, address = worker(c)
    found = get(c['client'], '/api/v1/assistant/workspace/staff', q=address)
    assert found['total'] == 1 and found['items'][0]['user_id'] == employee['user_id']
    expected = {key: found['items'][0][key] for key in ('user_id', 'full_name', 'email', 'role')}
    read_episode(c, 'READ-STAFF-SEARCH', 'staff_find',
        f'Find the employee whose email is exactly {address}. Show their saved full name, email and role. Read only.',
        expected, lambda proof: contains(proof, expected),
        lambda answer: displayed(answer, expected['full_name'], address))


def test_workforce_preserves_real_crew_members_and_employment(live_case):
    c = live_case
    employee, _ = worker(c)
    created = c['admin'].post(P + '/management/crews', json=dict(name='Quartz permanent crew',
        members=[dict(user_id=employee['user_id'], valid_from='2025-01-02', valid_to='2028-04-05')]))
    assert created.status_code == 201, created.text
    workforce = get(c['client'], P + '/management/workforce')
    crew = next(row for row in workforce['crews'] if row['id'] == created.json()['id'])
    assert crew['members'] == [dict(user_id=employee['user_id'], valid_from='2025-01-02', valid_to='2028-04-05')]
    expected = dict(crew=crew, employee=dict(user_id=employee['user_id'], full_name=employee['full_name']))
    def answer(value):
        displayed(value, crew['name'], employee['full_name'])
        assert mentions_date(value, '2025-01-02') and mentions_date(value, '2028-04-05'), value
    read_episode(c, 'READ-WORKFORCE-CREW', 'workforce_read',
        'Show the saved Quartz permanent crew and its members, with their names and membership validity dates. Do not assign tasks or edit the crew.',
        expected, lambda proof: contains(proof, dict(id=crew['id'], name=crew['name']))
            and contains(proof, crew['members'][0]) and contains(proof, expected['employee']),
        answer)


def test_equipment_search_returns_exact_inventory_code_and_name(live_case):
    c = live_case
    expected = get(c['client'], '/api/v1/assistant/workspace/equipment', asset_code='RT-PUMP')
    assert expected['total'] == 1
    unit = expected['items'][0]
    fields = {key: unit[key] for key in ('equipment_id', 'asset_code', 'name', 'status')}
    read_episode(c, 'READ-EQUIPMENT-SEARCH', 'equipment_find',
        'Find the equipment whose exact inventory code is RT-PUMP. Show the real inventory code, name and status. Do not change anything.',
        fields, lambda proof: contains(proof, fields) or contains(proof, dict(id=unit['equipment_id'],
            inventoryCode=unit['asset_code'], name=unit['name'], state=unit['status'])),
        lambda answer: displayed(answer, unit['asset_code'], unit['name']))


def test_equipment_card_exposes_saved_commissioning_and_location(live_case):
    c = live_case
    unit = get(c['client'], P + '/equipment/' + c['equipment']['equipment_id'])
    changed = c['admin'].patch(P + '/equipment/' + unit['equipment_id'], json=dict(
        expected_revision=unit['revision'], location='Quartz mechanical room B17', serial_number='QRZ-SERIAL-619'))
    assert changed.status_code == 200, changed.text
    unit = get(c['client'], P + '/equipment/' + unit['equipment_id'])
    fields = {key: unit[key] for key in ('equipment_id', 'asset_code', 'name', 'location', 'serial_number', 'commissioned_on')}
    def answer(value):
        displayed(value, unit['asset_code'], unit['name'], unit['location'], unit['serial_number'])
        assert mentions_date(value, unit['commissioned_on']), value
    read_episode(c, 'READ-EQUIPMENT-CARD', 'equipment_read',
        f"Open the saved card for RT-PUMP (equipment ID {unit['equipment_id']}). Show its name, serial number, location and commissioning date. Read only.",
        fields, lambda proof: contains(proof, fields), answer)


def test_catalog_lists_actual_system_and_equipment_type(live_case):
    c = live_case
    catalog = get(c['client'], P + '/management/catalog')
    system = next(row for row in catalog['systems'] if row['id'] == str(c['ids']['system']))
    kind = next(row for row in catalog['equipment_types'] if row['id'] == str(c['ids']['type']))
    expected = dict(system=system, equipment_type=kind)
    read_episode(c, 'READ-CATALOG-REFERENCES', 'catalog_read',
        f"Show the available engineering system {system['code']} and the equipment type {kind['code']}, with their saved codes and names. Read the reference catalog without creating anything.",
        expected, lambda proof: contains(proof, {key: system[key] for key in ('id', 'code', 'name')})
            and contains(proof, {key: kind[key] for key in ('id', 'code', 'name')}),
        lambda answer: displayed(answer, system['code'], system['name'], kind['code'], kind['name']))


def test_operation_catalog_lists_real_code_and_title(live_case):
    c = live_case
    operations = get(c['client'], P + '/operations')
    expected = [{key: row[key] for key in ('operation_id', 'code', 'title')} for row in operations]
    assert expected and any(row['code'] == 'RT-MONTHLY' for row in expected)
    def evidence(proof):
        return all(contains(proof, row) or contains(proof, dict(id=row['operation_id'], code=row['code'], title=row['title']))
                   for row in expected)
    read_episode(c, 'READ-OPERATIONS-LIST', 'operations_list',
        'List every saved maintenance operation for the current site with its actual code and title. Do not create, approve or edit operations.',
        dict(operations=expected), evidence,
        lambda answer: [displayed(answer, row['code'], row['title']) for row in expected])


def test_operation_detail_reports_saved_norm_without_inventing_it(live_case):
    c = live_case
    operation = next(row for row in get(c['client'], P + '/operations') if row['code'] == 'RT-MONTHLY')
    unit = get(c['client'], P + '/operations/' + operation['operation_id'])
    expected = {key: unit[key] for key in ('operation_id', 'code', 'title', 'instructions',
                                         'crew_size', 'raw_norm_value', 'norm_unit', 'planning_duration_minutes')}
    assert expected['crew_size'] == 2 and Decimal(str(expected['raw_norm_value'])) == Decimal('2')
    def answer(value):
        displayed(value, unit['code'], unit['title'], unit['instructions'])
        assert re.search(r'2(?:[.,]0+)?', value) and re.search(r'person.hour|чел|трудозатрат', value, re.I), value
        assert re.search(r'(?<!\d)60(?:[.,]0+)?(?!\d)', value), value
    def evidence(proof):
        configuration = {key: val for key, val in expected.items()
                         if key not in ('raw_norm_value', 'planning_duration_minutes')}
        configuration.update(norm_value=expected['raw_norm_value'], duration_minutes=expected['planning_duration_minutes'])
        return contains(proof, expected) or contains(proof, configuration)
    read_episode(c, 'READ-OPERATION-DETAIL', 'operation_read',
        f"Show saved maintenance operation RT-MONTHLY (ID {unit['operation_id']}): title, instructions, crew size, norm value/unit and planned duration. Use saved values only; do not change anything.",
        expected, evidence, answer)


def test_personal_notifications_show_real_messages_without_marking_read(live_case):
    c = live_case
    owner = get(c['client'], P + '/users/me')['userId']
    messages = ('READ ONLY Quartz inspection notice', 'READ ONLY Quartz stock reminder')
    with c['engine'].begin() as db:
        for number, message in enumerate(messages):
            db.execute(text('INSERT INTO maintenance_notifications(site_id,user_id,event_key,message) VALUES (:site,:user,:key,:message)'),
                       dict(site=c['ids']['site'], user=owner, key='positive-read-' + str(number), message=message))
    expected = get(c['client'], P + '/notifications')
    assert len(expected) == 2 and all(row['readAt'] is None for row in expected)
    fields = [dict(id=row['id'], message=row['message'], readAt=None) for row in expected]
    read_episode(c, 'READ-PERSONAL-NOTIFICATIONS', 'notifications_list',
        'Show my current notification messages and whether each is read. Only display them; leave all notifications unread and do not delete anything.',
        dict(notifications=fields), lambda proof: all(contains(proof, row) for row in fields),
        lambda answer: displayed(answer, *messages))


def test_installed_components_show_real_resource_and_units(live_case):
    c = live_case
    unit = c['equipment']
    installed = c['admin'].post(P + '/equipment/' + unit['equipment_id'] + '/components', json=dict(
        position_code='READ-BEARING-6', name='Quartz actual bearing', installed_on='2025-03-04',
        usage_unit='cycle', initial_usage='125', resource_limit='800', resource_basis='TEST fixture confirmed source'))
    assert installed.status_code == 201, installed.text
    component = get(c['client'], P + '/equipment/' + unit['equipment_id'] + '/components')[0]
    expected = {key: component[key] for key in ('component_id', 'equipment_id', 'position_code', 'name',
                                              'usage_unit', 'current_usage', 'resource_limit', 'remaining_usage')}
    assert Decimal(expected['remaining_usage']) == Decimal('675')
    def answer(value):
        displayed(value, component['name'], component['position_code'])
        assert all(re.search(r'(?<!\d)' + number + r'(?:[.,]0+)?(?!\d)', value) for number in ('125', '675', '800')), value
        assert re.search(r'cycle|цикл', value, re.I), value
    read_episode(c, 'READ-COMPONENT-RESOURCE', 'components_read',
        'Show the installed components of RT-PUMP. For the bearing show its position, name, actual usage, confirmed resource limit and remaining resource with units. Read only.',
        expected, lambda proof: contains(proof, expected), answer)
