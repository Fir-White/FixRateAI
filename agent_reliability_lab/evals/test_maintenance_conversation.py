"""Short maintenance conversations graded against authoritative SQL rows."""
from datetime import datetime, time, timedelta
import json
import os
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import text

from agent_reliability_lab.evals.test_agent_v3_e2e import ZONE, lab
from tests.backend.test_assistant import assistant_case, confirm
from tests.backend.test_assistant_architecture_v2 import add_order, stored, turn
from tests.backend.test_assistant_dependent_analytics import checksums
from tests.backend.test_management import config, join, managed
from tests.backend.test_runtime_integration import runtime


pytestmark = pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires local Ollama profile')


def schedule(lab):
    fixture, now, _, actor, ledger, _, _ = lab
    engine, _, _, _, ids = fixture
    asset = {'equipment_id': ledger['equipment']['КА-21']['id']}
    day = now.astimezone(ZONE).date()
    start = datetime.combine(day + timedelta(days=1), time(10), ZONE)
    skill = uuid4()
    low, _ = join(fixture)
    high, _ = join(fixture)
    unqualified, _ = join(fixture)
    off_shift, _ = join(fixture)
    upcoming = add_order(fixture, [asset], 'Контроль уставок шкафа', 'draft', start + timedelta(hours=4), start)
    overdue = add_order(fixture, [asset], 'Просроченный контроль шкафа', 'assigned', start - timedelta(days=3),
                        start - timedelta(days=4))
    later = add_order(fixture, [asset], 'Поздний осмотр шкафа', 'draft', start + timedelta(days=2),
                      start + timedelta(days=1))
    busy = add_order(fixture, [asset], 'Резерв смены', 'assigned', start + timedelta(hours=7), start + timedelta(hours=5))
    workers = ((low, 'Алексей Допущенный'), (high, 'Иван Занятый'), (unqualified, 'Олег Без Допуска'),
               (off_shift, 'Сергей Вне Смены'))
    with engine.begin() as db:
        rule = db.scalar(text('SELECT maintenance_rule_id FROM rule_equipment WHERE equipment_id=:equipment_id'), asset)
        origin = db.scalar(text("SELECT properties->>'data_origin' FROM equipment WHERE equipment_id=:equipment_id"), asset)
        db.execute(text('INSERT INTO skills(skill_id,code,name,validity_required) VALUES (:skill,:code,:name,true)'),
                   dict(skill=skill, code=str(skill), name='Допуск к контролю уставок'))
        db.execute(text('INSERT INTO rule_required_skills(site_id,maintenance_rule_id,skill_id) VALUES (:site,:rule,:skill)'),
                   dict(ids, rule=rule, skill=skill))
        for task in (upcoming, overdue, later):
            snapshot = dict(data_origin=origin, earliest_date=day.isoformat(), planning_duration_minutes=60,
                            duration_basis='approved fixture', qualification_ids=[str(skill)])
            db.execute(text('''UPDATE work_orders SET maintenance_rule_id=:rule,
                planned_end_at=planned_start_at+interval '1 hour', operation_snapshot=operation_snapshot||CAST(:snapshot AS jsonb)
                WHERE work_order_id=:task'''), dict(task=task, rule=rule, snapshot=json.dumps(snapshot)))
        db.execute(text('UPDATE maintenance_rules SET required_people=1 WHERE maintenance_rule_id=:rule'), dict(rule=rule))
        for worker, name in workers:
            db.execute(text('UPDATE users SET full_name=:name WHERE user_id=:worker'), dict(worker=worker, name=name))
            if worker != unqualified:
                db.execute(text('''INSERT INTO user_skills(site_id,user_id,skill_id,verified_at,valid_until)
                    VALUES (:site,:worker,:skill,:now,:until)'''),
                    dict(ids, worker=worker, skill=skill, now=now-timedelta(days=2), until=day+timedelta(days=30)))
            shift = start + timedelta(hours=3) if worker == off_shift else start - timedelta(hours=1)
            db.execute(text('''INSERT INTO availability_slots(site_id,user_id,starts_at,ends_at)
                VALUES (:site,:worker,:start,:end)'''), dict(ids, worker=worker, start=shift, end=start+timedelta(hours=6)))
        db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by,start_at,end_at)
            VALUES (:site,:task,:worker,:chief,:start,:end)'''),
            dict(ids, task=busy, worker=high, start=start+timedelta(hours=5), end=start+timedelta(hours=6)))
        db.execute(text('''INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by)
            VALUES (:site,:task,:worker,:chief)'''), dict(ids, task=overdue, worker=actor))
    return upcoming, overdue, later, low


def ask(fixture, client, question, chat=None):
    result, actions, chat = turn(client, question, chat=chat)
    assert result['status'] == 'completed' and result['execution_engine'] == 'v3', result
    assert not actions
    state = stored(fixture, result['turn_id'])
    assert state['read_only'] is True
    tools = [row['tool'] for row in result['trace'] if not row['tool'].startswith('__')]
    return result['answer'], tools, state, chat


def test_natural_maintenance_thread_reads_catalog_orders_and_workers(lab):
    fixture, _, _, actor, _, _, clients = lab
    engine, _, _, _, ids = fixture
    upcoming, overdue, later, low = schedule(lab)
    with engine.connect() as db:
        titles = db.scalars(text('''SELECT o.title FROM operation_templates o JOIN maintenance_rules r USING (operation_template_id)
            WHERE r.site_id=:site AND o.code LIKE 'RELIABILITY-%' ORDER BY o.code'''), ids).all()
        assignee = db.scalar(text('SELECT full_name FROM users WHERE user_id=:actor'), dict(actor=actor))
        chosen = db.scalar(text('SELECT full_name FROM users WHERE user_id=:actor'), dict(actor=low))
    before = checksums(fixture)
    chief = clients['chief_engineer']
    answer, tools, _, chat = ask(fixture, chief, 'Какие виды ТО есть на объекте?')
    assert 'ТО2' in answer and tools == ['maintenance_catalog_read']
    answer, tools, state, _ = ask(fixture, chief, 'А конкретнее, все по пунктам', chat)
    assert len(titles) == 3 and all(title in answer for title in titles)
    assert tools == ['maintenance_catalog_read'] and state['outcome'] == 'completed', state
    answer, tools, state, _ = ask(fixture, chief, 'Выбери подходящего на ближайшее ТО', chat)
    assert upcoming in answer and chosen in answer and later not in answer, answer
    assert tools == ['tasks_find', 'assignment_context', 'assignment_preview']
    assert state['outcome'] == 'completed' and state['maintenance_dialogue']['worker_ids'] == [str(low)]
    assert all(name not in answer for name in ('Иван Занятый', 'Олег Без Допуска', 'Сергей Вне Смены'))
    answer, tools, _, _ = ask(fixture, chief, 'Долбаёб?', chat)
    assert upcoming in answer and chosen in answer and 'assignment_preview' in tools
    assert 'вежлив' not in answer.casefold()

    _, _, _, chat = ask(fixture, chief, 'Какие ТО у нас есть?')
    answer, tools, _, _ = ask(fixture, chief, 'А какие просрочены?', chat)
    assert overdue in answer and upcoming not in answer and tools == ['tasks_find']
    answer, tools, _, _ = ask(fixture, chief, 'Кто их выполняет?', chat)
    assert overdue in answer and assignee in answer and upcoming not in answer and tools == ['tasks_find']
    answer, tools, _, _ = ask(fixture, chief, 'Кого лучше отправить завтра?', chat)
    assert upcoming in answer and chosen in answer and 'assignment_preview' in tools
    answer, tools, _, _ = ask(fixture, chief, 'Почему именно его?', chat)
    assert upcoming in answer and chosen in answer and 'загрузку' in answer
    assert tools == ['task_read', 'assignment_context', 'assignment_preview']
    assert checksums(fixture) == before


def test_executor_cannot_see_other_operations_or_recommend_their_workers(lab):
    fixture, _, _, _, ledger, _, clients = lab
    engine = fixture[0]
    upcoming, overdue, _, _ = schedule(lab)
    restricted = ledger['equipment']['КА-210']['id']
    with engine.connect() as db:
        title = db.scalar(text('''SELECT o.title FROM rule_equipment e JOIN maintenance_rules r USING (maintenance_rule_id)
            JOIN operation_templates o USING (operation_template_id) WHERE e.equipment_id=:id'''), dict(id=restricted))
    executor = clients['executor']
    answer, tools, _, chat = ask(fixture, executor, 'Какие виды ТО есть на объекте?')
    answer, tools, _, _ = ask(fixture, executor, 'Покажи все', chat)
    assert title not in answer and 'Порядок обслуживания секции 2' in answer and tools == ['maintenance_catalog_read']
    answer, _, _, _ = ask(fixture, executor, 'А какие просрочены?', chat)
    assert overdue in answer and upcoming not in answer
    answer, tools, state, _ = ask(fixture, executor, 'Выбери подходящего на ближайшее ТО', chat)
    assert upcoming not in answer and 'Алексей Допущенный' not in answer
    assert tools == ['tasks_find'] and state['outcome'] == 'blocked'
    response = executor.get(f'/api/v1/maintenance/ui/tasks/{upcoming}/assignment-context')
    assert response.status_code == 403


def test_catalog_failure_cannot_be_filled_with_invented_types(lab, monkeypatch):
    from app.assistant import maintenance_dialogue

    fixture, _, _, _, _, _, clients = lab
    real = maintenance_dialogue.invoke

    async def unavailable(app, tool, args, headers):
        if tool.name == 'maintenance_catalog_read':
            raise HTTPException(503, 'Unavailable test source')
        return await real(app, tool, args, headers)

    monkeypatch.setattr(maintenance_dialogue, 'invoke', unavailable)
    chief = clients['chief_engineer']
    answer, tools, state, chat = ask(fixture, chief, 'Какие ТО у нас есть?')
    assert tools == ['maintenance_catalog_read'] and state['outcome'] == 'blocked'
    assert 'Не удалось' in answer and 'ТО2' not in answer
    answer, tools, state, _ = ask(fixture, chief, 'А конкретнее, все по пунктам', chat)
    assert tools == ['maintenance_catalog_read'] and state['evidence'][0]['status'] == 'UNAVAILABLE'
    assert 'Не удалось' in answer and 'ТО2' not in answer


@pytest.mark.parametrize('question', [
    'Составь перечень регламентных работ, которые действительно предусмотрены на объекте.',
    'Что по техобслуживанию уже лежит в реестре нашего объекта?',
])
def test_model_routes_unseen_catalog_wording_to_object_evidence(lab, question):
    fixture, _, _, _, _, _, clients = lab
    answer, tools, state, _ = ask(fixture, clients['chief_engineer'], question)
    assert tools == ['maintenance_catalog_read'] and state['outcome'] == 'completed', answer
    assert state['metrics']['llm_calls'] >= 1 and state['metrics']['llm_requests'] >= 1
    assert all(f'Порядок обслуживания секции {index}' in answer for index in range(1, 4))


def test_reported_dialogue_resolves_type_backlog_and_exact_days(lab):
    fixture, now, _, _, ledger, _, clients = lab
    engine, _, _, _, ids = fixture
    upcoming, _, _, worker = schedule(lab)
    chief = clients['chief_engineer']
    equipment = ledger['equipment']['КА-21']['id']
    day = now.astimezone(ZONE).date()
    titles = ('Осмотр экрана защиты', 'Проверка контура диагностики', 'Протокол показаний защиты')
    for index, name in enumerate(titles, 1):
        response = chief.post(f'/api/v1/maintenance/equipment/{equipment}/service-configurations', json=config(
            day + timedelta(days=2), code=f'TYPE1-{index}', title=name, maintenance_type='ТО1',
            valid_from=(day-timedelta(days=45)).isoformat()))
        assert response.status_code == 201, response.text
    with engine.connect() as db:
        keys = db.execute(text('''SELECT o.work_order_id::text AS id,
            (COALESCE(o.planned_start_at,o.regulatory_deadline_at) AT TIME ZONE 'Asia/Yekaterinburg')::date::text AS day
            FROM work_orders o WHERE site_id=:site AND maintenance_rule_id IS NOT NULL
            AND status NOT IN ('completed','cancelled') ORDER BY work_order_id'''), ids).mappings().all()

    first, _, _, chat = ask(fixture, chief, 'Какие виды то есть?')
    assert 'ТО1' in first and 'ТО2' in first
    for prompt in ('А что за то 1?', 'Да, нужны детали. Все 3 вот их перечисли',
                   'Я имел в виду перечисли все 3 вида то1', 'хорошо, именно 3 операции ТО-1\\', 'Стоп, что?? как так?'):
        answer, tools, state, _ = ask(fixture, chief, prompt, chat)
        assert tools == ['maintenance_catalog_read'], (prompt, answer)
        assert state['maintenance_dialogue']['type_keys'] == ['то1']
        assert all(title in answer for title in titles) and 'Порядок обслуживания секции' not in answer, (prompt, answer)

    answer, tools, state, _ = ask(fixture, chief, 'Сколько невыполненных то есть на данный момент?', chat)
    assert tools == ['tasks_find'] and f'**{len(keys)}**' in answer and 'реестр нарядов' in answer
    assert state['evidence'][-1]['result']['filters']['maintenance_only'] is True
    answer, tools, state, _ = ask(fixture, chief, 'Напиши какие за 22 число, за 23 и за 24 ноября 2026', chat)
    days = {'2026-11-22', '2026-11-23', '2026-11-24'}
    assert tools == ['tasks_find'] and set(state['maintenance_dialogue']['days']) == days
    for day in days:
        ids = [row['id'] for row in keys if row['day'] == day]
        assert f'**{day}** · {len(ids)}' in answer
        assert all(identity in answer for identity in ids)

    _, _, state, chat = ask(fixture, chief, 'Какие виды ТО?')
    types = state['evidence'][-1]['result']['types']
    assert [item['type_name'] for item in types] == ['ТО1', 'ТО2']
    for prompt in ('А какие операции у первого?', 'Перечисли все'):
        answer, tools, state, _ = ask(fixture, chief, prompt, chat)
        assert tools == ['maintenance_catalog_read']
        assert state['evidence'][-1]['result']['type_codes'] == [types[0]['type_code']]
        assert all(title in answer for title in titles) and 'Порядок обслуживания секции' not in answer
    answer, tools, state, _ = ask(fixture, chief, 'А операции второго вида ТО?', chat)
    assert tools == ['maintenance_catalog_read'] and 'Порядок обслуживания секции' in answer
    assert state['evidence'][-1]['result']['type_codes'] == [types[1]['type_code']]
    answer, tools, state, _ = ask(fixture, chief, 'А кто может их выполнить?', chat)
    assert tools == ['tasks_find', 'assignment_context', 'assignment_preview']
    assert state['evidence'][0]['result']['filters']['type_codes'] == [types[1]['type_code']]
    assert state['maintenance_dialogue']['worker_ids'] == [str(worker)] and upcoming in answer
    assert state['outcome'] == 'partial' and 'Подбор относится к этому наряду' in answer

    _, _, _, chat = ask(fixture, chief, 'Какие виды ТО?')
    answer, tools, state, _ = ask(fixture, chief, 'А какие операции у третьего?', chat)
    assert not tools and state['outcome'] == 'blocked' and 'в предыдущем списке' in answer


def test_assignment_typo_and_short_continuations_keep_one_confirmation(lab):
    fixture, _, _, _, _, _, clients = lab
    engine, _, _, _, ids = fixture
    upcoming, _, later, worker = schedule(lab)
    chief = clients['chief_engineer']
    query = text('SELECT status,revision FROM work_orders WHERE work_order_id=:target')
    active = text("SELECT user_id FROM work_assignments WHERE work_order_id=:target AND status='assigned'")
    with engine.connect() as db:
        before = db.execute(query, dict(target=upcoming)).one()
    prompt = 'назанчь свободного сотрудника на ближайшее свободное то'
    first, actions, chat = turn(chief, prompt)
    assert first['status'] == 'completed' and first['workflow']['outcome'] == 'awaiting_confirmation', first
    action, = actions
    assert action['tool_name'] == 'task_assign' and action['arguments']['path']['task_id'] == upcoming
    assert action['arguments']['body']['executor_ids'] == [str(worker)] and later not in first['answer']
    for prompt in ('дак проверь ема', 'Делай'):
        reply, actions, _ = turn(chief, prompt, chat=chat)
        assert reply['workflow']['outcome'] == 'awaiting_confirmation' and 'карточка' in reply['answer'].lower()
        assert [item['action_id'] for item in actions] == [action['action_id']]
    with engine.connect() as db:
        assert db.execute(query, dict(target=upcoming)).one() == before
        assert db.execute(active, dict(target=upcoming)).all() == []
    executor = clients['executor']
    denied, other_actions, _ = turn(executor, 'Назначь свободного сотрудника на ближайшее ТО')
    assert denied['workflow']['outcome'] == 'blocked' and not other_actions
    denied_confirmation = confirm(executor, action)
    assert denied_confirmation.status_code in (403, 404), denied_confirmation.text
    for _ in range(2):
        result = confirm(chief, action)
        assert result.status_code == 200 and result.json()['status'] == 'succeeded', result.text
        assert result.json()['result']['verification']['status'] == 'confirmed'
    with engine.connect() as db:
        assert db.execute(query, dict(target=upcoming)).one() == ('assigned', before.revision + 1)
        assert [str(identity) for identity in db.scalars(active, dict(target=upcoming))] == [worker]
        audit = db.scalar(text("SELECT count(*) FROM audit_events WHERE site_id=:site AND entity_id=:target AND action='assign'"),
                          dict(ids, target=upcoming))
        assert audit == 1
    after, actions, _ = turn(chief, 'Делай', chat=chat)
    assert 'выполнено' in after['answer'] and after['workflow']['outcome'] == 'completed', after
    assert [item['action_id'] for item in actions] == [action['action_id']]
    with engine.connect() as db:
        assert db.execute(query, dict(target=upcoming)).one() == ('assigned', before.revision + 1)
