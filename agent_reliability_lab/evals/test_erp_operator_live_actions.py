"""Opt-in model planning with real confirmation, audit and business postcondition."""
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import text

from agent_reliability_lab.evals.test_agent_v3_e2e import lab
from agent_reliability_lab.evals.test_maintenance_conversation import schedule
from agent_reliability_lab.evals.test_pipeline_comparison import _cloud
from tests.backend.test_assistant import assistant_case, confirm
from tests.backend.test_assistant_architecture_v2 import stored, turn
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


@pytest.mark.skipif(os.getenv('FIXRATE_PIPELINE_ACTION_CHECK') != '1', reason='Opt-in live synthetic action')
def test_live_selection_assignment_and_confirmation(lab, monkeypatch):
    fixture, _, _, _, _, _, clients = lab
    engine, app, _, _, ids = fixture
    task_id, _, _, worker = schedule(lab)
    monkeypatch.setattr(app.state, 'settings', replace(app.state.settings, assistant_v3_pipeline='erp_operator'))
    monkeypatch.setattr(app.state, 'assistant_provider_factory', _cloud(), raising=False)
    client = clients['chief_engineer']
    result, actions, _ = turn(client, 'Найди ближайшее неназначенное ТО на завтра, подбери одного свободного '
                                     'исполнителя с действующим допуском, затем назначь его.')
    state = stored(fixture, result['turn_id'])
    output = Path(os.environ['FIXRATE_AGENT_AUDIT_OUTPUT']) / 'live-action.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {'outcome': state['outcome'], 'errors': state['erp_operator']['errors'],
                'trace': result.get('trace'), 'cards': len(actions)}
    output.write_text(json.dumps(evidence, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
    assert len(actions) == 1, evidence
    action = actions[0]
    assert action['arguments']['path']['task_id'] == task_id
    assert action['arguments']['body']['executor_ids'] == [worker]
    order = text('SELECT status,revision,planned_start_at,planned_end_at FROM work_orders WHERE work_order_id=:id')
    with engine.connect() as db:
        before = db.execute(order, {'id': task_id}).one()
    assert before.status == 'draft'
    denied = confirm(clients['executor'], action)
    assert denied.status_code in (403, 404)
    for _ in range(2):
        response = confirm(client, action)
        assert response.status_code == 200 and response.json()['result']['verification']['status'] == 'confirmed'
    with engine.connect() as db:
        after = db.execute(order, {'id': task_id}).one()
        audit = db.scalar(text("SELECT count(*) FROM audit_events WHERE site_id=:site AND entity_id=:task AND action='assign'"),
                          {**ids, 'task': task_id})
        assignment = db.execute(text('''SELECT user_id::text,start_at,end_at FROM work_assignments
            WHERE site_id=:site AND work_order_id=:task AND status NOT IN ('cancelled','declined')'''),
            {**ids, 'task': task_id}).one()
    assert after.status == 'assigned' and after.revision == before.revision + 1
    assert assignment == (worker, before.planned_start_at, before.planned_end_at)
    assert audit == 1
    evidence.update(verified=True, blocked_role_status=denied.status_code, audit_count=audit,
                    revision_increment=after.revision - before.revision)
    output.write_text(json.dumps(evidence, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
