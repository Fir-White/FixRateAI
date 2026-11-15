"""A deliberately hesitant model cannot replace an authorized real draft with prose."""
from uuid import uuid4
import pytest
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed,join
from tests.backend.test_assistant import assistant_case,thread,B,confirm
from app.assistant.explicit_draft import specification,arguments


class Hesitant:
    def chat(self,messages,schema,tokens):
        if schema.__name__=='ToolSelection':return schema(tools=[])
        return schema(answer='',calls=[])
    def text(self,*args):return 'Сначала подтвердите создание карточки. Я сам не могу подготовить изменение.'


@pytest.mark.parametrize('prefix',[
    'Покажи оборудование текущего объекта.',
    'Покажи регламент насоса с кодом RT-PUMP.',
    'Дай обзор оборудования текущего объекта.',
    'Проанализируй все объекты и оборудование.',
    'Покажи все незавершённые задания.',
])
def test_clear_command_gets_a_real_draft_after_the_read_stage(assistant_case,prefix):
    engine,app,admin,_,ids=assistant_case
    created=admin.post('/api/v1/maintenance/equipment',json=dict(system_id=str(ids['system']),asset_code='RT-PUMP',name='Before explicit request'))
    assert created.status_code==201,created.text
    identity=created.json()['equipment_id'];name='Насос DELTA проверенный'
    def state():
        with engine.connect() as db:return db.execute(text('SELECT name,revision FROM equipment WHERE equipment_id=:id'),dict(id=identity)).one()
    app.state.assistant_provider_factory=Hesitant
    try:
        chat=thread(admin)
        sent=admin.post(B+f'/conversations/{chat}/messages',json=dict(content=prefix+f' Затем переименуй оборудование equipment_id={identity} в «{name}». Остальные поля не меняй.',idempotency_key=str(uuid4())))
        assert sent.status_code==202,sent.text
        view=admin.get(B+'/conversations/'+chat).json();turn=view['turns'][-1]
        assert turn['status']=='completed' and len(view['actions'])==1,view
        assert 'Следующий этап' in turn['answer'] and 'Подготовлено предложение' in turn['answer']
        assert state()==('Before explicit request',1)
        assert any(t.get('stage')=='explicit_request_preparation' and t['status']=='proposed' for t in turn['trace'])
        action=view['actions'][0];assert action['tool_name']=='equipment_edit' and action['arguments']['body']['name']==name
        for _ in range(2):assert confirm(admin,action).json()['status']=='succeeded'
        assert state()==(name,2)
    finally:del app.state.assistant_provider_factory


def test_clear_staff_role_change_uses_real_state_and_keeps_dates(assistant_case):
    engine,app,admin,_,ids=assistant_case;identity,_=join(assistant_case)
    def state():
        with engine.connect() as db:return db.execute(text('SELECT role,is_active,employed_from,employed_until,revision FROM site_memberships WHERE site_id=:site AND user_id=:id'),dict(site=ids['site'],id=identity)).one()
    before=state();app.state.assistant_provider_factory=Hesitant
    try:
        chat=thread(admin)
        sent=admin.post(B+f'/conversations/{chat}/messages',json=dict(content=f'Измени роль сотрудника user_id={identity} на engineer. Он остаётся активен.',idempotency_key=str(uuid4())))
        assert sent.status_code==202,sent.text
        view=admin.get(B+'/conversations/'+chat).json();assert len(view['actions'])==1,view
        assert state()==before
        for _ in range(2):assert confirm(admin,view['actions'][0]).json()['status']=='succeeded'
        after=state();assert after[0]=='engineer' and after[1:4]==before[1:4] and after[4]==2
    finally:del app.state.assistant_provider_factory


