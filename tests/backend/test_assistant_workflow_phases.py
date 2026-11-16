"""Phase persistence/security with actual proposals, portfolio API and PostgreSQL.

The specialist is deliberately narrower than the production CP-SAT workflow:
save one real portfolio, then verify its persisted record with draft_read.
Only phase selection is substituted. This suite does not claim to exercise the
optimizer; production workflow suites cover the actual solver separately.
"""
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.assistant.tools import validate_arguments, invoke
from app.assistant.production_workflow import WorkflowResult
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case, thread, B, confirm
from tests.backend.test_requirements import setup_rule
from tests.backend.test_portfolio_plans import request_for, PATH as PORTFOLIOS


class Plan:
    def __init__(self,goals):self.goals=goals;self.other_calls=0
    def chat(self,messages,schema,tokens):
        if schema.__name__=='ToolSelection':return schema(tools=[],goals=self.goals)
        self.other_calls+=1
        raise AssertionError('TEST ONLY: blocked evidence must not invoke a conversational/executor model')
    def text(self,*args):
        self.other_calls+=1
        raise AssertionError('TEST ONLY: unverified evidence cannot be satisfied by prose')


def macro(identity='macro',title='TEST macro',**extra):
    return {'id':identity,'title':title,'tool':'portfolio_save','kind':'change','workflow_kind':'create',
            'required_evidence':'saved_data',**extra}


def send(client,chat,*,resume=None,content='TEST ONLY save a portfolio and verify its actual record',key=None):
    body=dict(content=content,idempotency_key=key or str(uuid4()))
    if resume:body['resume_turn_id']=resume
    response=client.post(B+f'/conversations/{chat}/messages',json=body)
    assert response.status_code==202,response.text
    return response.json()['turn_id']


def view(client,chat):
    response=client.get(B+'/conversations/'+chat)
    assert response.status_code==200,response.text
    return response.json()


@pytest.fixture
def phases(assistant_case,monkeypatch):
    from app.assistant import production_workflow
    engine,app,client,_,ids=assistant_case
    setup_rule(assistant_case)
    request=request_for()
    preview=client.post(PORTFOLIOS+'/preview',json=request)
    assert preview.status_code==200 and preview.json()['can_save'],preview.text
    commands={};outcomes_seen={};final_reads=[];macro_calls=[]
    def command(title):
        if title not in commands:
            commands[title]=dict(input=deepcopy(request),preview_sha256=preview.json()['input_sha256'],
                idempotency_key=str(uuid4()),title=title,reason='TEST ONLY separately reviewed phase')
        return commands[title]
    async def specialist(app,principal,question,history,outcomes,headers,trace,check,suggest,*,
                         kind,date_range=None,tool_subset=None,observe=None):
        assert kind=='create'
        question=question.strip()
        macro_calls.append(question)
        outcomes_seen.setdefault(question,[]).append(deepcopy(outcomes))
        saved=next((row for row in outcomes if row['tool_name']=='portfolio_save' and row['status']=='succeeded'),None)
        if saved:
            record=saved['result']['data']
            tool=tool_subset['draft_read']
            # The test objective is persistence of this record, not schedule
            # feasibility. Read the actual API's metadata projection rather
            # than treating an incomplete scheduling validation as success.
            checked=validate_arguments(app,tool,dict(path=dict(identity=record['draft_id']),view=dict(path=['record'])))
            check()
            actual=await invoke(app,tool,checked,headers)
            assert actual['draft_id']==record['draft_id']
            assert actual['revision']==record['revision']
            final_reads.append(record['draft_id'])
            if observe:observe('draft_read',checked,actual)
            return WorkflowResult('TEST ONLY saved portfolio verified by fresh authorized API','completed')
        proposal=await suggest(tool_subset['portfolio_save'],dict(body=command(question)),
                               'TEST ONLY save this portfolio after explicit confirmation')
        return WorkflowResult('TEST ONLY proposal pending','awaiting_confirmation','human_confirmation_required',str(proposal['action_id']))
    monkeypatch.setattr(production_workflow,'run',specialist)
    result=dict(engine=engine,app=app,client=client,ids=ids,outcomes=outcomes_seen,final_reads=final_reads,
                macro_calls=macro_calls,command=command)
    yield result
    if hasattr(app.state,'assistant_provider_factory'):del app.state.assistant_provider_factory


