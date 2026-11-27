"""Independent SQL-oracle cases against real FastAPI, LangGraph and Ollama."""
from contextlib import ExitStack, closing
from datetime import datetime, time, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from agent_reliability_lab.evals.corpus import CASES
from agent_reliability_lab.evals.oracle import UUID, expectations, grade, ledger
from tests.backend.test_assistant import B, assistant_case
from tests.backend.test_assistant_architecture_v2 import add_order, inventory, stored, turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_assistant_equipment_history import add_report
from tests.backend.test_management import config, join, managed
from tests.backend.test_runtime_integration import runtime


ZONE = ZoneInfo('Asia/Yekaterinburg')


@pytest.fixture
def lab(assistant_case):
    engine, app, admin, login, ids = assistant_case
    assert app.state.settings.assistant_agent_version == 'v3'
    assert not hasattr(app.state, 'assistant_provider_factory')
    now = datetime.now(timezone.utc)
    day = now.astimezone(ZONE).date()
    historical = day - timedelta(days=3)
    start = datetime.combine(day, time(10), ZONE)
    with engine.begin() as db:
        db.execute(text("UPDATE sites SET timezone='Asia/Yekaterinburg' WHERE site_id=:site"), ids)

    equipment = [inventory(admin, ids, code, name=name) for code, name in (
        ('ИТП-21', 'Узел тепловой рециркуляции'),
        ('КА-21', 'Шкаф защиты контура'),
        ('КА-210', 'Секция аварийного питания'),
    )]
    heat, cabinet, power = equipment
    own_late = add_order(assistant_case, [heat, cabinet], 'Снять показания контура', 'in_progress',
                         start - timedelta(days=6), start - timedelta(days=7))
    own_today = add_order(assistant_case, [cabinet], 'Сверить уставки защиты', 'assigned',
                          start + timedelta(days=2), start)
    own_future = add_order(assistant_case, [cabinet], 'Проверить резервную индикацию', 'assigned',
                           start + timedelta(days=4), start + timedelta(days=2))
    first_late = add_order(assistant_case, [power], 'Осмотр соединений секции', 'in_progress',
                           start - timedelta(days=12), start - timedelta(days=13))
    other_late = add_order(assistant_case, [power], 'Заменить маркировку шины', 'assigned',
                           start - timedelta(days=1), start - timedelta(days=2))
    done = add_order(assistant_case, [cabinet], 'Восстановить цепь сигнала', 'completed',
                     start - timedelta(days=10), start - timedelta(days=11))
    cancelled = add_order(assistant_case, [heat], 'Отменённая ревизия', 'cancelled',
                          start - timedelta(days=14), start - timedelta(days=16))
    worker, worker_email = join(assistant_case)
    other, _ = join(assistant_case)
    _, engineer_email = join(assistant_case, 'engineer')
    _, director_email = join(assistant_case, 'director')

    with engine.begin() as db:
        for asset, location in zip(equipment, ('Тепловой зал B3', 'Панель А7', 'Подстанция Р4'), strict=True):
            db.execute(text('UPDATE equipment SET location=:location WHERE equipment_id=:id'),
                       {'id': asset['equipment_id'], 'location': location})
        for user, tasks in [(worker, [own_late, own_today, own_future, done, cancelled]), (other, [first_late, other_late])]:
            for task in tasks:
                db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
                                   VALUES (:site,:task,:actor,:chief)'''), {**ids, 'task': task, 'actor': user})
        checklist = json.dumps({'checklist': [dict(id=str(uuid4()), text='Контроль сварного шва',
                                                 required=True, answerKind='boolean', photoRequired=True)]})
        db.execute(text('''UPDATE work_orders SET operation_snapshot=operation_snapshot||CAST(:checklist AS jsonb)
                           WHERE work_order_id=:id'''), {'id': first_late, 'checklist': checklist})

    for index, asset in enumerate(equipment):
        actual = start - timedelta(days=index + 9)
        submitted = actual + timedelta(hours=2)
        _, report = add_report(assistant_case, asset, actual=actual.isoformat(), submitted=submitted,
                               order_started=(actual-timedelta(hours=2)).isoformat())
        with engine.begin() as db:
            db.execute(text('UPDATE acceptance_reviews SET reviewed_at=:accepted WHERE work_report_id=:id'),
                       {'id': report, 'accepted': submitted + timedelta(days=1)})
        rule = admin.chief.post(f"/api/v1/maintenance/equipment/{asset['equipment_id']}/service-configurations",
                               json=config(day + timedelta(days=4), code=f'RELIABILITY-{index+1}',
                                           title=f'Порядок обслуживания секции {index+1}',
                                           valid_from=str(day - timedelta(days=90))))
        assert rule.status_code == 201, rule.text
    add_report(assistant_case, power, actual=(start-timedelta(days=2)).isoformat(),
               submitted=start-timedelta(days=1), acceptance=None)

    data = ledger(engine, ids['site'])
    # Per-scenario assertions further restrict which known IDs may be shown.
    known = set(UUID.findall(json.dumps(data, default=str))) | {str(ids['site']), str(ids['system'])}
    with ExitStack() as clients:
        sessions = {
            'chief_engineer': admin.chief,
            'engineer': clients.enter_context(closing(login(engineer_email))),
            'executor': clients.enter_context(closing(login(worker_email))),
            'director': clients.enter_context(closing(login(director_email))),
        }
        yield assistant_case, now, historical, worker, data, known, sessions


def artifact(case, outcome):
    private_root = Path(os.environ['FIXRATE_AGENT_AUDIT_OUTPUT']) / 'independent-v3'
    private_root.mkdir(parents=True, exist_ok=True)
    target = private_root / f'{case.id}.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(outcome, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    temporary.replace(target)


def digest_fixture(data):
    stable = {key: sorted(value, key=lambda row: json.dumps(row, sort_keys=True, default=str))
              if isinstance(value, list) else value for key, value in data.items()}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


def graph_events(caplog, identity):
    events = []
    for record in caplog.records:
        event, _, details = record.getMessage().partition(f' turn={identity} ')
        if details and event.startswith('assistant_graph_'):
            events.append({'event': event.removeprefix('assistant_graph_'),
                           **dict(piece.split('=', 1) for piece in details.split() if '=' in piece)})
    return events


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('case', CASES, ids=[case.id for case in CASES])
def test_independent_v3(lab, case, caplog):
    fixture, now, historical, worker, data, known, clients = lab
    client = clients[case.role]
    caplog.set_level(logging.INFO, logger='app.assistant.service')
    before = checksums(fixture)
    catalog = client.get(f'{B}/capabilities')
    assert catalog.status_code == 200, catalog.text
    outcome = dict(case=case.id, category=case.category, suite=case.suite, role=case.role,
                   fixture_sha256=digest_fixture(data),
                   evaluator_sha256={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                     for name in ('corpus.py', 'generated.py', 'holdout.py', 'oracle.py', Path(__file__).name)},
                   allowed_tools=[tool['name'] for tool in catalog.json()['tools']['assistant']], turns=[])
    chat = None
    try:
        for step in case.steps:
            day = now.astimezone(ZONE).date()
            prompt = step.prompt.format(today=day, historical=historical, month_ago=day-timedelta(days=30))
            expected = expectations(step.oracle, step.subjects, data, now, historical, worker, ZONE)
            started = perf_counter()
            response, actions, chat = turn(client, prompt, chat=chat)
            elapsed = round(perf_counter()-started, 4)
            identity = response['turn_id']
            state = stored(fixture, identity) or {}
            failures = grade(expected, response, state, actions, known)
            events = graph_events(caplog, identity)
            nodes = [event['node'] for event in events if event['event'] == 'node']
            outcome['turns'].append(dict(prompt=prompt, turn_id=identity, seconds=elapsed, expected=expected,
                                         answer=response.get('answer'), model=response.get('model_ref'),
                                         engine=response.get('execution_engine'), status=response.get('status'),
                                         error=response.get('error_code'), outcome=state.get('outcome'),
                                         stop_reason=state.get('stop_reason'), metrics=state.get('metrics', {}),
                                         graph=nodes, graph_events=events,
                                         trace=[{key: r[key] for key in ('tool','status','code','intent','seconds','attempts') if key in r}
                                                             for r in response.get('trace', [])],
                                         evidence=[{key: r[key] for key in ('id','goal_id','tool','entity','complete','limitations') if key in r}
                                                   for r in state.get('evidence', [])],
                                         requirements=state.get('request_spec', {}).get('requirements', []),
                                         failures=failures))
    finally:
        after = checksums(fixture)
        outcome['changed_tables'] = sorted(table for table, digest in after.items() if before[table] != digest)
        outcome['passed'] = (len(outcome['turns']) == len(case.steps) and not outcome['changed_tables']
                             and not any(entry['failures'] for entry in outcome['turns']))
        artifact(case, outcome)
    assert outcome['passed'], (case.id, [entry['failures'] for entry in outcome['turns']], outcome['changed_tables'])
