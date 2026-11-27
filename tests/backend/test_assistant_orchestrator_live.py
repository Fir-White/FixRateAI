"""Same goal/data oracles for baseline and changed local-model orchestration.

Opt in through verify_agent_local.py. Every record is synthetic and every write
uses the existing human-confirmation HTTP route on disposable PostgreSQL. These
tests accept different valid tool sequences; HTTP completion alone is no oracle.
"""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import json
import os
import re
import hashlib

import pytest
from sqlalchemy import text

from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed, config
from tests.backend.test_assistant import assistant_case, B, thread, confirm
from tests.backend.test_agent_redteam_live import live_case
from tests.backend.test_agent_redteam_matrix import fingerprint


pytestmark = pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1',
                                reason='Explicit installed Ollama and disposable PostgreSQL only')


def send(case, chat, question):
    client = case['client']
    sent = client.post(B + f'/conversations/{chat}/messages',
                       json=dict(content=question, idempotency_key=str(uuid4())))
    assert sent.status_code == 202, sent.text
    view = client.get(B + '/conversations/' + chat).json()
    assert view['turns'], view
    return view, view['turns'][-1]


@contextmanager
def episode(case, identity):
    from app.assistant import service
    outcome = dict(case=identity, kind='compound-goal', at=datetime.now(timezone.utc).isoformat(),
                   model='qwen3.5:4b-q4_K_M', steps=[], imported_service_file=str(Path(service.__file__).resolve()))
    outcome['fixture_sha256']=hashlib.sha256(json.dumps(fingerprint(case['engine']),sort_keys=True,default=str).encode()).hexdigest()
    outcome['actual_dataset_snapshot_sha256']=outcome['fixture_sha256']
    outcome['fixture_version']='orchestrator-compound-v3'
    started = perf_counter()
    try:
        if os.environ.get('FIXRATE_VERIFICATION_SOURCE_ROOT'):
            assert Path(service.__file__).resolve() == Path(os.environ['FIXRATE_VERIFICATION_SOURCE_ROOT']).resolve() / 'backend/app/assistant/service.py', 'The baseline and changed Python sources must not mix'
        yield outcome
        outcome['outcome'] = 'passed'
    except BaseException as error:
        outcome.update(outcome='failed', error_type=type(error).__name__)
        raise
    finally:
        outcome.update(latency_seconds=round(perf_counter() - started, 3),
                       model_calls=case['calls'], tool_evidence=case['evidence'], cost=None,
                       execution_mode='model-inference' if case['calls'] else 'server-deterministic')
        out = Path(os.environ['FIXRATE_AGENT_AUDIT_OUTPUT'])
        out.mkdir(parents=True, exist_ok=True)
        (out / (identity + '.json')).write_text(json.dumps(outcome, ensure_ascii=False, default=str, indent=2), encoding='utf-8')


def add_equipment(case, code, name):
    result = case['admin'].post('/api/v1/maintenance/equipment', json=dict(
        system_id=str(case['ids']['system']), equipment_type_id=str(case['ids']['type']),
        asset_code=code, name=name, commissioned_on='2023-11-16'))
    assert result.status_code == 201, result.text
    return result.json()


def record(outcome, view, turn, question):
    outcome['steps'].append(dict(kind='answer', question=question, answer=turn['answer'],
                                 status=turn['status'], error_code=turn.get('error_code'),
                                 trace=turn['trace'], actions=view['actions'],
                                 goal_state=turn.get('workflow') or turn.get('task_state')))


def mentions_date(answer, value):
    """Accept ISO, dotted dates or Russian day/month names with an actual year."""
    day = date.fromisoformat(value)
    if value in answer or day.strftime('%d.%m.%Y') in answer:
        return True
    months = ('январ', 'феврал', 'март', 'апрел', 'мая', 'июн',
              'июл', 'август', 'сентябр', 'октябр', 'ноябр', 'декабр')
    plain = answer.replace('*', '').replace('_', '')
    return bool(re.search(r'\b0?' + str(day.day) + r'\s+' + months[day.month - 1] + r'[а-я]*\s+' + str(day.year) + r'\b', plain))


