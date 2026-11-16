"""Server facts and actionable file links survive the persisted chat boundary."""
from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile
import json

import pytest
from sqlalchemy import text

from app.assistant.orchestrator import _render
from tests.backend.test_assistant import assistant_case, B, thread
from tests.backend.test_assistant_orchestrator import Planner, goal, send, step
from tests.backend.test_management import managed, equipment
from tests.backend.test_runtime_integration import runtime


def factual_state(value):
    return dict(goals=[dict(id='read', title='Requested server fact', tool='server_fact',
                           mode='read', status='completed', evidence_ids=['fact'])],
                evidence=[dict(id='fact', tool='server_fact', result=value,
                               checked_at='2026-11-16T12:00:00+00:00')])


@pytest.mark.parametrize('value, expected', [(0, '0'), (False, 'False'),
                                           (12.75, '12.75'), ('READY', 'READY')])
def test_verified_scalar_fact_is_visible_in_answer(value, expected):
    state = factual_state(value)
    original = deepcopy(state)
    answer = _render(state)
    assert expected in answer
    assert 'server_fact' in answer and '2026-11-16T12:00:00+00:00' in answer
    assert state == original


def test_scalar_success_keeps_independent_unfinished_objective_visible():
    state = factual_state(0)
    state['goals'].append(dict(id='missing', title='Obtain manufacturer passport',
                              tool='', status='blocked', evidence_ids=[]))
    answer = _render(state)
    assert '0' in answer and 'Obtain manufacturer passport' in answer
    assert 'Незавершённые пункты' in answer
    assert state['goals'][1]['status'] == 'blocked'


def test_single_resource_read_exposes_actual_fields_without_claiming_a_list_is_empty():
    answer = _render(factual_state(dict(asset_code='TEST-UNIT-6', name='Actual server name',
                                       revision=9, commissioned_on='2021-02-03')))
    for actual in ('TEST-UNIT-6', 'Actual server name', '2021-02-03', '9'):
        assert actual in answer
    assert 'Список пуст' not in answer


def test_registry_export_link_survives_reload_and_downloads_actual_equipment(assistant_case):
    engine, app, admin, _, ids = assistant_case
    asset = equipment(admin, ids)
    app.state.assistant_provider_factory = lambda: Planner(
        [dict(goal('export', 'registry_export'), title='Export current equipment registry')],
        [step('registry_export', identity='export')])
    chat = thread(admin)
    view = send(admin, chat, 'Export current equipment registry as an Excel file.')
    turn = view['turns'][-1]
    assert turn['status'] == 'completed', json.dumps(turn, ensure_ascii=True)
    assert turn['workflow']['outcome'] == 'completed', turn
    assert not view['actions']
    exported = [row for row in turn['trace'] if row.get('tool') == 'registry_export'
                and row.get('status') == 'completed']
    assert len(exported) == 1, turn['trace']
    resource = exported[0]['resource']
    assert resource['url'] == '/api/v1/maintenance/registry/excel'
    assert 'spreadsheet' in resource['mime']
    reloaded = admin.get(B + '/conversations/' + chat).json()['turns'][-1]
    assert next(row['resource'] for row in reloaded['trace'] if row.get('tool') == 'registry_export') == resource
    downloaded = admin.get(resource['url'])
    assert downloaded.status_code == 200
    with ZipFile(BytesIO(downloaded.content)) as archive:
        contents = '\n'.join(archive.read(name).decode('utf-8') for name in archive.namelist()
                             if name.endswith('.xml'))
    assert asset['asset_code'] in contents and asset['name'] in contents
    with engine.connect() as db:
        saved_trace = db.scalar(text('SELECT trace FROM assistant_turns WHERE turn_id=:id'),
                                dict(id=turn['turn_id']))
    assert next(row['resource'] for row in saved_trace if row.get('tool') == 'registry_export') == resource