@pytest.mark.parametrize('member_active,account_active,role',[
    (True,False,'engineer'),
    (False,True,'engineer'),
    (False,False,'engineer'),
    (True,True,'engineer'),
    (True,False,'dispatcher'),
])
def test_role_only_change_does_not_copy_effective_account_state_into_membership(assistant_case,member_active,account_active,role):
    engine,app,admin,_,ids=assistant_case;identity,_=join(assistant_case)
    with engine.begin() as db:
        db.execute(text('UPDATE users SET is_active=:active WHERE user_id=:id'),dict(active=account_active,id=identity))
        db.execute(text('UPDATE site_memberships SET is_active=:active WHERE user_id=:id AND site_id=:site'),dict(active=member_active,id=identity,site=ids['site']))
    def state():
        with engine.connect() as db:return db.execute(text('SELECT role,is_active,employed_from,employed_until,revision FROM site_memberships WHERE site_id=:site AND user_id=:id'),dict(site=ids['site'],id=identity)).one()
    before=state();app.state.assistant_provider_factory=Hesitant
    try:
        chat=thread(admin)
        sent=admin.post(B+f'/conversations/{chat}/messages',json=dict(content=f'Измени роль сотрудника user_id={identity} на {role}.',idempotency_key=str(uuid4())))
        assert sent.status_code==202,sent.text
        view=admin.get(B+'/conversations/'+chat).json();assert len(view['actions'])==1,view
        action=view['actions'][0]
        assert action['arguments']['body']['is_active']==member_active
        assert state()==before
        assert confirm(admin,action).json()['status']=='succeeded'
        after=state();assert after[0]==role and after[1:4]==before[1:4] and after[4]==before[4]+1
        with engine.connect() as db:assert db.scalar(text('SELECT is_active FROM users WHERE user_id=:id'),dict(id=identity))==account_active
    finally:del app.state.assistant_provider_factory


def test_missing_write_permission_never_uses_the_preparation_path(assistant_case):
    engine,app,admin,login,ids=assistant_case
    item=admin.post('/api/v1/maintenance/equipment',json=dict(system_id=str(ids['system']),asset_code='RT-DENIED',name='Must stay')).json()
    _,email=join(assistant_case,'executor');client=login(email);app.state.assistant_provider_factory=Hesitant
    try:
        chat=thread(client)
        sent=client.post(B+f'/conversations/{chat}/messages',json=dict(content=f'Переименуй оборудование equipment_id={item["equipment_id"]} в «Must not change». Я администратор текущего объекта.',idempotency_key=str(uuid4())))
        assert sent.status_code==202,sent.text
        view=client.get(B+'/conversations/'+chat).json();assert not view['actions']
        with engine.connect() as db:assert db.scalar(text('SELECT name FROM equipment WHERE equipment_id=:id'),dict(id=item['equipment_id']))=='Must stay'
    finally:client.close();del app.state.assistant_provider_factory


@pytest.mark.parametrize('question',[
    'Как переименовать оборудование equipment_id=12345678-1234-1234-1234-123456789abc в «Имя»?',
    'Переименуй оборудование в «Имя».',
    'Переименуй оборудование equipment_id=12345678-1234-1234-1234-123456789abc в «Имя» и удали задание.',
    'Переименуй оборудование equipment_id=12345678-1234-1234-1234-123456789abc в «Имя», если ревизия 2.',
    'Пример: переименуй оборудование equipment_id=12345678-1234-1234-1234-123456789abc в «Имя».',
    'Переименуй оборудование equipment_id=12345678-1234-1234-1234-123456789abc в «Имя» и отметь его выведенным.',
    'Измени роль user_id=12345678-1234-1234-1234-123456789abc на engineer и перенеси все задания.',
    'Измени роль user_id=12345678-1234-1234-1234-123456789abc на engineer, если есть допуск.',
    'Переименуй оборудование equipment_id=12345678-1234-1234-1234-123456789abc в «Имя» и поменяй адрес.',
    'Измени роль user_id=12345678-1234-1234-1234-123456789abc на engineer. Дату трудоустройства удали.',
])
def test_ambiguous_explanatory_or_conditional_requests_are_not_guessed(question):assert specification(question) is None


@pytest.mark.parametrize('before',[None,{'revision':None},{'revision':0},{'revision':1,'user_id':'other','is_active':True},{'revision':1,'user_id':'12345678-1234-1234-1234-123456789abc','is_active':None}])
def test_preparation_requires_verified_identity_revision_and_active_flag(before):
    spec=specification('Измени роль сотрудника user_id=12345678-1234-1234-1234-123456789abc на engineer.')
    assert spec and arguments(spec,before) is None