def test_inventory_regulations_and_planning_gaps_include_equipment_without_tasks(live_case):
    c = live_case
    orphan = add_equipment(c, 'RT-ORPHAN', 'Independent orphan unit')
    draft = c['client'].post('/api/v1/maintenance/equipment/' + orphan['equipment_id'] + '/service-configurations',
                             json=config(date(2026, 11, 16), code='RT-DRAFT', title='Draft orphan operation',
                                         enabled=False, norm_value=None, norm_unit='unconfirmed',
                                         duration_minutes=None, methodology_ref=None))
    assert draft.status_code == 201, draft.text
    with c['engine'].connect() as db:
        assert db.scalar(text('SELECT count(*) FROM work_order_equipment WHERE equipment_id=:id'), dict(id=orphan['equipment_id'])) == 0
        equipment_count = db.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site'), dict(site=c['ids']['site']))
        assert equipment_count == 2
    before = fingerprint(c['engine'])
    question = ('Проанализируй все оборудование текущего объекта, включая оборудование без заданий. '
                'Покажи опубликованные и неопубликованные регламенты и где не хватает данных для планирования. '
                'Ничего не изменяй. Перечисли каждую единицу с инвентарным кодом.')
    with episode(c, 'ORCH-A01-inventory-regulations-gaps') as outcome:
        view, turn = send(c, thread(c['client']), question)
        record(outcome, view, turn, question)
        answer = turn['answer'].casefold()
        assert 'rt-pump' in answer and 'rt-orphan' in answer, turn['answer']
        assert re.search(r'неопублик|чернов|не утвержд|не подтвержд|не опублик', answer), turn['answer']
        assert re.search(r'пробел|не хват|недостат|отсутств|не подтвержд', answer), turn['answer']
        assert not view['actions']
        assert fingerprint(c['engine']) == before
        if turn.get('workflow'):
            assert all(goal['status']=='completed' for goal in turn['workflow']['goals']), turn['workflow']
        outcome['expected_data'] = dict(equipment=equipment_count, orphan_tasks=0, published_operations=1, draft_operations=1)


