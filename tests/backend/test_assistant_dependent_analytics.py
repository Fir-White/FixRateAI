"""Independent PostgreSQL oracles for data-selected inputs through the assistant API."""
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import text

from app.assistant.analysis_contract import AnalysisRequest
from app.assistant.dialogue_routing import DialogueRoute
from app.assistant.semantic_plan import AnalyticalResult, AnalyticalRequestedResults, AnalyticalCoverageReview
from tests.backend.test_assistant import B, assistant_case
from tests.backend.test_assistant_architecture_v2 import add_order, inventory, stored, turn
from tests.backend.test_assistant_equipment_history import add_report
from tests.backend.test_management import config, join, managed
from tests.backend.test_runtime_integration import runtime


AGGREGATE = B + '/workspace/work-order-analytics'
OPEN = ('draft', 'assigned', 'clarification', 'rework', 'in_progress', 'in_review')


class Provider:
    supports_dialogue_routing = True
    supports_semantic_plan = True
    supports_request_coverage = True

    def __init__(self, question, **analysis):
        self.result = AnalyticalRequestedResults(
            results=[AnalyticalResult(intent='aggregate_work', source_text=question)],
            analysis=AnalysisRequest(source_text=question, **analysis),
        )

    def chat(self, messages, schema, budget):
        if schema is DialogueRoute:
            return DialogueRoute(kind='data_query', explain=True)
        if schema is AnalyticalRequestedResults:
            return self.result
        if schema is AnalyticalCoverageReview:
            return AnalyticalCoverageReview(missing=[])
        pytest.fail(f'Unexpected provider call {schema}')


def checksums(case):
    tables = ('equipment', 'work_orders', 'work_order_equipment', 'work_assignments',
              'schedule_entries', 'maintenance_rules', 'rule_equipment', 'acceptance_reviews',
              'work_reports', 'audit_events', 'assistant_actions', 'planning_draft_versions',
              'evidence_files','checklist_results','work_readings','ai_quality_checks')
    with case[0].connect() as db:
        return {table: db.scalar(text(f'SELECT md5(string_agg(q::text, chr(10) ORDER BY q::text)) '
                                      f'FROM {table} q WHERE site_id=:site'), case[-1])
                for table in tables if table != 'assistant_actions'} | {
                    'assistant_actions': db.scalar(text(
                        'SELECT count(*) FROM assistant_actions a JOIN assistant_conversations c USING(conversation_id) '
                        'WHERE c.site_id=:site'), case[-1])}


