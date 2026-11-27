"""Acceptance claims require role-specific executed evidence, not registration."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.assistant_acceptance_matrix import build, specifications, validate_record

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def manifest():
    return json.loads((ROOT / 'contracts/assistant-tools.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def matrix(manifest):
    return build(manifest)


def test_every_available_role_operation_has_an_explicit_positive_scenario(manifest, matrix):
    expected = {(tool['name'], role) for tool in manifest['tools'] for role in tool['roles']}
    actual = {(cell['operation'], cell['role']) for cell in matrix['cells']}
    assert actual == expected
    assert len(actual) == len(matrix['cells'])
    assert set(specifications()) == {tool['name'] for tool in manifest['tools']}
    assert all('password' not in operation['path'] for operation in matrix['operations'])
    for operation in matrix['operations']:
        assert set(operation['roles']).isdisjoint(operation['denied_roles'])
        assert set(operation['roles']) | set(operation['denied_roles']) == {'director', 'chief_engineer', 'engineer', 'dispatcher', 'admin', 'executor'}
        scenario = operation['positive_scenario']
        assert scenario['user_goal'] and scenario['fixture'] and scenario['postconditions'][0]
        assert scenario['first_visible_action'] and scenario['next_action']
        assert operation['traceability']['source_requirements']
        assert operation['traceability']['customer_decision_dependencies']
    assert len({operation['positive_scenario']['postconditions'][0] for operation in matrix['operations']}) == len(matrix['operations'])


def test_generated_contract_is_current_and_registration_is_not_a_pass(matrix,manifest):
    ledger=json.loads((ROOT / 'contracts/assistant-acceptance-evidence.json').read_text(encoding='utf-8'))
    assert json.loads((ROOT / 'contracts/assistant-acceptance.json').read_text(encoding='utf-8')) == build(manifest,evidence=ledger)
    for cell in matrix['cells']:
        assert cell['registered'] is True
        assert all(value == {'status': 'not_run', 'records': []} for value in cell['verification'].values())
    assert matrix['summary']['verification']['positive_e2e']['passed'] == 0


def test_export_fails_closed_when_a_new_operation_has_no_acceptance_case(manifest):
    changed = deepcopy(manifest)
    changed['tools'].append({**changed['tools'][0], 'name': 'new_unaccepted_user_operation'})
    with pytest.raises(AssertionError, match='new_unaccepted_user_operation'):
        build(changed)


def evidence(**overrides):
    return dict(operation='equipment_edit', role='chief_engineer', category='positive_e2e',
                status='passed', run_id='isolated-local-round-1', source_commit='a' * 40,
                fixture_sha256='b' * 64, artifact='private/reports/episode.json',
                test_node='tests/backend/test_actual_episode.py::test_rename',
                provider='ollama', mocked=False, goal_achieved=True, data_verified=True,
                no_unconfirmed_writes=True, model_ref='ollama:qwen3.5:4b-q4_K_M@sha256:' + 'c' * 64,
                **overrides)


@pytest.mark.parametrize('field,value', [
    ('provider', 'aitunnel'), ('provider', 'openai'), ('mocked', True),
    ('goal_achieved', False), ('data_verified', False), ('no_unconfirmed_writes', False),
    ('model_ref', 'qwen3.5:4b'), ('model_ref', 'ollama:qwen-cloud:latest@sha256:' + 'c' * 64),
    ('source_commit', 'main'), ('fixture_sha256', ''),
])
def test_positive_e2e_rejects_external_mocked_or_unverified_claims(field, value):
    record = evidence()
    record[field] = value
    with pytest.raises(ValueError):
        validate_record(record, {('equipment_edit', 'chief_engineer'): object()})


def test_evidence_cannot_promote_a_different_role_or_operation(manifest):
    record = evidence()
    record['role'] = 'executor'
    with pytest.raises(ValueError, match='available role/operation'):
        build(manifest, evidence=[record])


@pytest.mark.parametrize('category', ['negative', 'mocked', 'api_domain', 'reachability'])
def test_other_success_categories_do_not_close_positive_acceptance(manifest, category):
    record = evidence()
    record['category'] = category
    result = build(manifest, evidence=[record])
    cell = next(cell for cell in result['cells'] if (cell['operation'], cell['role']) == ('equipment_edit', 'chief_engineer'))
    assert cell['verification'][category]['status'] == 'passed'
    assert cell['verification']['positive_e2e']['status'] == 'not_run'


def test_explicit_evidence_promotes_only_its_cell_and_retains_failed_attempt(manifest):
    failed = evidence()
    failed.update(status='failed', goal_achieved=False, run_id='isolated-local-round-0')
    passed = evidence()
    result = build(manifest, evidence=[failed, passed])
    positives = [cell for cell in result['cells'] if cell['verification']['positive_e2e']['status'] == 'passed']
    assert len(positives) == 1
    assert (positives[0]['operation'], positives[0]['role']) == ('equipment_edit', 'chief_engineer')
    records = positives[0]['verification']['positive_e2e']['records']
    assert [record['status'] for record in records] == ['failed', 'passed']
    assert result['summary']['verification']['positive_e2e']['not_run'] == len(result['cells']) - 1
