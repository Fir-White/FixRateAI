"""Run A/B/C against the same private synthetic SQL snapshot, through real assistant HTTP."""
from collections import Counter
from contextlib import ExitStack, closing
from dataclasses import asdict, replace
from datetime import datetime, time, timedelta
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import re
from time import perf_counter
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
import pytest
from sqlalchemy import text

from agent_reliability_lab.pipeline_cases import conversations
from agent_reliability_lab.summarize_pipeline_comparison import reports_quantity
from ml_service.app.providers.aitunnel import AITunnelClient, AITunnelConfig
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import add_order, inventory, stored, turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_assistant_equipment_history import add_report
from tests.backend.test_management import config, join, managed
from tests.backend.test_runtime_integration import runtime


ZONE = ZoneInfo('Asia/Yekaterinburg')
CASES = conversations()
OPEN = {'draft', 'assigned', 'clarification', 'rework', 'in_progress', 'in_review'}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


@pytest.fixture
def pipeline_fixture(assistant_case):
    engine, app, admin, login, ids = assistant_case
    now = datetime.now(ZONE)
    today = now.date()
    days = dict(today=today, tomorrow=today + timedelta(days=1), next_day=today + timedelta(days=2),
                yesterday=today - timedelta(days=1))
    worker, executor_email = join(assistant_case)
    second, _ = join(assistant_case)
    _, engineer_email = join(assistant_case, 'engineer')
    _, director_email = join(assistant_case, 'director')
    with engine.begin() as db:
        db.execute(text("UPDATE sites SET timezone='Asia/Yekaterinburg' WHERE site_id=:site"), ids)

    for index, name in enumerate(('Коллектор Роса', 'Шкаф Рубин', 'Насос Ритм', 'Редуктор Север',
                                  'Сепаратор Сфера', 'Пульт Сигнал', 'Стенд Архив'), 1):
        asset = inventory(admin, ids, f'КС-{60+index}', name=name)
        category = 'ТО1' if index % 2 else 'ТО2'
        result = admin.chief.post(f'/api/v1/maintenance/equipment/{asset["equipment_id"]}/service-configurations',
                                  json=config(days['tomorrow'], code=f'LAB-OP-{index}', title=f'Регламент {name}',
                                              maintenance_type=category, valid_from=(today-timedelta(days=80)).isoformat()))
        assert result.status_code == 201, result.text
        binding = result.json()['binding_id']
        asset_id = asset['equipment_id']
        jobs = []
        for status, day, hour, title in (
            ('draft', 'tomorrow', 7, f'Черновой обход · сектор {index}'),
            ('assigned', 'tomorrow', 9, f'Назначенная проверка · сектор {index}'),
            ('assigned', 'next_day', 8, f'Контроль после смены · сектор {index}'),
        ):
            start = datetime.combine(days[day], time(hour, index * 5), ZONE)
            jobs.append((add_order(assistant_case, [asset], title, status, start+timedelta(hours=3), start), start, status))
        if index in (1, 2, 3):
            earlier = datetime.combine(today-timedelta(days=5), time(9), ZONE)
            accepted = index != 2
            task = add_order(assistant_case, [asset], f'Завершённая работа · сектор {index}',
                             'completed' if accepted else 'in_review', earlier+timedelta(hours=4), earlier)
            add_report(assistant_case, asset, task=task, actual=earlier.isoformat(), submitted=earlier+timedelta(hours=1),
                       acceptance='accepted' if accepted else None)
            jobs.append((task, earlier, 'history'))
        with engine.begin() as db:
            rule = db.scalar(text('SELECT maintenance_rule_id FROM rule_equipment WHERE binding_id=:binding'), dict(binding=binding))
            db.execute(text('''UPDATE equipment SET status=CASE WHEN :retired THEN 'retired' ELSE status END,
                location=:location, properties=properties||jsonb_build_object('data_origin','synthetic_demo')
                WHERE equipment_id=:asset'''), dict(retired=index == 7, asset=asset_id, location=f'Учебный отсек {index}'))
            db.execute(text("UPDATE maintenance_rules SET data_origin='synthetic_demo' WHERE maintenance_rule_id=:rule"), dict(rule=rule))
            for task, start, status in jobs:
                if index == 7 and status != 'history':
                    status = 'cancelled'
                db.execute(text('''UPDATE work_orders SET maintenance_rule_id=:rule,
                    status=CASE WHEN :cancelled THEN 'cancelled' ELSE status END,
                    planned_end_at=planned_start_at+interval '30 minutes',
                    operation_snapshot=operation_snapshot||jsonb_build_object('data_origin','synthetic_demo')
                    WHERE work_order_id=:task'''), dict(rule=rule, task=task, cancelled=status == 'cancelled'))
                if status in ('assigned', 'history'):
                    db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
                        VALUES (:site,:task,:worker,:chief)'''), {**ids, 'task': task,
                        'worker': worker if index in (1, 2, 4, 5) else second})

    with ExitStack() as clients:
        sessions = {'chief_engineer': admin.chief, 'engineer': clients.enter_context(closing(login(engineer_email))),
                    'director': clients.enter_context(closing(login(director_email))),
                    'executor': clients.enter_context(closing(login(executor_email)))}
        yield assistant_case, sessions, _ledger(engine, ids['site']), days, str(worker)


def _ledger(engine, site):
    with engine.connect() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        queries = dict(equipment='''SELECT equipment_id::text AS id, asset_code AS code,name,location,status,
            properties->>'data_origin' AS origin FROM equipment WHERE site_id=:site ORDER BY asset_code''',
            tasks='''SELECT w.work_order_id::text AS id,l.equipment_id::text AS asset,w.status,
            w.planned_start_at AS start,w.operation_snapshot->>'title' AS title,w.operation_snapshot->>'data_origin' AS origin,
            a.user_id::text AS worker FROM work_orders w JOIN work_order_equipment l USING(site_id,work_order_id)
            LEFT JOIN work_assignments a ON a.site_id=w.site_id AND a.work_order_id=w.work_order_id
            AND a.status NOT IN ('declined','cancelled') WHERE w.site_id=:site ORDER BY w.planned_start_at,w.work_order_id''',
            accepted='''SELECT r.work_report_id::text AS id,r.work_order_id::text AS task,
            a.reviewed_at FROM work_reports r JOIN acceptance_reviews a USING(site_id,work_order_id,work_report_id)
            WHERE r.site_id=:site AND a.decision='accepted' ORDER BY a.reviewed_at DESC,r.work_report_id''',
            rules='''SELECT b.equipment_id::text AS asset,b.binding_id::text AS id,
            o.code, o.title, m.name AS type, m.code AS type_code, r.data_origin AS origin
            FROM rule_equipment b JOIN maintenance_rules r USING(site_id,maintenance_rule_id)
            JOIN operation_templates o USING(site_id,operation_template_id) JOIN maintenance_types m USING(maintenance_type_id)
            JOIN regulation_editions ed USING(site_id,regulation_edition_id)
            WHERE b.site_id=:site AND r.publication_status='published' AND o.is_active AND ed.is_approved
            ORDER BY m.code,o.code''')
        result = {name: [dict(row) for row in db.execute(text(sql), dict(site=site)).mappings()]
                  for name, sql in queries.items()}
    assert all(row['origin'] == 'synthetic_demo' for name in ('equipment', 'tasks', 'rules') for row in result[name])
    return result


def _expected(check, ledger, days, role, worker):
    opts = check.options
    equipment, tasks = ledger['equipment'], ledger['tasks']
    if role == 'executor':
        tasks = [row for row in tasks if row['worker'] == worker]
        equipment = [row for row in equipment if row['id'] in {task['asset'] for task in tasks}]
    ids = {row['id'] for row in equipment}
    task_assets = {row['id']: row['asset'] for row in tasks}
    accepted = {task_assets[row['task']] for row in ledger['accepted'] if row['task'] in task_assets}
    assets = {row['id'] for row in equipment if not opts.get('code') or opts['code'] == row['code']}
    if coverage := opts.get('coverage'):
        assets &= {row['id'] for row in equipment if row['status'] != 'retired'
                   and (row['id'] in accepted) == (coverage == 'present')}
    match check.source:
        case 'equipment' | 'card':
            universe = ledger['equipment']
            selected = [row for row in equipment if row['id'] in assets]
        case 'tasks':
            universe = ledger['tasks']
            selected = [row for row in tasks if row['asset'] in assets and row['status'] in OPEN and
                        (not opts.get('state') or opts['state'] == row['status']) and
                        row['start'].astimezone(ZONE).date() == days[opts['day']]]
        case 'types' | 'operations' | 'regulation':
            universe = ledger['rules']
            selected = [row for row in universe if row['asset'] in ids]
            if check.source != 'regulation':
                active = {row['id'] for row in equipment if row['status'] != 'retired'}
                selected = [row for row in selected if row['asset'] in active]
            if check.source == 'types':
                return dict(required=sorted({row['type'] for row in selected}), excluded=[], count=None, empty=False)
            if check.source == 'operations':
                type_codes = sorted({row['type_code'] for row in selected})
                selected = [row for row in selected if row['type_code'] == type_codes[opts['position']-1]]
            else:
                selected = [row for row in selected if row['asset'] in assets]
        case 'history':
            universe = ledger['accepted']
            selected = [row for row in universe if task_assets.get(row['task']) in assets][:1]
    total = len(selected)
    shown = selected[:opts.get('limit', total)]
    field = ('code' if check.source in ('equipment', 'card') else 'id' if check.source == 'history' else 'title')
    blocked = (check.source == 'equipment' and not shown or check.source == 'tasks' and opts.get('code') and not assets)
    return dict(required=[] if opts.get('count') else [row[field] for row in shown],
                excluded=[row.get(field) for row in universe if row not in shown and row.get(field)],
                count=total if opts.get('count') else None, empty=not shown, can_deny=blocked,
                date=days[opts['day']].isoformat() if opts.get('day') and shown and not opts.get('count') else None)


def _judge(check, expected, response, state, actions):
    answer = (response.get('answer') or '').casefold()
    errors = []
    if response['status'] != 'completed':
        errors.append('turn_' + str(response['status']))
    if actions:
        errors.append('unexpected_action')
    for token in expected['required']:
        if not re.search(r'(?<!\w)' + re.escape(token.casefold()) + r'(?!\w)', answer):
            errors.append('missing:' + token)
    quoted = check.prompt.casefold()
    for token in expected['excluded']:
        if token.casefold() not in quoted and re.search(r'(?<!\w)' + re.escape(token.casefold()) + r'(?!\w)', answer):
            errors.append('extra:' + token)
    if expected.get('date') and expected['date'] not in answer:
        errors.append('date_missing')
    if expected['count'] is not None and not reports_quantity(answer, expected['count']):
        errors.append('quantity_not_reported')
    if expected['empty'] and not re.search(r'\b(?:нет|0|пуст\w*|не\s+(?:найден\w*|доступ\w*|удалось))\b', answer):
        errors.append('empty_or_denial_missing')
    sources = {'equipment': {'equipment_find', 'equipment_read'}, 'card': {'equipment_read'}, 'tasks': {'tasks_find', 'calendar_read'},
               'history': {'equipment_service_history'}, 'regulation': {'regulations_read'},
               'types': {'maintenance_catalog_read'}, 'operations': {'maintenance_catalog_read'}}
    receipts = [receipt for receipt in state.get('evidence', []) if receipt.get('retained') and receipt.get('result') is not None]
    verified = {receipt['tool'] for receipt in receipts}
    denied = {row['tool'] for row in response.get('trace', []) if row.get('code') == 404 or row.get('code') == 403}
    if not sources[check.source].intersection(verified | (denied if expected.get('can_deny') else set())):
        errors.append('wrong_or_missing_source')
    if coverage := check.options.get('coverage'):
        key = 'equipment_accepted_maintenance' if check.source == 'tasks' else 'accepted_maintenance'
        if not any(isinstance(receipt['result'], dict) and receipt['result'].get('filters', {}).get(key) == coverage
                   for receipt in receipts):
            errors.append('accepted_history_scope_unverified')
    return errors


def _cloud():
    values = dotenv_values(os.environ['FIXRATE_PIPELINE_CLOUD_CONFIG'], interpolate=False)
    explicit = {key: values[key] for key in ('AITUNNEL_API_KEY', 'AI_TUNNEL_API_KEY', 'AITUNNEL_BASE_URL') if values.get(key)}
    explicit.update(AITUNNEL_CHAT_MODEL='deepseek-v4-flash', AITUNNEL_TIMEOUT_SECONDS='70')
    result = AITunnelConfig.from_environment('chat', explicit)
    if not result.api_key:
        raise RuntimeError('C requires a configured AI Tunnel key')
    return partial(AITunnelClient, result)


@pytest.mark.skipif(os.getenv('FIXRATE_PIPELINE_COMPARE') != '1', reason='Opt-in live pipeline comparison')
def test_pipeline_comparison(pipeline_fixture, monkeypatch):
    fixture, clients, ledger, days, worker = pipeline_fixture
    app = fixture[1]
    assert app.state.settings.assistant_agent_version == 'v3'
    output = Path(os.environ['FIXRATE_AGENT_AUDIT_OUTPUT']) / 'pipeline-comparison'
    output.mkdir(parents=True, exist_ok=True)
    selected = set(filter(None, os.getenv('FIXRATE_PIPELINE_CASES', '').split(',')))
    cases = [case for case in CASES if not selected or case.id in selected]
    assert cases and (not selected or {case.id for case in cases} == selected)
    variants = os.getenv('FIXRATE_PIPELINE_VARIANTS', 'AB')
    assert variants and len(variants) == len(set(variants)) and not set(variants) - set('ABCDE')
    manifest = dict(corpus=_hash([asdict(case) for case in cases]), sql_snapshot=_hash(ledger), days=days,
                    variants=variants, cases=len(cases), synthetic=True)
    (output/'manifest.json').write_text(json.dumps(manifest, default=str, indent=2), encoding='utf-8')
    initial = checksums(fixture)
    summary = {}
    for variant in variants:
        counts = Counter()
        with monkeypatch.context() as settings:
            pipeline = {'A': 'v3', 'B': 'llm_dynamic', 'C': 'llm_dynamic',
                        'D': 'erp_operator', 'E': 'erp_operator'}[variant]
            settings.setattr(app.state, 'settings', replace(app.state.settings, assistant_v3_pipeline=pipeline))
            if variant in ('C', 'E'):
                settings.setattr(app.state, 'assistant_provider_factory', _cloud(), raising=False)
            with (output/f'{variant}.jsonl').open('w', encoding='utf-8') as log:
                for case in cases:
                    chat = None
                    observations = []
                    prior_task = None
                    for check in case.turns:
                        started = perf_counter()
                        prompt = check.prompt.format(**days)
                        response, actions, chat = turn(clients[case.role], prompt, chat=chat)
                        state = stored(fixture, response['turn_id']) or {}
                        expected = _expected(check, ledger, days, case.role, worker)
                        failures = _judge(check, expected, response, state, actions)
                        operator = state.get('erp_operator', {})
                        observations.append(dict(prompt=prompt, answer=response.get('answer'), expected=expected,
                            failures=failures, actions=len(actions), seconds=perf_counter()-started,
                            model=response.get('model_ref'), outcome=state.get('outcome'), error_code=response.get('error_code'),
                            trace=response.get('trace', []), metrics=state.get('metrics', {}),
                            operator_errors=operator.get('errors', []), operator_task_before=prior_task,
                            operator_task=operator.get('task'), operator_transition=operator.get('transition'),
                            operator_contract=operator.get('semantic'), verified_receipt=operator.get('verified_receipt')))
                        prior_task = operator.get('task')
                    passed = all(not row['failures'] for row in observations)
                    counts.update(conversations=1, passed=int(passed), turns=len(observations),
                                  turns_passed=sum(not row['failures'] for row in observations),
                                  unexpected_actions=sum(row['actions'] for row in observations))
                    print(variant, case.id, 'pass' if passed else 'fail', [row['failures'] for row in observations], flush=True)
                    log.write(json.dumps(dict(case=case.id, role=case.role, passed=passed, turns=observations),
                                         ensure_ascii=False, default=str) + '\n')
                    log.flush()
        summary[variant] = dict(counts)
        (output/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        final = checksums(fixture)
        assert final == initial, [name for name in final if final[name] != initial[name]]
    assert all(result['unexpected_actions'] == 0 for result in summary.values()), summary