@pytest.mark.parametrize('variant', ['tie', 'different-ids'])
def test_rank_and_fanout_from_all_tasks(assistant_case, variant):
    case = assistant_case
    engine, app, admin, _, ids = case
    local_today = date.today()
    with engine.begin() as db:
        db.execute(text("UPDATE sites SET timezone='Asia/Yekaterinburg' WHERE site_id=:site"), ids)
    marker = variant + '-' + uuid4().hex[:6]
    a = inventory(admin, ids, 'A-'+marker, name='Заслонка '+marker)
    b = inventory(admin, ids, 'B-'+marker, name='Конденсатор '+marker)
    c = inventory(admin, ids, 'C-'+marker, name='Байпас '+marker)
    now = datetime.now(timezone.utc)
    older = now - timedelta(days=9)
    newer = now - timedelta(days=4)
    linked = add_order(case, [a, b], 'Общая проверка', 'in_progress', newer, None)
    for ix in range(29):
        add_order(case, [a], f'Модуль {ix}', 'assigned', older, None)
        add_order(case, [b], f'Проверка {ix}', 'in_review', newer, None)
    for _ in range(34):
        add_order(case, [c], 'Срок в будущем', 'assigned', now+timedelta(days=3), older)
    add_order(case, [c], 'Уже исполнено', 'completed', older, older)
    add_order(case, [b], 'Дополнительный наряд', 'assigned', now+timedelta(days=1), None)
    _, accepted = add_report(case, a, actual=older.isoformat(), submitted=older+timedelta(hours=1))
    _, unaccepted = add_report(case, a, actual=newer.isoformat(), submitted=newer+timedelta(hours=1), acceptance=None)
    with engine.begin() as db:
        db.execute(text('UPDATE acceptance_reviews SET reviewed_at=:reviewed WHERE work_report_id=:report'),
                   dict(reviewed=older+timedelta(hours=2), report=accepted))
    obligation = local_today + timedelta(days=10)
    rule = admin.chief.post(f'/api/v1/maintenance/equipment/{a["equipment_id"]}/service-configurations',
                           json=config(obligation, title='Испытание заслонки', valid_from='2025-01-01'))
    assert rule.status_code==201, rule.text
    question = 'Сравни две установки, у которых больше всего просроченных работ. Проверь названия работ, историю ТО, регламенты и календарь.'
    app.state.assistant_provider_factory = lambda: Provider(question, group_by='equipment', metric='overdue', limit=2,
        projections=['equipment_details','overdue_tasks','latest_maintenance','active_regulations','maintenance_calendar'],
        history_months=12, compare=True, recommendations=3)
    before = checksums(case)
    response, actions, _ = turn(admin, question)
    assert actions==[]
    result = stored(case, response['turn_id'])
    assert result['outcome']=='completed', (response['answer'], result['goals'])
    receipts = [proof for proof in result['evidence'] if proof.get('output_type')=='aggregate']
    ranking = receipts[0]['result']
    with engine.connect() as db:
        expected = db.execute(text("""
            SELECT e.equipment_id::text, count(*) FILTER (WHERE w.regulatory_deadline_at < :cutoff)
            FROM equipment e JOIN work_order_equipment j USING (site_id,equipment_id)
            JOIN work_orders w USING (site_id,work_order_id)
            WHERE e.site_id=:site AND w.status=ANY(:states)
            GROUP BY e.equipment_id HAVING min(w.regulatory_deadline_at) < :cutoff
            ORDER BY 2 DESC,min(w.regulatory_deadline_at),e.equipment_id
        """), dict(site=ids['site'], states=list(OPEN), cutoff=datetime.fromisoformat(ranking['cutoff']))).all()
    assert [(row['id'],row['overdue']) for row in ranking['groups']]==expected
    assert [row[0] for row in expected]==[a['equipment_id'], b['equipment_id']]
    assert all(any(row['task_id']==linked for row in proof['result']['items'])
               for proof in result['evidence'] if proof.get('output_type')=='overdue_tasks')
    for goal in result['goals'][1:]:
        assert goal['depends_on']==['analysis-selection']
        assert [link['entity_id'] for link in goal['bindings']]==[row[0] for row in expected]
        assert {link['from_evidence'] for link in goal['bindings']}=={receipts[0]['id']}
    answer = response['answer']
    for fact in (accepted, rule.json()['binding_id'], obligation.isoformat(),
                 'принятых отчётов в периоде нет', 'действующих регламентов нет', 'показано 30 из 30'):
        assert fact in answer, answer
    assert unaccepted not in answer and c['equipment_id'] not in answer
    assert checksums(case)==before


def test_unavailable_source_keeps_rank_and_other_asset(assistant_case, monkeypatch):
    case = assistant_case
    _, app, admin, _, ids = case
    a, b = [inventory(admin, ids, f'Ф-{i}-{uuid4().hex[:6]}') for i in range(2)]
    past = datetime.now(timezone.utc)-timedelta(days=2)
    add_order(case, [a,b], 'Замер сопротивления', 'in_progress', past, None)
    question = 'Отбери две установки с наибольшим числом просрочек и проверь регламенты и фактическое ТО.'
    app.state.assistant_provider_factory = lambda: Provider(question, group_by='equipment', metric='overdue',
        limit=2, projections=['active_regulations','latest_maintenance'])
    from app.assistant import read_transport
    real = read_transport.invoke

    async def with_failure(app, tool, args, headers):
        if tool.name=='regulations_read' and args['path']['equipment_id']==b['equipment_id']:
            raise HTTPException(503, 'Fixture unavailable')
        return await real(app, tool, args, headers)

    monkeypatch.setattr(read_transport, 'invoke', with_failure)
    before = checksums(case)
    response, actions, _ = turn(admin, question)
    result = stored(case, response['turn_id'])
    assert actions==[] and checksums(case)==before
    assert result['outcome']=='partial', response['answer']
    projected = next(goal for goal in result['goals'] if goal['id']=='analysis-active_regulations')
    assert {link['entity_id']:link['status'] for link in projected['bindings']}=={
        a['equipment_id']:'EMPTY', b['equipment_id']:'UNAVAILABLE'}
    assert 'HTTP 503' in response['answer'] and 'действующих регламентов нет' in response['answer']