def count_drafts(case):
    with case['engine'].connect() as db:
        return db.scalar(text('SELECT count(DISTINCT draft_id) FROM planning_draft_versions WHERE site_id=:site'),dict(site=case['ids']['site']))


def test_confirmation_does_not_complete_macro_before_fresh_final_api_read(phases):
    case=phases;client=case['client'];chat=thread(client)
    case['app'].state.assistant_provider_factory=lambda:Plan([macro()])
    root=send(client,chat)
    initial=view(client,chat);assert len(initial['actions'])==1 and count_drafts(case)==0
    action=initial['actions'][0]
    assert action['workflow_goal_id']=='macro::portfolio_save'
    applied=confirm(client,action)
    assert applied.status_code==200 and applied.json()['status']=='succeeded',applied.text
    assert count_drafts(case)==1 and case['final_reads']==[]
    pending=view(client,chat)['turns'][-1]['workflow']
    assert pending['outcome']!='completed' and pending['goals'][0]['status']!='completed'
    send(client,chat,resume=root)
    final=view(client,chat)
    assert final['turns'][-1]['workflow']['outcome']=='completed'
    assert len(case['final_reads'])==1 and len(final['actions'])==1 and count_drafts(case)==1
    response=client.post(B+f'/conversations/{chat}/messages',json=dict(content='TEST continue old parent',
        idempotency_key=str(uuid4()),resume_turn_id=root))
    assert response.status_code==409,response.text


def test_lost_phase_checkpoint_recovers_existing_proposal_without_replay(phases,monkeypatch):
    from app.assistant import service
    case=phases;client=case['client'];chat=thread(client)
    case['app'].state.assistant_provider_factory=lambda:Plan([macro()])
    original=service.propose;crashed=[False]
    async def lost(*args,**kwargs):
        action=await original(*args,**kwargs)
        if not crashed[0]:
            crashed[0]=True
            raise RuntimeError('TEST ONLY worker lost after real phase proposal commit')
        return action
    monkeypatch.setattr(service,'propose',lost)
    root=send(client,chat)
    for _ in range(2):send(client,chat,resume=root)
    saved=view(client,chat)
    assert len(saved['actions'])==1 and count_drafts(case)==0
    assert saved['turns'][-1]['workflow']['goals'][0]['pending_action_id']==saved['actions'][0]['action_id']
    assert saved['turns'][-1]['workflow']['outcome']=='awaiting_confirmation'
    assert len(case['macro_calls'])==1
    assert confirm(client,saved['actions'][0]).json()['status']=='succeeded'
    send(client,chat,resume=root)
    final=view(client,chat)
    assert final['turns'][-1]['workflow']['outcome']=='completed',final
    assert count_drafts(case)==1


@pytest.mark.parametrize('status',['rejected','stale','failed'])
def test_terminal_unsuccessful_phase_cannot_be_recreated_on_resume(phases,status):
    case=phases;client=case['client'];chat=thread(client)
    case['app'].state.assistant_provider_factory=lambda:Plan([macro()])
    root=send(client,chat);action=view(client,chat)['actions'][0]
    with case['engine'].begin() as db:
        db.execute(text('UPDATE assistant_actions SET status=:status,finished_at=now() WHERE action_id=:id'),dict(status=status,id=action['action_id']))
    for _ in range(2):send(client,chat,resume=root)
    saved=view(client,chat)
    assert len(saved['actions'])==1 and len(case['macro_calls'])==1 and count_drafts(case)==0
    assert saved['turns'][-1]['workflow']['goals'][0]['reason']=='action_'+status
    assert confirm(client,action).json()['status']==status


