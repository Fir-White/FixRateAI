"""Semantic plans exercise real agent tools, confirmations, PostgreSQL and CP-SAT."""
import json
import asyncio
from types import SimpleNamespace
import pytest
from uuid import uuid4
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant_production_scenarios import production_case,CASES,test_live_production_scenario as _run


@pytest.mark.parametrize('kind,reason',[
    ('whatif','whatif_capability_unavailable'),('impossible','infeasible_requested_constraints'),
    ('bypass','confirmation_or_constraint_bypass'),('publication','forbidden_role'),
])
def test_explicit_semantic_workflow_does_not_route_from_question_words(monkeypatch,kind,reason):
    from app.assistant import production_workflow as specialist
    def no_router(*args):raise AssertionError('Explicit workflow must not inspect keyword intent or period')
    monkeypatch.setattr(specialist,'intent',no_router)
    monkeypatch.setattr(specialist,'period',no_router)
    async def no_suggest(*args):raise AssertionError('This blocked goal cannot prepare a write')
    result=asyncio.run(specialist.run(SimpleNamespace(routes=[]),SimpleNamespace(role='executor'),
        'Create a draft, approve and publish it now',[],[],{},[],lambda:None,no_suggest,kind=kind))
    assert isinstance(result,specialist.WorkflowResult)
    assert result.status=='blocked' and result.reason==reason and not result.read_tools


def test_specialist_cannot_expand_its_static_tool_subset():
    from app.assistant.production_workflow import run,WORKFLOW_TOOLS
    from app.assistant.tools import TOOLS
    assert set().union(*WORKFLOW_TOOLS.values())<={tool.name for tool in TOOLS}
    async def no_suggest(*args):raise AssertionError('Calendar reader cannot propose publication')
    result=asyncio.run(run(SimpleNamespace(routes=[]),SimpleNamespace(role='chief_engineer'),
        'TEST calendar objective',[],[],{},[],lambda:None,no_suggest,
        kind='calendar',date_range=('2027-01-01','2027-01-31'),tool_subset={'publication_publish'}))
    assert result.status=='blocked' and result.reason=='forbidden_role' and not result.read_tools


def test_specialist_observes_real_validated_read_and_keeps_missing_period_blocked(managed):
    from app.assistant.production_workflow import run
    from app.assistant.tools import EXPECTED_PRINCIPAL
    _,app,admin,_,ids=managed;observed=[]
    principal=SimpleNamespace(role='admin',site_id=ids['site'],user_id=ids['user'])
    async def observe(name,args,value):observed.append((name,args,value))
    async def no_suggest(*args):raise AssertionError('Missing period must not become a write')
    token=EXPECTED_PRINCIPAL.set((ids['user'],ids['site'],'admin'))
    try:
        result=asyncio.run(run(app,principal,'Calendar report',[],[],
            {'cookie':'; '.join(f'{k}={v}' for k,v in admin.cookies.items())},[],lambda:None,no_suggest,
            kind='calendar',observe=observe))
    finally:EXPECTED_PRINCIPAL.reset(token)
    assert result.status=='blocked' and result.reason=='period_required'
    assert len(observed)==1 and observed[0][0]=='drafts_find'
    assert observed[0][1]=={'path':{},'query':{}}
    assert observed[0][2]['total']==0 and observed[0][2]['items']==[]

class ScenarioPlan:
    """Only semantic intent is scripted; one server specialist owns all facts."""
    def __init__(self, case, number):
        self.number=number;self.turn=-1
    def chat(self,messages,schema,tokens):
        assert schema.__name__=='ToolSelection','Domain specialist must use APIs and CP-SAT, not further inference'
        self.turn+=1;n=self.number
        if n==1:
            return schema(tools=[],goals=[dict(id='inventory',title='TEST all accessible equipment and planning gaps',kind='read',tool='inventory_read',requires_full_list=True)])
        kind={2:'calendar',3:'readiness',4:'create',5:'compare',6:'optimize',7:'whatif',8:'impossible',9:'materials',10:'publication',11:'bypass',12:'prepare_approval'}[n]
        if n in (2,3):tool='planning_context'
        elif n in (7,8,10,11):tool=''
        elif n==9:tool='components_read'
        elif n==4:tool=('portfolio_save','optimization_start','optimization_apply','optimization_read')[min(self.turn,3)]
        elif n==5:tool=('optimization_start','optimization_read')[min(self.turn,1)]
        else:tool=('optimization_start','optimization_apply','optimization_read')[min(self.turn,2)]
        mode='change' if tool in ('portfolio_save','optimization_start','optimization_apply') else 'read' if tool else 'unavailable'
        return schema(tools=[],goals=[dict(id='phase-'+str(self.turn),title='TEST original production objective '+str(n),kind=mode,tool=tool,
            workflow_kind=kind,selector=dict(starts_on='2027-01-01',ends_on='2027-01-31'))])