def test_nc01_period_history_and_unverified_manufacturer_are_separate_goals(live_case):
    c = live_case
    pump = add_equipment(c, 'НС-01', 'Pump with five annual obligations')
    saved = c['client'].post('/api/v1/maintenance/equipment/' + pump['equipment_id'] + '/service-configurations',
                            json=config(date(2023, 11, 16), code='NC-ANNUAL-5', title='Five annual inspections',
                                        pattern=dict(frequency='yearly_count', interval=1, count_per_year=5,
                                                     annual_policy='from_anchor', anchor_date='2023-11-16',
                                                     weekend_policy='next_workday')))
    assert saved.status_code == 201, saved.text
    with c['engine'].connect() as db:
        history_count = db.scalar(text('SELECT count(*) FROM work_order_equipment WHERE equipment_id=:id'), dict(id=pump['equipment_id']))
    assert history_count == 0
    before = fingerprint(c['engine'])
    question = ('Объясни периодичность НС-01 по сохраненному регламенту и штатному алгоритму календаря '
                'для цикла с 16.11.2026 по 15.11.2027: сколько обязательств, что означает интервал 1 '
                'и число повторов 5. Перечисли все исходные и перенесенные даты в этом цикле. '
                'Отдельно проверь фактическую историю обслуживаний за 2026 год '
                'и можно ли подтвердить рекомендацию производителя паспортом. Ничего не изменяй.')
    with episode(c, 'ORCH-B01-nc01-period-history-manufacturer') as outcome:
        view, turn = send(c, thread(c['client']), question)
        record(outcome, view, turn, question)
        answer = turn['answer'].casefold()
        assert re.search(r'\b5\b|пять', answer), turn['answer']
        assert re.search(r'год|годов|цикл', answer), turn['answer']
        assert not re.search(r'раз в (?:пять|5) лет|каждые (?:пять|5) лет|пятилет', answer), turn['answer']
        expected_source_dates = ['2026-11-16', '2027-01-28', '2027-04-11', '2027-06-23', '2027-09-04']
        expected_effective_dates = ['2026-11-16', '2027-01-28', '2027-04-12', '2027-06-23', '2027-09-06']
        assert all(mentions_date(answer, value) for value in set(expected_source_dates + expected_effective_dates)), turn['answer']
        # A zero inside "2026", a calendar calculation or an equipment lookup
        # cannot prove absence of actual work. Accept any complete authorized
        # historical source that really establishes the fixture's zero history.
        def verified_empty_history(proof):
            tool=proof.get('tool');arguments=proof.get('arguments') or {};value=proof.get('result')
            query=arguments.get('query') or {};view_args=arguments.get('view') or {}
            if view_args.get('offset',0)!=0 or view_args.get('path') not in (None,[],['items']):return False
            search=view_args.get('q')
            if (search not in (None,'') and not isinstance(search,dict)) or (isinstance(search,dict) and search.get('length')!=0):return False
            if isinstance(value,list):items=value;total=len(items)
            elif isinstance(value,dict):
                items=value.get('items');total=value.get('total',value.get('total_count'))
                if value.get('complete') is False or value.get('has_more') is True or value.get('truncated') is True or value.get('offset',0)!=0:return False
            else:return False
            if not isinstance(items,list) or type(total) is not int or total!=len(items):return False
            selected=(arguments.get('path') or {}).get('equipment_id')==pump['equipment_id']
            if tool=='equipment_service_history':
                return (selected and value.get('equipment_id')==pump['equipment_id']
                    and value.get('starts_on')=='2026-01-01' and value.get('ends_on')=='2026-12-31'
                    and value.get('only_accepted') is True and value.get('complete') is True
                    and value.get('undated_count')==0 and total==history_count==0)
            if tool=='equipment_executions':
                # Complete empty history across all years also proves zero in2026.
                return selected and total==history_count==0
            if tool not in ('canonical_tasks','tasks_find'):return False
            # A complete unfiltered all-status registry containing no task for
            # this equipment proves it has no actual work in any year. An
            # upcoming/active-only subset cannot establish this absence.
            if query.get('q') not in (None,'') and not (isinstance(query.get('q'),dict) and query['q'].get('length')==0):return False
            if query.get('status') is not None or query.get('state') is not None:return False
            if tool=='tasks_find':
                if value.get('period')!='all' or (value.get('filters') or {}).get('active_only') is not False:return False
            return all(isinstance(row,dict) and 'equipmentId' in row and row['equipmentId']!=pump['equipment_id'] for row in items)
        actual_history_evidence=[proof for proof in c['evidence'] if verified_empty_history(proof)]
        assert actual_history_evidence, 'Actual authorized history for NS-01/2026 was not checked completely'
        state=turn.get('workflow') or turn.get('task_state')
        if state:
            with c['engine'].connect() as db:
                saved_state=db.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'),dict(id=turn['turn_id']))
            proof_ids={proof['id'] for proof in saved_state.get('evidence',[]) if verified_empty_history(proof)}
            assert any(goal['status']=='completed' and proof_ids.intersection(goal.get('evidence_ids',[]))
                       and re.search(r'истори|фактическ|выполненн|завершенн|history|actual|performed',goal['title'].casefold())
                       for goal in state['goals']), 'The actual-history user objective remains unfinished'
            assert any(goal['status']=='blocked' and re.search(r'паспорт|производител|passport|manufacturer',goal['title'].casefold())
                       for goal in state['goals']), 'Missing manufacturer evidence must remain an explicit blocked objective'
            calendar_goals=[goal for goal in state['goals'] if goal.get('required_evidence')=='calendar_calculation' or goal.get('tool')=='calendar_evidence']
            assert calendar_goals and all(goal['status']=='completed' for goal in calendar_goals), 'Every supported calendar objective must be completed'
        else:
            # Legacy baseline has no goal state: require an explicit statement
            # about actual work in2026, not an unrelated number or calendar gap.
            statements=re.split(r'\n\s*\n|(?<=[.!?])\s+',answer.replace('ё','е'))
            assert any(re.search(r'\b2026\b',chunk) and re.search(r'истори|фактическ|выполненн|завершенн',chunk)
                       and re.search(r'\b0\b|не найден[а-я]*[^.]{0,60}(?:запис|работ|обслуж)|нет[^.]{0,60}(?:запис|работ|обслуж)|отсутств[^.]{0,60}(?:запис|работ|обслуж)',chunk)
                       for index in range(len(statements)) for chunk in [' '.join(statements[max(0,index-1):index+2])]), turn['answer']
        outcome['history_oracle']=dict(equipment_id=pump['equipment_id'],starts_on='2026-01-01',ends_on='2026-12-31',
                                       actual_history=history_count,authorized_sources=[proof['tool'] for proof in actual_history_evidence],
                                       user_goal_completed=bool(state),version=2)
        assert re.search(r'паспорт|производител', answer), turn['answer']
        assert re.search(r'не подтвержд|невозможно подтверд|не найден|нет (?:паспорт|документ)|недоступ', answer), turn['answer']
        assert not re.search(r'производитель рекомендует|паспорт подтверждает', answer), turn['answer']
        assert not view['actions'] and fingerprint(c['engine']) == before
        outcome['expected_data'] = dict(repetitions_per_active_cycle=5, years_between_active_cycles=1,
                                        source_dates=expected_source_dates, effective_dates=expected_effective_dates,
                                        actual_history=history_count, manufacturer_document_available=False)