def test_committed_phase_with_lost_response_is_uncertain_and_never_replayed(phases,monkeypatch):
    from app.assistant import service
    case=phases;client=case['client'];chat=thread(client)
    case['app'].state.assistant_provider_factory=lambda:Plan([macro()])
    root=send(client,chat);action=view(client,chat)['actions'][0]
    original=service.invoke;dispatches=[]
    async def commit_then_lose(app,tool,args,headers):
        value=await original(app,tool,args,headers)
        if tool.name=='portfolio_save':
            dispatches.append(1)
            raise HTTPException(502,'TEST ONLY response lost after committed portfolio save')
        return value
    monkeypatch.setattr(service,'invoke',commit_then_lose)
    for _ in range(3):assert confirm(client,action).json()['status']=='uncertain'
    for _ in range(2):send(client,chat,resume=root)
    saved=view(client,chat)
    assert dispatches==[1] and count_drafts(case)==1 and len(saved['actions'])==1
    assert saved['turns'][-1]['workflow']['goals'][0]['status']=='uncertain'
    assert saved['turns'][-1]['workflow']['outcome']!='completed' and case['final_reads']==[]


def test_distinct_goal_ids_with_underscore_cannot_consume_each_others_phase_outcomes(phases):
    case=phases;client=case['client'];chat=thread(client)
    case['app'].state.assistant_provider_factory=lambda:Plan([
        macro('macroXa','FIRST'),macro('macro_a','SECOND')])
    send(client,chat)
    saved=view(client,chat)
    assert len(saved['actions'])==2 and count_drafts(case)==0
    assert {action['workflow_goal_id'] for action in saved['actions']}=={'macroXa::portfolio_save','macro_a::portfolio_save'}
    assert case['outcomes']['FIRST'][0]==[]
    assert case['outcomes']['SECOND'][0]==[]


def test_unrelated_conversation_phase_outcomes_are_not_reused(phases):
    case=phases;client=case['client'];left,right=thread(client),thread(client)
    case['app'].state.assistant_provider_factory=lambda:Plan([macro('shared','LEFT')])
    root=send(client,left);left_action=view(client,left)['actions'][0]
    case['app'].state.assistant_provider_factory=lambda:Plan([macro('shared','RIGHT')])
    send(client,right);right_action=view(client,right)['actions'][0]
    left_result=confirm(client,left_action).json()['result']['data']
    right_result=confirm(client,right_action).json()['result']['data']
    send(client,left,resume=root)
    assert case['final_reads']==[left_result['draft_id']]
    assert left_result['draft_id']!=right_result['draft_id']
    assert len(case['outcomes']['LEFT'][-1])==1
    assert case['outcomes']['LEFT'][-1][0]['result']['data']['draft_id']==left_result['draft_id']
    assert count_drafts(case)==2


@pytest.mark.parametrize('required',['manufacturer_document','user_decision','optimizer_result','saved_data','file_content','calendar_calculation'])
def test_required_evidence_cannot_be_satisfied_by_conversation_prose(assistant_case,required):
    _,app,client,_,_=assistant_case;chat=thread(client)
    planner=Plan([dict(id='proof',title='TEST verify required primary evidence',tool='',kind='conversation',required_evidence=required)])
    app.state.assistant_provider_factory=lambda:planner
    try:
        send(client,chat,content='TEST ONLY verify the required primary source')
        saved=view(client,chat)
        assert saved['turns'][-1]['workflow']['goals'][0]['status']=='blocked'
        assert saved['turns'][-1]['workflow']['outcome']!='completed' and planner.other_calls==0
    finally:del app.state.assistant_provider_factory


@pytest.mark.parametrize('required',['manufacturer_document','user_decision'])
def test_resume_preserves_required_evidence_blockers_before_macro_phases(phases,required):
    case=phases;client=case['client'];chat=thread(client)
    case['app'].state.assistant_provider_factory=lambda:Plan([macro(required_evidence=required)])
    root=send(client,chat)
    assert view(client,chat)['actions']==[] and case['macro_calls']==[]
    send(client,chat,resume=root)
    saved=view(client,chat)
    assert saved['actions']==[] and case['macro_calls']==[] and count_drafts(case)==0
    assert saved['turns'][-1]['workflow']['goals'][0]['status']=='blocked'