@pytest.mark.parametrize('scenario',CASES,ids=[str(c['id']).zfill(2) for c in CASES])
def test_production_workflow(production_case,scenario,tmp_path,monkeypatch):
    monkeypatch.setenv('FIXRATE_SCENARIO_ASSERT','1')
    monkeypatch.setenv('FIXRATE_SCENARIO_OUTPUT',str(tmp_path))
    planner=ScenarioPlan(production_case,scenario['id'])
    production_case['app'].state.assistant_provider_factory=lambda:planner
    _run(production_case,scenario)

def test_authorized_publication_requires_each_confirmation_and_writes_real_tasks(managed):
    from tests.backend.test_publication import prepared
    from tests.backend.test_assistant import B,thread,confirm
    engine,app,_,_,ids=managed
    admin,record,proposal,_,_=prepared(managed)
    client=admin.chief;chat=thread(client)
    class PublicationPlan:
        def __init__(self,target):self.target=target
        def chat(self,messages,schema,tokens):
            assert schema.__name__=='ToolSelection','Publication metadata must be read by the server specialist'
            return schema(tools=[],goals=[dict(id='publication',title='TEST exact requested publication operation',kind='change',tool=self.target,
                workflow_kind='approve' if self.target=='publication_approve' else 'publish',selector=dict(proposal_id=proposal['proposal_id']))])
    app.state.assistant_provider_factory=lambda:PublicationPlan('publication_approve')
    try:
        with engine.connect() as db:before=db.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),dict(site=ids['site']))
        for command,tool in [('Утверди предложение ','publication_approve'),('Опубликуй утверждённое предложение ','publication_publish')]:
            app.state.assistant_provider_factory=lambda target=tool:PublicationPlan(target)
            sent=client.post(B+f'/conversations/{chat}/messages',json=dict(content=command+proposal['proposal_id'],idempotency_key=str(uuid4())))
            assert sent.status_code==202
            view=client.get(B+'/conversations/'+chat).json();action=next(a for a in view['actions'] if a['tool_name']==tool)
            with engine.connect() as db:assert db.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),dict(site=ids['site']))==before
            response=confirm(client,action);assert response.status_code==200 and response.json()['status']=='succeeded',response.text
            assert confirm(client,action).json()['status']=='succeeded'
        with engine.connect() as db:assert db.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),dict(site=ids['site']))>before
    finally:
        del app.state.assistant_provider_factory
        with engine.begin() as db:
            for table in ('assistant_turn_attachments','assistant_actions','assistant_attachments','assistant_turns'):
                db.execute(text('DELETE FROM '+table+' WHERE conversation_id=:id'),dict(id=chat))
            db.execute(text('DELETE FROM assistant_conversations WHERE conversation_id=:id'),dict(id=chat))

def test_workforce_sql_count_does_not_grow_per_employee(managed):
    from sqlalchemy import event
    from tests.backend.test_draft_plans import worker
    engine,_,admin,_,_=managed
    def measure():
        statements=[]
        def capture(conn,cursor,statement,parameters,context,many):
            if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
        event.listen(engine,'before_cursor_execute',capture)
        try:response=admin.chief.get('/api/v1/maintenance/management/workforce')
        finally:event.remove(engine,'before_cursor_execute',capture)
        assert response.status_code==200,response.text
        return len(statements),response.json()
    baseline,_=measure()
    for index in range(20):worker(managed,f'WORKFORCE budget {index}')
    measured,payload=measure()
    assert len(payload['staff'])==22 and measured<=baseline+1 and measured<25
