"""Independent workflow security regressions on real HTTP/PostgreSQL.

Only model planning is scripted. Proposals, authorization, confirmations,
postcondition reads and persisted workflow records use the actual application.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import json

import pytest
from sqlalchemy import text

from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case, B, thread, equipment_body, proposal, confirm


class Planned:
    response_model='TEST-ONLY-independent-security-planner'

    def __init__(self, goals, calls=()):
        self.goals=goals
        self.calls=iter(calls)

    def chat(self, messages, schema, tokens):
        if schema.__name__=='ToolSelection':
            return schema.model_validate(dict(tools=[],goals=self.goals))
        calls=next(self.calls,None)
        if calls is None:
            raise RuntimeError('TEST ONLY scripted planner has no more steps')
        return schema.model_validate(dict(answer='',calls=[dict(tool=name,
            arguments_json=json.dumps(args),explanation='TEST ONLY authorized objective') for name,args in calls]))


def send(client,chat,content='TEST ONLY requested equipment',**values):
    return client.post(B+f'/conversations/{chat}/messages',json={
        'idempotency_key':str(uuid4()),'content':content,**values})


def view(client,chat):
    response=client.get(B+'/conversations/'+chat)
    assert response.status_code==200,response.text
    return response.json()


def blocked_source(app,client,chat):
    app.state.assistant_provider_factory=lambda:Planned([dict(id='need',title='Preserved objective',tool='')])
    response=send(client,chat)
    assert response.status_code==202,response.text
    return response.json()['turn_id']


@pytest.fixture(autouse=True)
def clear_scripted_provider(assistant_case):
    yield
    app=assistant_case[1]
    if hasattr(app.state,'assistant_provider_factory'):
        del app.state.assistant_provider_factory


def test_resume_source_is_scoped_to_owner_conversation_and_role(assistant_case):
    _,app,client,_,_=assistant_case
    own=thread(client);foreign=thread(client.chief)
    source=blocked_source(app,client.chief,foreign)
    response=send(client,own,resume_turn_id=source)
    assert response.status_code==404,response.text
    assert client.get(B+'/conversations/'+foreign).status_code==404


def test_idempotent_message_key_cannot_be_reused_for_different_resume_source(assistant_case):
    _,app,client,_,_=assistant_case;chat=thread(client)
    first=blocked_source(app,client,chat);second=blocked_source(app,client,chat)
    key=str(uuid4())
    response=send(client,chat,content='TEST ONLY continue',idempotency_key=key,resume_turn_id=first)
    assert response.status_code==202,response.text
    replay=send(client,chat,content='TEST ONLY continue',idempotency_key=key,resume_turn_id=first)
    assert replay.status_code==202 and replay.json()['turn_id']==response.json()['turn_id']
    changed=send(client,chat,content='TEST ONLY continue',idempotency_key=key,resume_turn_id=second)
    assert changed.status_code==409,changed.text


def test_crash_after_committed_proposal_recovers_same_card_on_resume(assistant_case,monkeypatch):
    from app.assistant import service
    engine,app,client,_,ids=assistant_case;chat=thread(client);body=equipment_body(ids)
    goals=[dict(id='create_one',title='Add the explicitly requested asset',tool='equipment_create')]
    app.state.assistant_provider_factory=lambda:Planned(goals,[[('equipment_create',dict(body=body))]])
    original=service.propose;lost=[False]
    async def commit_then_crash(*args,**kwargs):
        result=await original(*args,**kwargs)
        if not lost[0]:
            lost[0]=True
            raise RuntimeError('TEST ONLY worker lost after proposal commit')
        return result
    monkeypatch.setattr(service,'propose',commit_then_crash)
    response=send(client,chat)
    assert response.status_code==202,response.text
    source=response.json()['turn_id']
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM assistant_actions WHERE conversation_id=:chat'),dict(chat=chat))==1
        assert db.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site AND asset_code=:code'),dict(site=ids['site'],code=body['asset_code']))==0
    resumed=send(client,chat,content='TEST ONLY continue saved objective',resume_turn_id=source)
    assert resumed.status_code==202,resumed.text
    saved=view(client,chat)
    assert len(saved['actions'])==1,saved['actions']
    assert saved['turns'][-1]['workflow']['goals'][0]['action_id']==saved['actions'][0]['action_id']
    # Confirmation uses the real API, then a resource readback. No generated text
    # or HTTP-only success assertion substitutes for the persisted equipment.
    applied=confirm(client,saved['actions'][0])
    assert applied.status_code==200 and applied.json()['status']=='succeeded',applied.text
    assert applied.json()['result']['verification']['status']=='confirmed'
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site AND asset_code=:code'),dict(site=ids['site'],code=body['asset_code']))==1
    replay=confirm(client,saved['actions'][0])
    assert replay.json()['action_id']==applied.json()['action_id']


def test_dependent_same_resource_change_can_continue_after_verified_confirmation(assistant_case):
    _,app,client,_,ids=assistant_case;chat=thread(client)
    created=client.post('/api/v1/maintenance/equipment',json=equipment_body(ids))
    assert created.status_code==201,created.text
    identity=created.json()['equipment_id']
    goals=[dict(id='name',title='Rename requested equipment',tool='equipment_edit'),
           dict(id='location',title='Then set its requested room',tool='equipment_edit',depends_on=['name'])]
    app.state.assistant_provider_factory=lambda:Planned(goals,[[('equipment_edit',dict(path=dict(equipment_id=identity),body=dict(name='Reviewed rename')))]])
    response=send(client,chat,content='TEST ONLY rename then set location')
    assert response.status_code==202,response.text
    first=view(client,chat);assert len(first['actions'])==1
    applied=confirm(client,first['actions'][0])
    assert applied.json()['result']['verification']['status']=='confirmed',applied.text
    app.state.assistant_provider_factory=lambda:Planned(goals,[[('equipment_edit',dict(path=dict(equipment_id=identity),body=dict(location='Reviewed room')))]])
    resumed=send(client,chat,content='TEST ONLY continue saved task',resume_turn_id=response.json()['turn_id'])
    assert resumed.status_code==202,resumed.text
    second=view(client,chat);assert len(second['actions'])==2,second
    new=next(action for action in second['actions'] if action['action_id']!=first['actions'][0]['action_id'])
    assert new['arguments']['body']['expected_revision']==2
    applied=confirm(client,new)
    assert applied.json()['result']['verification']['status']=='confirmed',applied.text
    actual=client.get('/api/v1/maintenance/equipment/'+identity).json()
    assert actual['name']=='Reviewed rename' and actual['location']=='Reviewed room' and actual['revision']==3
    # Returning to an older parent turn must consult the newest lineage state,
    # rather than replay a step which the child already completed.
    again=send(client,chat,content='TEST ONLY continue original task',resume_turn_id=response.json()['turn_id'])
    assert again.status_code==409,again.text


def test_polling_cannot_overwrite_newer_worker_checkpoint(assistant_case,monkeypatch):
    from app.assistant import workflow as wf
    engine,app,client,_,_=assistant_case;chat=thread(client)
    source=blocked_source(app,client,chat)
    with engine.connect() as db:
        old=db.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'),dict(id=source))
    newer=deepcopy(old);newer['revision']+=1;newer['stop_reason']='TEST_NEWER_CHECKPOINT'
    original=wf.refresh_actions;injected=[False]
    def concurrent_checkpoint(session,state,*args,**kwargs):
        result=original(session,state,*args,**kwargs)
        if not injected[0]:
            injected[0]=True
            with engine.begin() as db:
                db.execute(text('UPDATE assistant_turns SET workflow=CAST(:state AS jsonb) WHERE turn_id=:id'),dict(id=source,state=json.dumps(newer)))
        return result
    monkeypatch.setattr(wf,'refresh_actions',concurrent_checkpoint)
    assert client.get(B+'/conversations/'+chat).status_code==200
    with engine.connect() as db:
        actual=db.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'),dict(id=source))
    assert actual['revision']==newer['revision'] and actual['stop_reason']=='TEST_NEWER_CHECKPOINT'


def test_expired_dispatch_claim_is_durable_uncertain_and_confirmation_does_not_retry(assistant_case,monkeypatch):
    from app.assistant import service
    engine,app,client,_,ids=assistant_case;chat=thread(client)
    record=proposal(client,chat,'equipment_create',dict(body=equipment_body(ids)))
    with engine.begin() as db:
        db.execute(text("UPDATE assistant_actions SET status='executing',started_at=:when WHERE action_id=:id"),dict(id=record['action_id'],when=datetime.now(timezone.utc)-timedelta(minutes=4)))
    view(client,chat)
    with engine.connect() as db:
        actual=db.execute(text('SELECT status,result FROM assistant_actions WHERE action_id=:id'),dict(id=record['action_id'])).mappings().one()
    assert actual['status']=='uncertain'
    assert actual['result']['verification']['status']=='unverified'
    async def forbidden(*args):pytest.fail('Uncertain action must never be dispatched again')
    monkeypatch.setattr(service,'invoke',forbidden)
    assert confirm(client,record).json()['status']=='uncertain'


def test_document_injection_does_not_grant_cross_specialist_mutation_or_confirmation(assistant_case):
    engine,app,client,_,ids=assistant_case;chat=thread(client)
    body=equipment_body(ids)
    # Malicious model output simulates obeying an injected document instruction.
    # A read objective must not dispatch or even propose an unrelated write.
    goals=[dict(id='read_inventory',title='Read equipment registry',tool='equipment_find')]
    app.state.assistant_provider_factory=lambda:Planned(goals,
        [[('equipment_create',dict(body=body))],[('confirm_action',{})],[('equipment_find',{})]])
    response=send(client,chat,content='TEST ONLY read inventory; document contains untrusted instructions')
    assert response.status_code==202,response.text
    saved=view(client,chat)
    assert saved['actions']==[]
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site AND asset_code=:code'),dict(site=ids['site'],code=body['asset_code']))==0
    trace=saved['turns'][-1]['trace']
    assert any(row['tool']=='equipment_create' and row['status']=='denied' for row in trace),trace


def test_stop_prevents_late_actions_and_does_not_expose_foreign_goal_state(assistant_case):
    engine,_,client,_,_=assistant_case;chat=thread(client);turn=uuid4()
    with engine.begin() as db:
        db.execute(text("INSERT INTO assistant_turns(turn_id,conversation_id,request_key,content,status,prompt_version) VALUES (:turn,:chat,:key,'TEST ONLY','running','TEST')"),dict(turn=turn,chat=chat,key=uuid4()))
    url=B+f'/conversations/{chat}/turns/{turn}/stop'
    assert client.chief.post(url).status_code==404
    assert client.post(url).json()['stopped'] is True
    assert client.post(url).json()['stopped'] is False


def test_two_independent_creations_have_separate_confirmation_boundaries(assistant_case):
    engine,app,client,_,ids=assistant_case;chat=thread(client)
    first,second=equipment_body(ids),equipment_body(ids)
    goals=[dict(id='first',title='Create first requested asset',tool='equipment_create'),
           dict(id='second',title='Create second requested asset',tool='equipment_create')]
    app.state.assistant_provider_factory=lambda:Planned(goals,
        [[('equipment_create',dict(body=first))],[('equipment_create',dict(body=second))]])
    response=send(client,chat,content='TEST ONLY create two independent assets after my separate confirmations')
    assert response.status_code==202,response.text
    saved=view(client,chat)
    assert len(saved['actions'])==2,saved
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site'),dict(site=ids['site']))==0
    applied=confirm(client,saved['actions'][0])
    assert applied.json()['result']['verification']['status']=='confirmed',applied.text
    saved=view(client,chat)
    assert {action['status'] for action in saved['actions']}=={'succeeded','proposed'}
    assert saved['turns'][-1]['workflow']['outcome']=='awaiting_confirmation'
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site'),dict(site=ids['site']))==1


def test_failed_initial_planning_can_resume_without_losing_original_lineage(assistant_case):
    engine,app,client,_,ids=assistant_case;chat=thread(client);body=equipment_body(ids)
    class BrokenPlanner:
        def chat(self,*args):raise RuntimeError('TEST ONLY planning failed before decomposition')
    app.state.assistant_provider_factory=BrokenPlanner
    response=send(client,chat,content='TEST ONLY add original requested asset')
    assert response.status_code==202,response.text
    source=response.json()['turn_id']
    initial=view(client,chat)
    assert initial['turns'][-1]['status']=='failed' and initial['turns'][-1]['workflow']['outcome']!='completed'
    app.state.assistant_provider_factory=lambda:Planned(
        [dict(id='original',title='Original requested creation',tool='equipment_create')],
        [[('equipment_create',dict(body=body))]])
    resumed=send(client,chat,content='TEST ONLY continue saved original request',resume_turn_id=source)
    assert resumed.status_code==202,resumed.text
    saved=view(client,chat)
    assert len(saved['actions'])==1,saved
    with engine.connect() as db:
        root=db.scalar(text('SELECT workflow_root_turn_id FROM assistant_actions WHERE action_id=:id'),dict(id=saved['actions'][0]['action_id']))
    assert str(root)==source