@pytest.mark.parametrize('required',['manufacturer_document','user_decision'])
@pytest.mark.parametrize('goal_kind',['change','read'])
def test_explicit_binding_preserves_source_gate_before_proposal_and_resume(assistant_case,required,goal_kind):
    from tests.backend.test_management import equipment
    engine,app,client,_,ids=assistant_case;asset=equipment(client,ids);chat=thread(client)
    tool='equipment_edit' if goal_kind=='change' else 'equipment_read'
    goal=dict(id='source',title='Проверить обязательный первичный источник',tool=tool,kind=goal_kind,
              required_evidence=required,selector=dict(equipment_id=asset['equipment_id']))
    if goal_kind=='change':goal['changes']=dict(name='Насос с проверенным основанием')
    planner=Plan([goal]);app.state.assistant_provider_factory=lambda:planner
    question=f'Проверь рекомендацию производителя. Затем переименуй оборудование equipment_id={asset["equipment_id"]} в «Насос с проверенным основанием». Остальные поля не меняй.'
    try:
        root=send(client,chat,content=question)
        for resumed in (False,True):
            if resumed:send(client,chat,resume=root)
            saved=view(client,chat);workflow=saved['turns'][-1]['workflow']
            assert saved['actions']==[] and len(workflow['goals'])==1
            assert workflow['goals'][0]['required_evidence']==required
            assert workflow['goals'][0]['status']=='blocked' and workflow['outcome']=='blocked'
            assert planner.other_calls==0
            current=client.get('/api/v1/maintenance/equipment/'+asset['equipment_id']).json()
            assert (current['name'],current['revision'])==(asset['name'],asset['revision'])
        with engine.connect() as db:
            assert db.scalar(text('SELECT count(*) FROM assistant_actions WHERE conversation_id=:chat'),dict(chat=chat))==0
    finally:del app.state.assistant_provider_factory


def test_read_goal_with_explicit_patch_is_normalized_to_real_confirmed_mutation(assistant_case):
    from tests.backend.test_management import equipment
    _,app,client,_,ids=assistant_case;asset=equipment(client,ids);chat=thread(client)
    app.state.assistant_provider_factory=lambda:Plan([dict(id='patch',title='TEST update requested equipment location',
        tool='equipment_read',kind='read',selector=dict(equipment_id=asset['equipment_id']),changes=dict(location='Reviewed room'))])
    try:
        send(client,chat,content=f"Измени расположение оборудования equipment_id={asset['equipment_id']} на «Reviewed room».")
        saved=view(client,chat)
        assert len(saved['actions'])==1 and saved['actions'][0]['tool_name']=='equipment_edit'
        assert saved['turns'][-1]['workflow']['outcome']=='awaiting_confirmation'
        action=saved['actions'][0]
        assert set(action['arguments']['body'])=={'expected_revision','location'}
        assert confirm(client,action).json()['result']['verification']['status']=='confirmed'
        current=client.get('/api/v1/maintenance/equipment/'+asset['equipment_id']).json()
        assert current['name']==asset['name'] and current['location']=='Reviewed room' and current['revision']==2
    finally:del app.state.assistant_provider_factory