def test_assignees_equipment_and_periods_share_aggregate_contract(assistant_case):
    case = assistant_case
    engine, app, admin, login, ids = case
    a = inventory(admin, ids, 'RANK-'+ids['marker'])
    employees = [join(case) for _ in range(3)]
    day = date.today()
    current = datetime.combine(day, datetime.min.time(), timezone.utc)
    tasks = [add_order(case, [a], f'Заказ {i}', 'assigned', current+timedelta(days=2), current)
             for i in range(4)]
    add_order(case, [a], 'Другая неделя', 'completed', current-timedelta(days=2), current-timedelta(days=7))
    with engine.begin() as db:
        for index, (identity, _) in enumerate(employees, 1):
            for task_id in tasks[:index]:
                db.execute(text('INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by) '
                                'VALUES (:site,:task,:employee,:user)'),
                           dict(ids, task=task_id, employee=identity))
    request = 'Назови трёх исполнителей с наибольшей очередью незавершённых работ и выведи их назначения.'
    app.state.assistant_provider_factory = lambda: Provider(request, group_by='assignee', metric='unfinished',
                                                            limit=3, projections=['staff_assignments'])
    answer, actions, _ = turn(admin, request)
    assert actions==[]
    assert [answer['answer'].index(identity) for identity, _ in employees[::-1]]==sorted(
            answer['answer'].index(identity) for identity, _ in employees[::-1])
    result = stored(case, answer['turn_id'])
    assignment_proofs = {proof['entity']['user_id']:proof['result']['items'] for proof in result['evidence']
                         if proof['goal_id']=='analysis-staff_assignments'}
    assert {user:{p['task_id'] for p in assignment_proofs[user]} for user,_ in employees} == {
        user:set(tasks[:index]) for index,(user,_) in enumerate(employees,1)}
    with closing(login(employees[0][1])) as executor:
        assert executor.get(AGGREGATE, params=dict(group_by='assignee', metric='unfinished')).status_code==403
        own = executor.get(AGGREGATE, params=dict(group_by='equipment', metric='unfinished')).json()
        assert [(row['id'],row['unfinished']) for row in own['groups']]==[(a['equipment_id'],1)]
    request = 'Покажи оборудование с наибольшим количеством незавершённых работ.'
    app.state.assistant_provider_factory = lambda: Provider(request, group_by='equipment', metric='unfinished', limit=1)
    answer, _, _ = turn(admin, request)
    assert a['equipment_id'] in answer['answer'] and 'Незавершённых 4' in answer['answer']
    earlier = day-timedelta(days=7)
    request = f'Сравни количество запланированных работ {earlier} и {day}.'
    app.state.assistant_provider_factory = lambda: Provider(request, group_by='period', metric='planned',
        windows=[dict(starts_on=earlier,ends_on=earlier),
                 dict(starts_on=day+timedelta(days=1),ends_on=day+timedelta(days=1))])
    answer, actions, _ = turn(admin, request)
    result = stored(case, answer['turn_id'])
    assert result['outcome']=='completed' and actions==[], answer['answer']
    assert 'запланировано 1' in answer['answer'] and 'запланировано 4' in answer['answer']
    assert '+3' in answer['answer']


def test_another_building_and_incomplete_large_details(assistant_case):
    case = assistant_case
    engine, app, admin, _, ids = case
    a = inventory(admin, ids, 'F-'+ids['marker'])
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=2)
    other = dict(ids, site=uuid4(), system=uuid4())
    with engine.begin() as db:
        db.execute(text("INSERT INTO sites(site_id,name,timezone) VALUES (:site,'Отдельное здание','Asia/Tokyo')"), other)
        db.execute(text("INSERT INTO engineering_systems(system_id,site_id,code,name) "
                        "VALUES (:system,:site,'F','Система второго здания')"), other)
        foreign_id = db.scalar(text("INSERT INTO equipment(equipment_id,site_id,system_id,equipment_type_id,asset_code,name) "
            "VALUES (:asset,:site,:system,:type,:code,'Недоступная установка') RETURNING equipment_id"),
            dict(other, asset=uuid4(), code=a['asset_code']))
    foreign_case = (*case[:-1], other)
    try:
        add_order(foreign_case, [{'equipment_id':foreign_id}], 'Не должно быть в ответе', 'assigned', past, past)
        for ix in range(105):
            add_order(case, [a], f'Задача с длинным реестром {ix}', 'assigned', past, past)
        question = 'Какая установка с наибольшим количеством просроченных работ? Перечисли названия и сроки.'
        app.state.assistant_provider_factory = lambda: Provider(question, group_by='equipment', metric='overdue',
            limit=1, projections=['overdue_tasks'])
        before = checksums(case)
        answer, actions, _ = turn(admin, question)
        result = stored(case, answer['turn_id'])
        assert result['outcome']=='partial' and actions==[] and checksums(case)==before
        assert 'просроченных 105' in answer['answer'] and 'показано 100 из 105' in answer['answer']
        assert str(foreign_id) not in answer['answer'] and 'Не должно быть в ответе' not in answer['answer']
    finally:
        with engine.begin() as db:
            for table in ('work_order_equipment', 'work_orders', 'equipment', 'engineering_systems', 'sites'):
                db.execute(text(f'DELETE FROM {table} WHERE site_id=:site'), other)
