"""Explicit transport faults and misleading model prose; actual DB contents never replaced."""
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed,equipment
from tests.backend.test_assistant import assistant_case,thread,B


class ReadReply:
    def __init__(self,reply):self.reply=reply;self.steps=0
    def chat(self,messages,schema,tokens):
        if schema.__name__=='ToolSelection':return schema(tools=['equipment_find'])
        self.steps+=1
        return schema(answer='',calls=[dict(tool='equipment_find',arguments_json='{}',explanation='TEST ONLY authorized read')] if self.steps==1 else [])
    def text(self,*args):return self.reply


@pytest.mark.parametrize('status',[401,403,404,422,503])
def test_all_failed_reads_cannot_be_rendered_as_an_empty_registry(assistant_case,monkeypatch,status):
    from app.assistant import read_transport
    engine,app,admin,_,ids=assistant_case
    asset=equipment(admin,ids)
    async def unavailable(*args,**kwargs):raise HTTPException(status,'TEST ONLY explicit read fault; no fake successful result')
    monkeypatch.setattr(read_transport,'invoke',unavailable)
    app.state.assistant_provider_factory=lambda:ReadReply('Оборудование не найдено в реестре. Повторите запрос вручную.')
    try:
        chat=thread(admin)
        sent=admin.post(B+f'/conversations/{chat}/messages',json=dict(content='Перечисли оборудование.',idempotency_key=str(uuid4())))
        assert sent.status_code==202,sent.text
        state=admin.get(B+'/conversations/'+chat).json();turn=state['turns'][-1]
        assert turn['status']=='completed' and not state['actions']
        assert 'Не удалось получить запрошенные данные' in turn['answer'],turn
        assert 'не подтверждает отсутствие записей' in turn['answer']
        assert 'Оборудование не найдено в реестре.' not in turn['answer']
        assert any(t['tool']=='__evidence_guard' and t['error_type']=='unverified_read_results' for t in turn['trace'])
        with engine.connect() as db:assert db.scalar(text('SELECT count(*) FROM equipment WHERE equipment_id=:id'),dict(id=asset['equipment_id']))==1
    finally:del app.state.assistant_provider_factory


@pytest.mark.parametrize('has_asset',[False,True])
def test_verified_empty_or_nonempty_read_is_not_overridden(assistant_case,has_asset):
    _,app,admin,_,ids=assistant_case
    asset=equipment(admin,ids) if has_asset else None
    reply='Проверенные данные получены.' if has_asset else 'Проверенный реестр пуст.'
    app.state.assistant_provider_factory=lambda:ReadReply(reply)
    try:
        chat=thread(admin)
        sent=admin.post(B+f'/conversations/{chat}/messages',json=dict(content='Перечисли оборудование.',idempotency_key=str(uuid4())))
        assert sent.status_code==202,sent.text
        turn=admin.get(B+'/conversations/'+chat).json()['turns'][-1]
        assert f'**{int(has_asset)}**' in turn['answer']
        if asset:assert asset['name'] in turn['answer'] and asset['asset_code'] in turn['answer']
        assert not any(t['tool']=='__evidence_guard' for t in turn['trace'])
        assert any(t['tool']=='equipment_find' and t['status']=='completed' and t['result']['total']==int(has_asset) for t in turn['trace'])
    finally:del app.state.assistant_provider_factory
