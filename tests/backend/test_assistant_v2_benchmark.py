"""Frozen engineering corpus with independent database expectations."""
import csv
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.assistant import orchestrator, service
from tests.backend.test_assistant import B, assistant_case
from tests.backend.test_assistant_architecture_v2 import CompoundProvider, add_order, engineering_case, inventory, item, stored, turn
from tests.backend.test_assistant_equipment_history import add_report
from tests.backend.test_management import join, managed
from tests.backend.test_runtime_integration import runtime


with (Path(__file__).parents[1] / 'fixtures/assistant-architecture-v2.tsv').open(encoding='utf-8') as stream:
    CASES = list(csv.DictReader(stream, delimiter='\t'))

LIVE = os.environ.get('FIXRATE_AGENT_LIVE') == '1'
TOOLS = {
    'equipment_details': 'equipment_read',
    'equipment_tasks': 'tasks_find',
    'latest_maintenance': 'equipment_service_history',
    'maintenance_history': 'equipment_service_history',
    'active_regulations': 'regulations_read',
    'maintenance_calendar': 'calendar_evidence',
}


def goals_for(oracle, request, subject, task):
    if oracle == 'card':
        return [item('equipment_details', request, subject=subject)]
    if oracle in ('open', 'overdue', 'partial', 'ambiguous', 'dynamic', 'foreign_role', 'assigned_role',
                  'open_owned_site', 'overdue_failure', 'recommend', 'other_unavailable'):
        period = 'overdue' if oracle in ('overdue', 'overdue_failure', 'ambiguous', 'dynamic', 'recommend', 'other_unavailable') else 'all'
        results = [item('equipment_tasks', request, subject=subject, period=period)]
        if oracle == 'recommend':
            results.append(item('recommend_actions', 'Предложи три возможных следующих действия для инженера',
                                subject=subject, recommendation_count=3))
        if oracle == 'other_unavailable':
            results.append(item('other', 'пришли расписание из неподключённого внешнего календаря', subject=None))
        return results
    if oracle.startswith(('latest', 'history')) or oracle in ('before_after_topic', 'self_correct'):
        kind = 'maintenance_history' if oracle.startswith('history') else 'latest_maintenance'
        return [item(kind, request, subject=subject)]
    if oracle.startswith('calendar'):
        return [item('maintenance_calendar', request, subject=subject)]
    if oracle.startswith('rules'):
        return [item('active_regulations', request, subject=subject)]
    if oracle == 'manufacturer':
        return [item('manufacturer_source', 'подтверди паспорт производителя', subject=None)]
    if oracle in ('propose_cancel', 'conditional', 'confirm_once', 'after_confirm'):
        return [item('cancel_task', request, subject=task)] + (
            [item('active_regulations', 'посмотри действующие регламенты НС-01', subject=subject)] if oracle == 'after_confirm' else [])
    if oracle == 'compound_write':
        return [item('edit_equipment', request, subject=subject)]
    if oracle == 'no_changes':
        return [item('equipment_details', 'Посмотри состояние НС-01', subject=subject),
                item('edit_equipment', 'Ничего не изменяй', subject=subject)]
    if oracle == 'recover':
        return [item('active_regulations', 'Прочитай действующие регламенты НС-01', subject=subject),
                item('latest_maintenance', 'проверь последнюю фактически принятую работу', subject=subject)]
    raise ValueError(oracle)


def order_rows(data, selected):
    with data['case'][0].connect() as db:
        return dict(db.execute(text("""SELECT w.work_order_id::text, w.regulatory_deadline_at
            FROM work_orders w JOIN work_order_equipment l USING (work_order_id, site_id)
            WHERE l.equipment_id=:asset AND w.status IN ('draft','assigned','clarification','rework',
                'in_progress','in_review')"""), {'asset': selected['equipment_id']}).all())


def confirm(client, action):
    return client.post(f"{B}/actions/{action['action_id']}/confirm", json={
        'confirmed': True, 'payload_sha256': action['payload_sha256']})


