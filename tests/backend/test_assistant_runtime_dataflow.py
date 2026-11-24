"""Task-card chains and negative facts over new PostgreSQL fixtures."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import text

from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_architecture_v2 import add_order, inventory, stored, turn
from tests.backend.test_assistant_dependent_analytics import Provider, checksums
from tests.backend.test_assistant_equipment_history import add_report
from tests.backend.test_management import join, managed
from tests.backend.test_runtime_integration import runtime


EARLIEST = 'Выбери просроченный наряд с самым ранним сроком и проверь его отчёт и готовность к приёмке.'
GAPS = 'Найди задание с недостающими материалами. Перечисли препятствия приёмке.'


def provider(case, prompt, metric):
    case[1].state.assistant_provider_factory = lambda: Provider(prompt, group_by='task', metric=metric,
        limit=1, projections=['task_materials'])


def set_material(case, task, asset):
    from PIL import Image
    engine, app, _, _, ids = case
    started = datetime.now(timezone.utc) - timedelta(days=7)
    _, report = add_report(case, None, task=task, actual=started.isoformat(),
                           submitted=started+timedelta(hours=2), acceptance=None)
    checklist = [dict(id=str(uuid4()),text='Измерение вибрации',answerKind='boolean',required=True,photoRequired=True)]
    photo = str(uuid4())
    storage_key = f'runtime-dataflow/{photo}.png'
    local = app.state.settings.photo_storage_root / storage_key
    local.parent.mkdir(parents=True,exist_ok=True)
    Image.new('RGB',(20,20),'blue').save(local)
    content = local.read_bytes()
    with engine.begin() as db:
        db.execute(text("UPDATE work_reports SET checklist_snapshot=CAST(:items AS jsonb) WHERE work_report_id=:id"),
                   dict(items=json.dumps(checklist), id=report))
        db.execute(text("""UPDATE work_orders SET status='in_review',operation_snapshot=operation_snapshot||
            '{"required_acts":["Паспорт контроля"],"methodology_ref":"Процедура 91"}'::jsonb WHERE work_order_id=:task"""),
                   dict(task=task))
        db.execute(text("""INSERT INTO evidence_files (evidence_file_id,site_id,work_order_id,work_report_id,
            uploaded_by,stage,storage_key,mime_type,file_size,sha256,checklist_item_id,view_key,equipment_id)
            VALUES (:photo,:site,:task,:report,:user,'before',:storage_key,'image/png',:size,:digest,
                    :checklist,'Корпус',:asset)"""),
                   dict(ids,photo=photo,task=task,report=report,storage_key=storage_key,size=len(content),
                        digest=sha256(content).hexdigest(),checklist=checklist[0]['id'],asset=asset['equipment_id']))
    return report,photo


@pytest.mark.parametrize('metric', ['earliest_overdue','missing_materials'])
def test_execute_three_typed_nodes_against_same_report(assistant_case, metric):
    case = assistant_case
    engine, _, admin, _, ids = case
    asset = inventory(admin, ids, 'CASE-'+ids['marker'])
    oldest = datetime.now(timezone.utc)-timedelta(days=8)
    tied = [add_order(case,[asset],f'Калибровка канала {ix}','assigned',oldest,None) for ix in range(2)]
    winner = min(tied)
    report,photo = set_material(case,winner,asset)
    for index in range(30):
        add_order(case,[asset],f'Контроль цепи {index}','assigned',oldest+timedelta(minutes=10+index),None)
    add_order(case,[asset],'Завершённая запись','completed',oldest-timedelta(days=1),None)
    prompt = EARLIEST if metric=='earliest_overdue' else GAPS
    provider(case,prompt,metric)
    with engine.connect() as db:
        ordered = db.execute(text("""SELECT work_order_id::text FROM work_orders WHERE site_id=:site
          AND status IN ('assigned','in_review') ORDER BY regulatory_deadline_at,work_order_id"""), ids).scalars().all()
    before = checksums(case)
    answer, actions, _ = turn(admin,prompt)
    state = stored(case,answer['turn_id'])
    assert state['outcome']=='completed', (answer['answer'],state['goals'])
    assert ordered[0]==winner and actions==[] and checksums(case)==before
    root, card, materials = state['goals']
    assert card['depends_on']==[root['id']] and materials['depends_on']==[card['id']]
    assert card['bindings'][0]['entity_id']==winner
    assert materials['bindings'][0]['from_evidence']==card['bindings'][0]['evidence_id']
    evidence = next(p for p in state['evidence'] if p['id']==materials['bindings'][0]['evidence_id'])
    assert evidence['arguments']['query']['execution_id']==report
    assert next(p['result'] for p in state['evidence'] if p.get('output_type')=='aggregate')['eligible_groups']==32
    for fact in (winner, report, photo, 'одинаковый нормативный срок', 'Измерение вибрации', 'фото до и после',
                 'Фактическое начало', 'Фактические трудозатраты', 'Паспорт контроля', 'разрешение главного инженера'):
        assert fact.casefold() in answer['answer'].casefold()
    assert 'Фактическое окончание' not in evidence['result']['missing_materials']


@pytest.mark.parametrize('error', ['no-id','denied','unavailable'])
def test_bad_source_or_dependency_preserves_only_verified_facts(assistant_case, monkeypatch, error):
    from app.assistant import read_transport
    case = assistant_case
    _, _, admin, _, ids = case
    asset = inventory(admin, ids, 'BAD-'+ids['marker'])
    task = add_order(case,[asset],'Обход резервной линии','assigned',
                     datetime.now(timezone.utc)-timedelta(days=2),None)
    provider(case,EARLIEST,'earliest_overdue')
    real = read_transport.invoke
    invoked = []

    async def transport(app, tool, args, headers):
        invoked.append(tool.name)
        if tool.name=='task_acceptance_evidence':
            raise HTTPException(403 if error=='denied' else 503,'Контролируемый отказ')
        result = await real(app,tool,args,headers)
        if tool.name=='work_order_analytics' and error=='no-id':
            result['groups'][0].pop('id')
        return result

    monkeypatch.setattr(read_transport,'invoke',transport)
    before = checksums(case)
    answer, actions, _ = turn(admin,EARLIEST)
    state = stored(case,answer['turn_id'])
    assert actions==[] and checksums(case)==before
    if error=='no-id':
        assert invoked==['work_order_analytics'] and 'выбор' not in answer['answer'].casefold()
        assert state['outcome']=='blocked' and state['goals'][1]['reason']=='dependency_output_unavailable'
    else:
        assert state['outcome']=='partial' and task in answer['answer']
        assert ('HTTP 403' if error=='denied' else 'HTTP 503') in answer['answer']
        assert 'препятствий не найдено' not in answer['answer']


def test_missing_confirmed_service_excludes_unresolved_and_accepted(assistant_case):
    case = assistant_case
    engine, _, admin, _, ids = case
    stale, fresh, unknown = [inventory(admin,ids,f'{code}-{ids["marker"]}') for code in ('ST','FR','UN')]
    past = datetime.now(timezone.utc)-timedelta(days=15)
    _, accepted = add_report(case,fresh,actual=past.isoformat(),submitted=past+timedelta(hours=1))
    add_report(case,unknown,actual=None,submitted=past)
    add_report(case,stale,actual=past.isoformat(),submitted=past+timedelta(hours=1),acceptance=None)
    with engine.begin() as db:
        db.execute(text('UPDATE acceptance_reviews SET reviewed_at=:reviewed WHERE work_report_id=:id'),
                   dict(reviewed=past+timedelta(hours=2),id=accepted))
    first,last = (past-timedelta(days=2)).date(),(past+timedelta(days=2)).date()
    prompt = f'Найди оборудование без подтверждённого обслуживания с {first} по {last}.'
    case[1].state.assistant_provider_factory = lambda: Provider(prompt,group_by='equipment',metric='without_service')
    result, actions, _ = turn(admin,prompt)
    state = stored(case,result['turn_id'])
    assert actions==[] and state['outcome']=='partial',result['answer']
    assert stale['equipment_id'] in result['answer']
    assert all(row['equipment_id'] not in result['answer'] for row in (fresh,unknown))
    assert 'по 1 единицам факт нельзя проверить' in result['answer'].casefold()


def test_real_access_and_attempt_revision_gate(assistant_case):
    case = assistant_case
    engine, _, admin, login, ids = case
    asset = inventory(admin,ids,'OWN-'+ids['marker'])
    worker, email = join(case)
    deadline = datetime.now(timezone.utc)-timedelta(days=2)
    own = add_order(case,[asset],'Своя проверка','assigned',deadline,None)
    foreign = add_order(case,[asset],'Чужая просрочка','assigned',deadline-timedelta(days=3),None)
    with engine.begin() as db:
        db.execute(text('INSERT INTO work_assignments(site_id,work_order_id,user_id,assigned_by) '
                        'VALUES (:site,:task,:worker,:user)'),dict(ids,task=own,worker=worker))
    source = '/api/v1/assistant/workspace/'
    with closing(login(email)) as executor:
        selected = executor.get(source+'work-order-analytics',params=dict(group_by='task',metric='earliest_overdue')).json()
        assert [row['id'] for row in selected['groups']]==[own]
        assert executor.get(source+f'tasks/{foreign}/acceptance-evidence',params={'expected_revision':1}).status_code==404
        assert executor.get(source+f'tasks/{own}/acceptance-evidence',params={'expected_revision':1}).status_code==200
        assert executor.get(source+f'tasks/{own}/acceptance-evidence',params={'expected_revision':2}).status_code==409