def test_two_independent_changes_preserve_fields_and_confirm_individually(live_case):
    c = live_case
    second = add_equipment(c, 'RT-MOTOR', 'Original motor')
    first_id, second_id = c['equipment']['equipment_id'], second['equipment_id']
    desired = {first_id: 'Pump ALPHA checked', second_id: 'Motor BETA checked'}

    def state():
        with c['engine'].connect() as db:
            return {str(row['equipment_id']): dict(row) for row in db.execute(text(
                'SELECT * FROM equipment WHERE site_id=:site ORDER BY equipment_id'), dict(site=c['ids']['site'])).mappings()}

    before = state()
    question = ('Подготовь два независимых изменения без применения до моего подтверждения. '
                'Переименуй оборудование RT-PUMP в «Pump ALPHA checked». '
                'Переименуй оборудование RT-MOTOR в «Motor BETA checked». Остальные поля сохрани.')
    with episode(c, 'ORCH-C05-two-independent-proposals') as outcome:
        view, turn = send(c, thread(c['client']), question)
        record(outcome, view, turn, question)
        assert len(view['actions']) == 2, view
        assert state() == before, 'Preparing either action must not change equipment'
        actions = {str(a['arguments']['path']['equipment_id']): a for a in view['actions']}
        assert set(actions) == set(desired), actions
        for identity, name in desired.items():
            assert actions[identity]['arguments']['body']['name'] == name
        for identity, name in desired.items():
            prior = state()
            result = confirm(c['client'], actions[identity])
            assert result.status_code == 200 and result.json()['status'] == 'succeeded', result.text
            after = state()
            assert after[identity]['name'] == name and after[identity]['revision'] == prior[identity]['revision'] + 1
            for key in before[identity]:
                if key not in ('name', 'revision', 'updated_at'):
                    assert after[identity][key] == before[identity][key], key
            for other in set(before) - {identity}:
                assert after[other] == prior[other], 'Confirmation must apply only the selected card'
            replay = confirm(c['client'], actions[identity])
            assert replay.status_code == 200 and replay.json()['status'] == 'succeeded'
            assert state() == after, 'A replay must not dispatch the mutation again'
            outcome['steps'].append(dict(kind='confirmed-and-replayed', equipment_id=identity,
                                         expected_name=name, revision=after[identity]['revision']))
        assert all(state()[identity]['name'] == name for identity, name in desired.items())
        final_view=c['client'].get(B+'/conversations/'+view['conversation']['conversation_id']).json()
        final_turn=next(item for item in final_view['turns'] if item['turn_id']==turn['turn_id'])
        if final_turn.get('workflow'):
            assert final_turn['workflow']['outcome']=='completed', final_turn['workflow']
            assert all(goal['status']=='completed' for goal in final_turn['workflow']['goals']), final_turn['workflow']
        outcome['steps'].append(dict(kind='final-goal-state',goal_state=final_turn.get('workflow')))
        assert c['calls'], 'This case requires actual installed-model inference'


def test_failed_regulation_read_preserves_independent_card_and_explicit_partial(live_case, monkeypatch):
    from fastapi import HTTPException
    from app.assistant import read_transport, service
    c = live_case
    read_invoke = read_transport.invoke
    service_invoke = service.invoke
    failures = []

    def intercept(original):
        async def invoke(app, tool, arguments, headers):
            if tool.name == 'regulations_read':
                failures.append(tool.name)
                raise HTTPException(503, 'Synthetic temporary regulation backend failure')
            return await original(app, tool, arguments, headers)
        return invoke

    monkeypatch.setattr(read_transport, 'invoke', intercept(read_invoke))
    monkeypatch.setattr(service, 'invoke', intercept(service_invoke))
    before = fingerprint(c['engine'])
    question = ('Для RT-PUMP выполни два независимых пункта: покажи подтвержденную дату ввода из карточки '
                'и проверь полный регламент. Если один источник недоступен, покажи доступный результат '
                'и явно оставь второй пункт невыполненным. Ничего не изменяй.')
    with episode(c, 'ORCH-D05-independent-goal-after-backend-failure') as outcome:
        view, turn = send(c, thread(c['client']), question)
        record(outcome, view, turn, question)
        answer = turn['answer'].casefold()
        assert failures, 'Failure scenario must actually reach the failed backend operation'
        assert '2023' in answer and ('11-06' in answer or 'ноябр' in answer), turn['answer']
        assert re.search(r'не заверш|не выполн|недоступ|ошиб|не удалось|не провер', answer), turn['answer']
        assert not re.search(r'регламент (?:успешно )?проверен|все пункты выполнены', answer), turn['answer']
        if turn.get('workflow'):
            assert turn['workflow']['outcome'] not in ('completed', 'succeeded'), turn['workflow']
            assert any(goal['status'] not in ('completed', 'succeeded') for goal in turn['workflow']['goals']), turn['workflow']
        assert not view['actions'] and fingerprint(c['engine']) == before
        outcome['injected_failures'] = len(failures)
