"""Keep a private wire/SQL transcript for each attempted laboratory episode."""
import hashlib
import json
import logging
import os
from pathlib import Path

import pytest
from sqlalchemy import text


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == 'call':
        item.lab_outcome = report.outcome


def evidence_refs(state):
    keys = ('id', 'goal_id', 'tool', 'status', 'entity', 'complete', 'limitations')
    return [{key: row[key] for key in keys if key in row} for row in state.get('evidence', [])]


@pytest.fixture(autouse=True)
def retain_http_transcript(request, caplog):
    output = os.environ.get('FIXRATE_AGENT_AUDIT_OUTPUT')
    if 'lab' not in request.fixturenames or not output:
        yield
        return
    fixture, _, _, _, _, _, _ = request.getfixturevalue('lab')
    engine, _, _, _, ids = fixture
    caplog.set_level(logging.INFO, logger='app.assistant.service')
    yield
    with engine.connect() as db:
        turns = db.execute(text('''SELECT c.role,t.turn_id,t.content,t.answer,t.status,t.error_code,
             t.execution_engine,t.model_ref,t.trace,t.workflow,
             EXTRACT(EPOCH FROM t.finished_at-t.created_at) AS api_seconds
             FROM assistant_turns t JOIN assistant_conversations c USING(conversation_id)
             WHERE c.site_id=:site ORDER BY t.created_at,t.turn_id'''), ids).mappings().all()
        actions = db.execute(text('''SELECT a.action_id,a.turn_id,a.tool_name,a.status
             FROM assistant_actions a JOIN assistant_conversations c USING(conversation_id)
             WHERE c.site_id=:site ORDER BY a.created_at,a.action_id'''), ids).mappings().all()
    records = [(record.getMessage()) for record in caplog.get_records('call')
               if record.name == 'app.assistant.service' and record.getMessage().startswith('assistant_graph_')]
    payload = dict(node=request.node.nodeid, outcome=getattr(request.node, 'lab_outcome', 'interrupted'),
                   turns=[], actions=[dict(action) for action in actions])
    for row in turns:
        item = dict(row)
        state = item.pop('workflow') or {}
        item.update(outcome=state.get('outcome'), stop_reason=state.get('stop_reason'), metrics=state.get('metrics'),
                    graph=[line for line in records if f' turn={item["turn_id"]} ' in line],
                    evidence=evidence_refs(state), requirements=state.get('request_spec', {}).get('requirements', []))
        payload['turns'].append(item)
    root = Path(output) / 'transcripts'
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:16]
    (root / f'{digest}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
