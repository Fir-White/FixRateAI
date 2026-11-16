"""Business state verification; no model or successful endpoint is mocked into existence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import asyncio
import json

import pytest

from app.assistant.action_outcomes import verify_postcondition, verify_action, mark_interrupted_actions

EQUIPMENT, SYSTEM, TASK, EXECUTION, CHECK, WORKER = [str(uuid4()) for _ in range(6)]
WHEN = '2026-01-01T10:00:00+00:00'


def equipment():
    return dict(equipment_id=EQUIPMENT, system_id=SYSTEM, equipment_type_id=None,
                parent_equipment_id=None, asset_code='OUTCOME-01', name='Initial equipment',
                serial_number=None, commissioned_on=None, location='Room', status='active',
                properties={'data_origin': 'synthetic_demo', 'calibration': 'preserve'}, revision=3)


def bundle(state='in_progress', revision=4):
    return dict(task=dict(id=TASK, state=state, revision=revision, activeExecutionId=EXECUTION,
                         assignees=[dict(executorId=WORKER)], scheduledStart=WHEN,
                         scheduledEnd='2026-01-01T11:00:00+00:00'),
                execution=dict(id=EXECUTION, taskId=TASK, state='draft', narrative='Recorded fact',
                    checklist=[dict(id=CHECK, answer='done')], photos=[], readings=[], actual={}),
                decision=None)


def command(**fields):
    return dict(path=dict(task_id=TASK), body=dict(expected_revision=3, **fields))


def outcome(name, args, value, before=None, after=None):
    return verify_postcondition(name, args, value, before, value if after is None else after)


def test_equipment_edit_requires_requested_change_and_preserves_omitted_fields():
    before=equipment();after=dict(before, name='Requested name', revision=4)
    args=dict(path=dict(equipment_id=EQUIPMENT), body=dict(expected_revision=3,name='Requested name'))
    result=outcome('equipment_edit',args,after,before)
    assert result['status']=='confirmed'
    assert set(result['evidence'])=={'before_sha256','receipt_sha256','after_sha256','checks_sha256'}
    assert 'Requested name' not in json.dumps(result)
    assert outcome('equipment_edit',args,dict(after,location=None),before)['status']=='failed'
    assert outcome('equipment_edit',args,dict(after,name='Other name'),before)['status']=='failed'


def test_equipment_create_checks_effective_defaults_and_returned_resource_identity():
    args=dict(body=dict(system_id=SYSTEM,asset_code='CREATED',name='Created',data_origin='synthetic_demo'))
    after=dict(equipment(), asset_code='CREATED',name='Created',location=None,
               properties={'data_origin':'synthetic_demo'},revision=1)
    assert outcome('equipment_create',args,after)['status']=='confirmed'
    assert outcome('equipment_create',args,dict(after,system_id=str(uuid4())))['status']=='failed'
    assert outcome('equipment_create',args,dict(after,equipment_id='fake'))['status']=='unverified'


def test_equipment_properties_and_data_origin_follow_patch_semantics():
    before=equipment();args=dict(path=dict(equipment_id=EQUIPMENT),body=dict(expected_revision=3,data_origin='customer'))
    after=dict(before,revision=4,properties=dict(before['properties'],data_origin='customer'))
    assert outcome('equipment_edit',args,after,before)['status']=='confirmed'
    args['body']=dict(expected_revision=3,properties={'new':True})
    after['properties']={'new':True,'data_origin':'synthetic_demo'}
    assert outcome('equipment_edit',args,after,before)['status']=='confirmed'


@pytest.mark.parametrize('receipt,after,reason',[
    ({'ok':True},{'ok':True},'receipt_identity_missing_or_mismatched'),
    (None,{},'readback_or_receipt_missing'),
    ({'task':None},{'task':None},'receipt_identity_missing_or_mismatched'),
    ({'data':{'data':{'data':{}}}},{},'readback_or_receipt_missing'),
])
def test_success_shaped_or_malformed_results_never_confirm(receipt,after,reason):
    result=verify_postcondition('task_start',command(),receipt,after=after)
    assert result['status']=='unverified' and result['reason']==reason


@pytest.mark.parametrize('name',['unsupported','publication_publish','photo_review','forecast_run'])
def test_unknown_postconditions_remain_unverified_even_with_success_flag(name):
    result=outcome(name,command(),dict(status='succeeded',data={'ok':True}))
    assert result['status']=='unverified' and result['reason']=='unsupported_postcondition'


def test_nested_assistant_result_envelopes_are_verified_but_arbitrary_nested_data_is_not():
    after=bundle();args=command()
    wrapped={'data':{'data':after,'navigate_to':'/assistant'},'verification':{'status':'confirmed'}}
    assert verify_postcondition('task_start',args,wrapped,after=after)['status']=='confirmed'
    assert verify_postcondition('task_start',args,{'answer':'saved','data':after},after=after)['status']=='unverified'


@pytest.mark.parametrize('field,value,reason',[
    ('revision',5,'receipt_revision_mismatch'),('revision',True,'receipt_revision_mismatch'),
    ('id',str(uuid4()),'receipt_identity_missing_or_mismatched')])
def test_task_receipt_identity_and_revision_are_not_inferred(field,value,reason):
    after=bundle();after['task'][field]=value
    result=outcome('task_start',command(),after)
    assert result['status']=='unverified' and result['reason']==reason


def test_newer_readback_does_not_falsely_claim_failure_or_success():
    receipt=bundle();after=deepcopy(receipt);after['task'].update(revision=5,state='submitted')
    result=verify_postcondition('task_start',command(),receipt,after=after)
    assert result['status']=='unverified' and result['reason']=='readback_revision_changed'


def test_start_checks_new_report_identity_and_draft_state():
    before=bundle('assigned',3);before['execution']=None;before['task']['activeExecutionId']=None
    after=bundle()
    assert outcome('task_start',command(),after,before)['status']=='confirmed'
    assert outcome('task_start',command(),after,bundle('rework_required',3))['status']=='failed'
    after['execution']['taskId']=str(uuid4())
    assert outcome('task_start',command(),after,before)['status']=='failed'


@pytest.mark.parametrize('verdict,state',[('accepted','accepted'),('rejected','rework_required')])
def test_report_review_verifies_the_specific_execution_decision_and_state(verdict,state):
    after=bundle(state);after['execution']['state']='submitted'
    after['decision']=dict(id=str(uuid4()),taskId=TASK,executionId=EXECUTION,
                           verdict=verdict,reason='Inspected',decidedAt=WHEN)
    args=command(execution_id=EXECUTION,verdict=verdict,reason=' Inspected ')
    assert outcome('report_review',args,after)['status']=='confirmed'
    after['decision']['executionId']=str(uuid4())
    assert outcome('report_review',args,after)['status']=='failed'


def test_report_submit_preserves_facts_and_requires_submission_timestamp():
    before=bundle(revision=3);after=bundle('submitted');after['execution'].update(state='submitted',submittedAt=WHEN)
    assert outcome('report_submit',command(),after,before)['status']=='confirmed'
    after['execution']['narrative']='Fabricated replacement'
    assert outcome('report_submit',command(),after,before)['status']=='failed'
    after['execution']['narrative']=before['execution']['narrative'];after['execution']['submittedAt']=None
    assert outcome('report_submit',command(),after,before)['status']=='failed'


def test_report_save_checks_answers_narrative_actual_and_readings_in_server_formats():
    before=bundle(revision=3);after=bundle()
    reading=dict(equipment_id=EQUIPMENT,parameter_code='pressure',value='1.000000',unit='bar',measured_at=WHEN,phase='after')
    after['execution'].update(narrative='Saved facts',readings=[reading],
        actual=dict(started_at=WHEN,performed_at='2026-01-01T11:00:00Z',person_hours='2.000'))
    args=command(narrative='Saved facts',answers={CHECK:'done'},readings=[dict(reading,value='1')],
        actual=dict(started_at=WHEN,performed_at='2026-01-01T11:00:00+00:00',person_hours='2'))
    assert outcome('report_save',args,after,before)['status']=='confirmed'
    after['execution']['readings'][0]['value']='9'
    assert outcome('report_save',args,after,before)['status']=='failed'


def test_report_save_does_not_silently_erase_unsupplied_answers_or_photos():
    before=bundle(revision=3);other=str(uuid4());before['execution']['checklist'].append(dict(id=other,answer='kept'))
    after=deepcopy(before);after['task']['revision']=4
    args=command(narrative='Recorded fact',answers={CHECK:'done'})
    assert outcome('report_save',args,after,before)['status']=='confirmed'
    after['execution']['checklist'][1]['answer']=None
    assert outcome('report_save',args,after,before)['status']=='failed'


def test_task_assignment_verifies_full_workers_and_equivalent_timezones():
    after=bundle('assigned')
    args=command(executor_ids=[WORKER],start_at='2026-01-01T15:00:00+05:00',end_at='2026-01-01T16:00:00+05:00')
    assert outcome('task_assign',args,after)['status']=='confirmed'
    after['task']['assignees'].append(dict(executorId=str(uuid4())))
    assert outcome('task_assign',args,after)['status']=='failed'


def test_task_cancel_checks_released_assignments():
    after=bundle('cancelled');after['task']['assignees']=[]
    assert outcome('task_cancel',command(reason='Requested cancellation'),after)['status']=='confirmed'
    after['task']['assignees']=[dict(executorId=WORKER)]
    assert outcome('task_cancel',command(reason='Requested cancellation'),after)['status']=='failed'


def test_diagnostics_do_not_leak_any_command_or_response_text():
    secret='PRIVATE PASSWORD SENTINEL'
    args=command(password=secret,api_key=secret,narrative=secret,answers={})
    value={'task':{'id':TASK,'revision':4,'state':{'password':secret}},'execution':{'narrative':secret},'api_key':secret}
    result=outcome('report_save',args,value)
    assert result['status']!='confirmed'
    assert secret not in json.dumps(result)
    assert 'password' not in json.dumps(result)


def test_verify_action_reads_authorized_resource_and_handles_readback_failure(monkeypatch):
    from app.assistant import tools
    after=bundle();calls=[]
    monkeypatch.setattr(tools,'validate_arguments',lambda app,tool,args:args)
    async def read(app,tool,args,headers):
        calls.append((tool.name,args,headers));return after
    monkeypatch.setattr(tools,'invoke',read)
    result=asyncio.run(verify_action(None,SimpleNamespace(name='task_start'),command(),after,{'cookie':'private'}))
    assert result['status']=='confirmed'
    assert calls==[('task_read',{'path':{'task_id':TASK}},{'cookie':'private'})]
    async def denied(*args):raise RuntimeError('DO NOT EXPOSE SECRET')
    monkeypatch.setattr(tools,'invoke',denied)
    result=asyncio.run(verify_action(None,SimpleNamespace(name='task_start'),command(),after,{}))
    assert result['status']=='unverified' and result['reason']=='authorized_readback_failed'
    assert 'SECRET' not in json.dumps(result)


def test_verify_unknown_action_does_not_invoke_anything(monkeypatch):
    from app.assistant import tools
    async def forbidden(*args):pytest.fail('Unknown verification must not invoke any tool')
    monkeypatch.setattr(tools,'invoke',forbidden)
    result=asyncio.run(verify_action(None,SimpleNamespace(name='unknown'),command(),{},{}))
    assert result['status']=='unverified'


def test_interrupted_dispatch_helper_only_claims_stale_executing_in_one_conversation():
    class Session:
        def execute(self,sql,values):
            self.sql,self.values=str(sql),values
            return SimpleNamespace(rowcount=2)
    session=Session();conversation=str(uuid4());cutoff=datetime.now(timezone.utc)-timedelta(minutes=3)
    assert mark_interrupted_actions(session,conversation_id=conversation,cutoff=cutoff)==2
    assert "status='executing'" in session.sql and "started_at<:cutoff" in session.sql
    assert 'conversation_id=:conversation' in session.sql and session.values['conversation']==conversation
    assert json.loads(session.values['result'])['verification']['status']=='unverified'
    with pytest.raises(ValueError):mark_interrupted_actions(session,conversation_id=conversation,cutoff=datetime.now())
    with pytest.raises(ValueError):mark_interrupted_actions(session,conversation_id='foreign',cutoff=cutoff)
