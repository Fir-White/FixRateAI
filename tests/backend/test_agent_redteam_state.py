"""Stateful approval lifecycles. Genuine proposals, domain writes and DB assertions."""
from uuid import uuid4
import pytest
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case,thread,proposal,confirm,equipment_body,B

@pytest.mark.parametrize('boundary',('rejection','expiry','foreign_owner','role_change','chat_deleted','stale'))
def test_failed_boundary_then_independent_success_and_replay(assistant_case,boundary):
    engine,_,admin,_,ids=assistant_case;chat=thread(admin)
    body=equipment_body(ids);before=admin.get('/api/v1/maintenance/equipment').json()['total']
    target=None
    if boundary=='stale':
        target=admin.post('/api/v1/maintenance/equipment',json=body).json()
        action=proposal(admin,chat,'equipment_edit',dict(path=dict(equipment_id=target['equipment_id']),body=dict(expected_revision=1,name='Should never replace human update')))
    else:action=proposal(admin,chat,'equipment_create',dict(body=body))
    # An inaccurate hash must not consume the legitimate proposal or write data.
    denied=admin.post(B+'/actions/'+action['action_id']+'/confirm',json=dict(payload_sha256='0'*64,confirmed=True))
    assert denied.status_code==409
    if boundary=='rejection':
        assert admin.post(B+'/actions/'+action['action_id']+'/reject').json()['status']=='rejected'
        assert confirm(admin,action).json()['status']=='rejected'
    elif boundary=='expiry':
        with engine.begin() as db:db.execute(text("UPDATE assistant_actions SET expires_at=now()-interval '1 second' WHERE action_id=:id"),dict(id=action['action_id']))
        assert confirm(admin,action).status_code==409
    elif boundary=='foreign_owner':assert confirm(admin.chief,action).status_code==404
    elif boundary=='role_change':
        with engine.begin() as db:db.execute(text("UPDATE site_memberships SET role='technician' WHERE site_id=:site AND user_id=:user"),ids)
        try:assert confirm(admin,action).status_code==404
        finally:
            with engine.begin() as db:db.execute(text("UPDATE site_memberships SET role='admin' WHERE site_id=:site AND user_id=:user"),ids)
    elif boundary=='chat_deleted':
        assert admin.delete(B+'/conversations/'+chat).status_code==200
        assert confirm(admin,action).status_code==404
        chat=thread(admin)
    elif boundary=='stale':
        human=admin.patch('/api/v1/maintenance/equipment/'+target['equipment_id'],json=dict(expected_revision=1,name='Human version retained'))
        assert human.status_code==200
        assert confirm(admin,action).status_code==409
        saved=admin.get('/api/v1/maintenance/equipment/'+target['equipment_id']).json()
        assert saved['name']=='Human version retained' and saved['revision']==2
    count=admin.get('/api/v1/maintenance/equipment').json()['total']
    assert count==before+(boundary=='stale')
    # A declined/blocked earlier action must not poison the next explicit action.
    next_body=equipment_body(ids);next_action=proposal(admin,chat,'equipment_create',dict(body=next_body))
    done=confirm(admin,next_action);assert done.status_code==200 and done.json()['status']=='succeeded',done.text
    for _ in range(3):assert confirm(admin,next_action).json()==done.json()
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM equipment WHERE site_id=:site AND asset_code=:code'),dict(site=ids['site'],code=next_body['asset_code']))==1
        assert db.scalar(text("SELECT count(*) FROM audit_events WHERE entity_id=:id AND action='confirmed'"),dict(id=next_action['action_id']))==1
