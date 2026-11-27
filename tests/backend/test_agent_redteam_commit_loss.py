"""Faults AFTER a real committed API write; never substitute a successful domain result."""
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case,thread,proposal,equipment_body,confirm


@pytest.mark.parametrize('failure',['http500','http502','http503','timeout','connection'])
def test_committed_write_lost_response_is_not_dispatched_twice(assistant_case,monkeypatch,failure):
    from app.assistant import service
    engine,app,client,_,ids=assistant_case
    body=equipment_body(ids);body['asset_code']='RT-LOSS-'+uuid4().hex[:10]
    command=proposal(client,thread(client),'equipment_create',dict(body=body))
    original=service.invoke;dispatches=[]
    async def commit_then_lose(*args,**kwargs):
        value=await original(*args,**kwargs)
        dispatches.append(value)
        if failure.startswith('http'):raise HTTPException(int(failure[4:]),'TEST ONLY response lost after real commit')
        if failure=='timeout':raise TimeoutError('TEST ONLY after commit')
        raise ConnectionError('TEST ONLY after commit')
    monkeypatch.setattr(service,'invoke',commit_then_lose)
    for _ in range(3):
        response=confirm(client,command)
        assert response.status_code==200,response.text
        assert response.json()['status']=='uncertain',response.text
    assert len(dispatches)==1
    with engine.connect() as db:
        rows=db.execute(text('SELECT name,asset_code FROM equipment WHERE site_id=:site AND asset_code=:code'),dict(site=ids['site'],code=body['asset_code'])).all()
        assert rows==[(body['name'],body['asset_code'])]
        assert db.scalar(text('SELECT status FROM assistant_actions WHERE action_id=:id'),dict(id=command['action_id']))=='uncertain'
