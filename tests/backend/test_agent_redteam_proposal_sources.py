"""Authoritative technical metadata/user literals; real API/SQL and unchanged stale guards."""
from uuid import uuid4
import pytest
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed,equipment,join
from tests.backend.test_assistant import assistant_case,thread,B,confirm,proposal,Scripted


def ask(app,client,question,tool,args):
    app.state.assistant_provider_factory=lambda:Scripted([dict(answer='',calls=[dict(tool=tool,arguments=args,explanation='TEST ONLY model-supplied metadata error')])])
    try:
        chat=thread(client)
        sent=client.post(B+f'/conversations/{chat}/messages',json=dict(content=question,idempotency_key=str(uuid4())))
        assert sent.status_code==202,sent.text
        view=client.get(B+'/conversations/'+chat).json()
        assert len(view['actions'])==1,view
        return view['actions'][0]
    finally:del app.state.assistant_provider_factory


@pytest.mark.parametrize('name,wrong_revision',[
    ('Насос DELTA проверенный',2),
    ('Насос "A"',3),
    ('RT/Насос-1',5),
    ('Насос \\ север',99),
    ('Онлайн_%_Тест',2147483646),
])
def test_llm_proposal_uses_fresh_revision_and_the_exact_user_literal(assistant_case,name,wrong_revision):
    engine,app,admin,_,ids=assistant_case;asset=equipment(admin,ids);identity=asset['equipment_id']
    path='/api/v1/maintenance/equipment/'+identity
    def state():
        with engine.connect() as db:return db.execute(text('SELECT name,revision FROM equipment WHERE equipment_id=:id'),dict(id=identity)).one()
    before=state();assert before[1]==1
    record=ask(app,admin,f'Переименуй оборудование equipment_id={identity} в «{name}». Подготовь предложение для подтверждения.','equipment_edit',dict(path=dict(equipment_id=identity),body=dict(expected_revision=wrong_revision,name='\\"'+name+'\\"')))
    assert record['arguments']['body']['expected_revision']==before[1]
    assert record['arguments']['body']['name']==name
    assert record['before_snapshot']['preview']['revision']==before[1] and state()==before
    # Actual HTTP optimistic locking is unchanged; only draft preparation may
    # supply a server-issued token before the human reviews the final hash.
    assert admin.patch(path,json=dict(expected_revision=wrong_revision,name='MUST NOT WRITE')).status_code==409
    assert state()==before
    for _ in range(2):
        result=confirm(admin,record)
        assert result.status_code==200 and result.json()['status']=='succeeded',result.text
    assert state()==(name,2)


def test_staff_revision_is_derived_without_changing_employment_metadata(assistant_case):
    engine,app,admin,_,ids=assistant_case;identity,_=join(assistant_case)
    def state():
        with engine.connect() as db:return db.execute(text('SELECT role,employed_from,employed_until,revision FROM site_memberships WHERE site_id=:site AND user_id=:id'),dict(site=ids['site'],id=identity)).one()
    before=state()
    record=ask(app,admin,f'Измени роль сотрудника user_id={identity} на engineer. Он остаётся активен. Подготовь предложение.','staff_edit',dict(path=dict(user_id=str(identity)),body=dict(expected_revision=2,role='engineer',is_active=True)))
    assert record['arguments']['body']['expected_revision']==1 and state()==before
    assert confirm(admin,record).json()['status']=='succeeded'
    after=state();assert after[0]=='engineer' and after[1:3]==before[1:3] and after[3]==2


def test_explicit_user_revision_condition_is_not_silently_replaced(assistant_case):
    engine,app,admin,_,ids=assistant_case;asset=equipment(admin,ids);identity=asset['equipment_id']
    record=ask(app,admin,f'Переименуй оборудование equipment_id={identity} в «Условное имя», только если текущая ревизия 2.','equipment_edit',dict(path=dict(equipment_id=identity),body=dict(expected_revision=2,name='Условное имя')))
    assert record['arguments']['body']['expected_revision']==2
    result=confirm(admin,record)
    assert result.status_code==200 and result.json()['status']=='failed' and result.json()['result']['status_code']==409,result.text
    with engine.connect() as db:assert db.scalar(text('SELECT revision FROM equipment WHERE equipment_id=:id'),dict(id=identity))==1


def test_direct_mcp_stale_revision_is_not_silently_replaced(assistant_case):
    engine,_,admin,_,ids=assistant_case;asset=equipment(admin,ids);identity=asset['equipment_id']
    record=proposal(admin,thread(admin),'equipment_edit',dict(path=dict(equipment_id=identity),body=dict(expected_revision=2,name='MUST NOT WRITE')))
    assert record['arguments']['body']['expected_revision']==2
    result=confirm(admin,record)
    assert result.status_code==200 and result.json()['status']=='failed' and result.json()['result']['status_code']==409,result.text
    with engine.connect() as db:assert db.scalar(text('SELECT revision FROM equipment WHERE equipment_id=:id'),dict(id=identity))==1


@pytest.mark.parametrize('mistake',['wrong_tool','wrong_target','unrequested_field'])
def test_model_cannot_prepare_a_different_change_than_the_explicit_command(assistant_case,mistake):
    engine,app,admin,_,ids=assistant_case;first=equipment(admin,ids);second=equipment(admin,dict(ids,marker=ids['marker']+'-other'))
    name='Approved target name';identity=first['equipment_id']
    if mistake=='wrong_tool':
        tool='equipment_create';args=dict(body=dict(system_id=str(ids['system']),asset_code='MUST-NOT-CREATE',name='Unrequested asset'))
    else:
        tool='equipment_edit';args=dict(path=dict(equipment_id=second['equipment_id'] if mistake=='wrong_target' else identity),body=dict(expected_revision=1,name=name))
        if mistake=='unrequested_field':args['body']['status']='retired'
    app.state.assistant_provider_factory=lambda:Scripted([dict(answer='',calls=[dict(tool=tool,arguments=args,explanation='TEST ONLY wrong model choice')]),dict(answer='Модель остановилась.',calls=[])])
    try:
        chat=thread(admin)
        sent=admin.post(B+f'/conversations/{chat}/messages',json=dict(content=f'Переименуй оборудование equipment_id={identity} в «{name}». Остальные поля не меняй.',idempotency_key=str(uuid4())))
        assert sent.status_code==202,sent.text
        view=admin.get(B+'/conversations/'+chat).json();assert len(view['actions'])==1,view
        action=view['actions'][0]
        assert action['tool_name']=='equipment_edit' and action['arguments']['path']['equipment_id']==identity
        assert set(action['arguments']['body'])=={'name','expected_revision'}
        assert confirm(admin,action).json()['status']=='succeeded'
        with engine.connect() as db:
            assert db.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site'),dict(site=ids['site']))==2
            assert db.execute(text('SELECT name,status FROM equipment WHERE equipment_id=:id'),dict(id=identity)).one()==(name,'active')
            assert db.scalar(text('SELECT revision FROM equipment WHERE equipment_id=:id'),dict(id=second['equipment_id']))==1
    finally:del app.state.assistant_provider_factory