def write_case(case, result, state, findings, elapsed, controlled):
    if 'FIXRATE_AGENT_AUDIT_OUTPUT' not in os.environ:
        return
    out = Path(os.environ['FIXRATE_AGENT_AUDIT_OUTPUT'])
    out.mkdir(exist_ok=True, parents=True)
    (out / f"{case['id']}.json").write_text(json.dumps(dict(case=case,
        profile='local_qwen' if LIVE and not controlled else 'scripted_intent_real_http',
        status=result['status'], outcome=(state or {}).get('outcome'),
        answer=result['answer'], trace=result['trace'], metrics=(state or {}).get('metrics'),
        claims=findings, latency_seconds=elapsed), ensure_ascii=False, indent=2), encoding='utf-8')


@pytest.mark.parametrize('case', CASES, ids=[case['id'] for case in CASES])
def test_architecture_v2_corpus(engineering_case, monkeypatch, case, request):
    data = engineering_case
    engine, app, admin, login, ids = data['case']
    selected = data[case['asset']]
    subject = selected['asset_code']
    oracles = case['oracle'].split(',')
    primary = oracles[0]
    prompt = case['request'].format(day=data['obligation'], task=data['upcoming'])
    client, chat = admin.chief, None
    providers = [service.provider]
    monkeypatch.setattr(app.state, 'assistant_provider_factory', lambda: providers[0](), raising=False)
    now = datetime.now(timezone.utc)
    if primary == 'ambiguous':
        inventory(admin, ids, 'НС-97', name=data['asset']['name'])
        subject = data['asset']['name']
    if primary in ('partial', 'history_partial'):
        for index in range(26):
            if primary == 'partial':
                add_order(data['case'], [selected], f'Строка проверки {index}', 'draft', now + timedelta(days=3), None)
            else:
                add_report(data['case'], selected)
    if primary == 'latest_gap':
        add_report(data['case'], selected, actual=None)
    if primary == 'latest_conflict':
        add_report(data['case'], selected, decision_actual='2026-01-03T08:00:00+00:00')
    if primary == 'rules_expired':
        with engine.begin() as db:
            db.execute(text("UPDATE rule_equipment SET valid_to='2025-12-31' WHERE binding_id=:id"), {'id': data['rule']})
    if primary in ('foreign_role', 'assigned_role'):
        worker, address = join(data['case'])
        client = login(address)
        request.addfinalizer(client.close)
        if primary == 'assigned_role':
            with engine.begin() as db:
                db.execute(text("""INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
                    VALUES (:site,:task,:worker,:actor)"""),
                    dict(site=ids['site'], task=data['upcoming'], worker=worker, actor=ids['user']))
    if primary == 'open_owned_site':
        foreign_site, foreign_system, foreign_asset = uuid4(), uuid4(), uuid4()
        foreign_ids = dict(site=foreign_site, system=foreign_system, asset=foreign_asset, current=selected['equipment_id'])
        with engine.begin() as db:
            db.execute(text("INSERT INTO sites(site_id,name) VALUES (:site,'Другая учебная площадка')"), foreign_ids)
            db.execute(text("""INSERT INTO engineering_systems(system_id,site_id,code,name)
                VALUES (:system,:site,'FOREIGN','Другая насосная группа')"""), foreign_ids)
            db.execute(text("""INSERT INTO equipment(equipment_id,site_id,system_id,equipment_type_id,asset_code,name,commissioned_on)
                SELECT :asset,:site,:system,equipment_type_id,asset_code,name,commissioned_on
                FROM equipment WHERE equipment_id=:current"""), foreign_ids)

        def cleanup_foreign():
            with engine.begin() as db:
                db.execute(text("DELETE FROM equipment WHERE equipment_id=:asset"), foreign_ids)
                db.execute(text("DELETE FROM engineering_systems WHERE system_id=:system"), foreign_ids)
                db.execute(text("DELETE FROM sites WHERE site_id=:site"), foreign_ids)

        request.addfinalizer(cleanup_foreign)
    if primary in ('overdue_failure', 'latest_failure', 'latest_denied'):
        read = orchestrator.read_tool
        failed_tool = 'tasks_find' if primary == 'overdue_failure' else 'equipment_service_history'
        http_status = 403 if primary == 'latest_denied' else 503

        async def fail_target(app, tool, arguments, *args, **kwargs):
            if tool.name == failed_tool:
                raise HTTPException(http_status, 'Недоступен контрольный источник.')
            return await read(app, tool, arguments, *args, **kwargs)

        monkeypatch.setattr(orchestrator, 'read_tool', fail_target)
    if primary in ('before_after_topic', 'self_correct', 'dynamic'):
        previous_asset = data['other'] if primary != 'dynamic' else selected
        previous_prompt = (f'Проверь просроченные задания {subject}.' if primary == 'dynamic' else
                           f"Проверь последнее фактическое обслуживание {previous_asset['asset_code']}.")
        first_intent = 'equipment_tasks' if primary == 'dynamic' else 'latest_maintenance'
        prior_provider = CompoundProvider([item(first_intent, previous_prompt, subject=previous_asset['asset_code'],
                                               period='overdue' if primary == 'dynamic' else None)])
        providers[0] = service.provider if LIVE else lambda: prior_provider
        previous, _, chat = turn(client, previous_prompt)
        assert previous['status'] == 'completed', previous['answer']
        if primary == 'dynamic':
            with engine.begin() as db:
                db.execute(text("UPDATE work_orders SET regulatory_deadline_at=now()+interval '7 days' WHERE work_order_id=:id"),
                           {'id': data['overdue']})

    rows = order_rows(data, selected)
    expected = [result for oracle in oracles for result in goals_for(oracle, prompt, subject, data['upcoming'])]
    # Fault injection and dispatch/resume cases stress the server independently
    # of semantic model variation. The ordinary cases also run on pinned Qwen.
    controlled = primary in {'recover', 'after_confirm', 'no_changes', 'latest_denied', 'latest_failure', 'overdue_failure'}
    providers[0] = service.provider if LIVE and not controlled else lambda: CompoundProvider(expected)
    start = perf_counter()
    result, actions, chat = turn(client, prompt, chat=chat)
    state = stored(data['case'], result['turn_id'])
    findings = []

    def claim(label, supported, *, actual=None, expected=None, failure='CONTRADICTED'):
        findings.append(dict(claim=label, grade='SUPPORTED' if supported else failure, actual=actual, expected=expected))

    claim('transport_completed', result['status'] == 'completed', actual=result['status'], expected='completed')
    proof_rows = (state or {}).get('evidence', [])
    for objective in expected:
        target = TOOLS.get(objective.intent)
        if not target:
            continue
        matching = [proof for proof in proof_rows if proof['tool'] == target and
                    (target != 'tasks_find' or proof['arguments'].get('query', {}).get('period') == objective.period)]
        if primary in ('ambiguous', 'calendar_invalid', 'foreign_role'):
            claim('no_authorized_entity_read', not matching, expected='no final read')
            continue
        if not matching:
            claim(target, False, expected='verified source', failure='UNSUPPORTED')
            continue
        proof = matching[-1]
        value = proof['result']
        if primary in ('latest_failure', 'latest_denied', 'overdue_failure'):
            disposition = 'FORBIDDEN' if primary == 'latest_denied' else 'UNAVAILABLE'
            claim('retained_error_class', proof['status'] == disposition and value is None,
                  actual=proof['status'], expected=disposition)
            claim('no_false_absence', 'нет' not in result['answer'])
            continue
        entity = proof.get('entity', {}).get('equipment_id')
        claim(target + ':equipment', entity == selected['equipment_id'], actual=entity, expected=selected['equipment_id'])
        if target == 'tasks_find':
            wanted = {identity for identity, deadline in rows.items() if objective.period != 'overdue' or deadline and deadline < now}
            if primary == 'assigned_role':
                wanted &= {data['upcoming']}
            found = {task['id'] for task in value.get('items', [])} if isinstance(value, dict) else set()
            claim('scoped_task_rows', wanted == found, expected=sorted(wanted), actual=sorted(found))
            claim('task_page_coverage', proof['complete'] is (primary != 'partial'))
        elif target == 'equipment_service_history':
            report = data['accepted'] if case['asset'] == 'asset' else data['other_report'] if case['asset'] == 'other' else None
            found = {entry['report_id'] for entry in value.get('items', [])} if isinstance(value, dict) else set()
            if primary == 'history_empty':
                report = None
            if primary in ('latest_gap', 'latest_conflict', 'history_partial'):
                claim('uncertainty_preserved', proof['status'] == 'PARTIAL' and not proof['complete'], actual=proof['status'])
            else:
                claim('accepted_report_identity', found == ({report} if report else set()), actual=sorted(found), expected=report)
                if report:
                    claim('report_visible_in_answer', report in result['answer'])
        elif target == 'regulations_read':
            rule = case['asset'] == 'asset' and primary != 'rules_expired'
            claim('current_regulation_in_answer', (data['rule'] in result['answer']) == rule)
        elif target == 'calendar_evidence':
            active = case['asset'] == 'asset' and primary != 'calendar_empty'
            actual = {item['effective_date'] for config in value.get('configurations', [])
                      for item in config['occurrences']} if isinstance(value, dict) else set()
            claim('calendar_dates', actual == ({data['obligation']} if active else set()),
                  actual=sorted(actual), expected=[data['obligation']] if active else [])
    if primary in ('propose_cancel', 'compound_write', 'confirm_once', 'after_confirm'):
        target = 'equipment_edit' if primary == 'compound_write' else 'task_cancel'
        claim('separate_confirmation', [(item['tool_name'], item['status']) for item in actions] == [(target, 'proposed')])
        if actions and primary in ('confirm_once', 'after_confirm'):
            before = service.now()
            confirmed = confirm(client, actions[0])
            again = confirm(client, actions[0])
            with engine.connect() as db:
                status, revision = db.execute(text('SELECT status,revision FROM work_orders WHERE work_order_id=:id'),
                                              {'id': data['upcoming']}).one()
                audit = db.scalar(text("""SELECT count(*) FROM audit_events WHERE entity_id=:action
                    AND action='confirmed' AND occurred_at>=:before"""),
                    dict(action=actions[0]['action_id'], before=before))
            claim('dispatch_once', confirmed.is_success and again.is_success and status == 'cancelled'
                  and revision == 2 and audit == 1)
            if primary == 'after_confirm':
                view = client.get(f'{B}/conversations/{chat}').json()
                resumed = next(item for item in view['turns'] if item['turn_id'] == result['turn_id'])
                claim('confirmation_readback', any(goal['status'] == 'completed' and goal['tool'] == 'task_cancel'
                      for goal in resumed['workflow']['goals']))
    else:
        claim('no_side_effect_proposal', not actions)
    if primary == 'recommend':
        claim('three_separate_recommendations', 'Рекомендации' in result['answer'] and '\n3. ' in result['answer'])
    if primary == 'other_unavailable':
        claim('unsupported_goal_visible', any(goal.get('semantic', {}).get('intent') == 'other' and
              goal['status'] == 'blocked' for goal in (state or {}).get('goals', [])), failure='UNVERIFIABLE')
    if primary == 'recover' and state:
        pending = next(goal for goal in state['goals'] if goal['tool'] == 'equipment_service_history')
        pending['status'] = 'running'
        with engine.begin() as db:
            db.execute(text("""UPDATE assistant_turns SET status='running',finished_at=NULL,deadline_at=now()-interval '1 second',
                workflow=CAST(:workflow AS jsonb) WHERE turn_id=:id"""),
                {'id': result['turn_id'], 'workflow': json.dumps(state)})
        continuation, _, _ = turn(client, 'Продолжи сохранённую проверку.', chat=chat, resume=result['turn_id'])
        claim('resumed_only_incomplete_step', continuation['status'] == 'completed' and
              [entry['tool'] for entry in continuation['trace']] == ['equipment_find', 'equipment_service_history'])
    write_case(case, result, state, findings, perf_counter() - start, controlled)
    assert findings and all(finding['grade'] == 'SUPPORTED' for finding in findings), (findings, result['answer'])