@pytest.mark.parametrize('kind',['approve','publish'])
def test_real_publication_phase_completes_only_after_fresh_postcondition_read(assistant_case,kind):
    from tests.backend.test_publication import prepared,approve,PATH as PUBLICATIONS
    engine,app,_,_,ids=assistant_case
    admin,_,proposal,_,_=prepared(assistant_case)
    if kind=='publish':proposal=approve(admin,proposal)
    client=admin.chief;chat=thread(client)
    name='publication_approve' if kind=='approve' else 'publication_publish'
    app.state.assistant_provider_factory=lambda:Plan([dict(id='publication',title='TEST exact selected publication phase',
        tool=name,kind='change',workflow_kind=kind,required_evidence='saved_data',selector=dict(proposal_id=proposal['proposal_id']))])
    def counts():
        with engine.connect() as db:
            domain=tuple(db.scalar(text('SELECT count(*) FROM '+table+' WHERE site_id=:site'),dict(site=ids['site']))
                         for table in ('work_orders','draft_publications'))
            actions=db.scalar(text('SELECT count(*) FROM assistant_actions WHERE conversation_id=:chat'),dict(chat=chat))
            return (*domain,actions)
    try:
        before=counts()
        root=send(client,chat,content='TEST ONLY '+kind+' exact proposal '+proposal['proposal_id'])
        pending=view(client,chat)
        assert len(pending['actions'])==1 and counts()[:2]==before[:2]
        action=pending['actions'][0]
        assert action['workflow_goal_id']=='publication::'+name
        result=confirm(client,action)
        assert result.status_code==200 and result.json()['status']=='succeeded',result.text
        expected_state='approved' if kind=='approve' else 'published'
        receipt=result.json()['result']['data']
        assert receipt['state']==expected_state and receipt['proposal_id']==proposal['proposal_id']
        after=counts()
        assert after[2]==before[2]+1
        if kind=='publish':
            assert after[0]==before[0]+proposal['summary']['added_tasks'] and after[1]==before[1]+1
        else:assert after[:2]==before[:2]
        unresolved=view(client,chat)['turns'][-1]['workflow']
        assert unresolved['goals'][0]['status']=='planned' and unresolved['outcome']!='completed'
        from app.assistant.production_workflow import _publication_verified
        current=client.get(PUBLICATIONS+proposal['proposal_id']).json()
        assert _publication_verified(kind,proposal['proposal_id'],receipt,current) is True
        child=send(client,chat,resume=root)
        with engine.connect() as db:
            persisted=db.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'),dict(id=child))
        diagnostic=dict(goal_status=persisted['goals'][0]['status'],reason=persisted['goals'][0].get('reason'),
            response=persisted['goals'][0].get('response'),
            proofs=[{key:proof.get(key) for key in ('tool','complete','retained','evidence_kind','limitations')} for proof in persisted['evidence']])
        assert persisted['outcome']=='completed',diagnostic
        final=view(client,chat)
        assert final['turns'][-1]['workflow']['outcome']=='completed',final
        with engine.connect() as db:
            state=db.scalar(text('SELECT workflow FROM assistant_turns WHERE turn_id=:id'),dict(id=final['turns'][-1]['turn_id']))
        reads=[proof for proof in state['evidence'] if proof['tool']=='publication_read']
        assert reads and reads[-1]['result']['proposal_id']==proposal['proposal_id']
        assert reads[-1]['result']['state']==expected_state
        assert reads[-1]['result']['proposal_digest']==receipt['proposal_digest']
        assert client.get(PUBLICATIONS+proposal['proposal_id']).json()['state']==expected_state
        assert confirm(client,action).json()['status']=='succeeded' and counts()==after
        replay=client.post(B+f'/conversations/{chat}/messages',json=dict(content='TEST continue old root',
            idempotency_key=str(uuid4()),resume_turn_id=root))
        assert replay.status_code==409 and counts()==after
    finally:del app.state.assistant_provider_factory


@pytest.mark.parametrize('field',['proposal_id','proposal_digest','draft_id','base_revision','decided_by','decided_at','approval_token','publication_id','published_at'])
def test_publication_receipt_must_match_exact_resource_and_transition_facts(field):
    from app.assistant.production_workflow import _publication_verified
    identity=str(uuid4())
    receipt=dict(proposal_id=identity,proposal_digest='a'*64,draft_id=str(uuid4()),base_revision=2,
        state='published',decided_by=str(uuid4()),decided_at='2026-01-01T10:00:00+00:00',
        approval_token=str(uuid4()),publication_id=str(uuid4()),published_at='2026-01-01T11:00:00+00:00')
    assert _publication_verified('publish',identity,receipt,deepcopy(receipt)) is True
    changed=deepcopy(receipt)
    changed[field]=3 if field=='base_revision' else 'b'*64 if field=='proposal_digest' else (
        '2026-01-02T10:00:00+00:00' if field.endswith('_at') else str(uuid4()))
    assert _publication_verified('publish',identity,receipt,changed) is False
