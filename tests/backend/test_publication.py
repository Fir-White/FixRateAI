"""Real approval, exact consent, atomic writes and the existing executor lifecycle."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import text
from tests.backend.test_draft_plans import prepare,save,worker,BASE
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime,login

PATH='/api/v1/maintenance/publication-proposals/'

def profile(row):
    return dict(row_number=row,instructions='TEST ONLY inspect synthetic fixture',safety_notes='TEST ONLY safety approved by test chief',
        methodology_ref='TEST ONLY procedure',engineer_note='TEST ONLY note for technician',
        checklist=[dict(text='TEST ONLY inspection confirmed',answer_kind='boolean',required=True,photo_required=False)])

def prepared(managed,*,place=True,continuous=False,split=False):
    engine,app,admin,local_login,ids=managed
    admin,eq,_,row,_,request=prepare(managed,**(dict(interpretation='CONTINUOUS_WORK',splittable=True,min_segment_minutes=60) if continuous else dict(splittable=True,min_segment_minutes=60) if split else {}))
    worker_id=worker(managed,'TEST ONLY published worker');record,_,preview=save(admin,request)
    root=preview['items'][0]['occurrence_id']
    segment=admin.get(BASE+f"/{record['draft_id']}/occurrences/{root}/segments").json()['items'][0]
    segments=[segment]
    if continuous or split:
        first=dict(segment,segment_id=str(uuid4()),person_hours='1.500')
        second=dict(segment,person_hours='1.500',depends_on_segment_ids=[first['segment_id']])
        response=admin.post(BASE+f"/{record['draft_id']}/segments",json=dict(expected_revision=1,occurrence_id=root,segments=[first,second],reason='TEST ONLY reviewed segmentation'))
        assert response.status_code==200,response.text
        record=response.json();segments=[first,second]
    if place:
        for index,segment in enumerate(segments):
            start='09:00' if index==0 else '10:30';end='10:30' if len(segments)>1 and index==0 else '12:00'
            response=admin.post(BASE+f"/{record['draft_id']}/placements",json=dict(expected_revision=record['revision'],segment_id=segment['segment_id'],start_local='2027-01-02T'+start,end_local='2027-01-02T'+end,worker_ids=[worker_id],locked=False,unlock=False,reason='TEST ONLY reviewed placement'))
            assert response.status_code==200,response.text
            record=response.json()
    command=dict(expected_revision=record['revision'],idempotency_key=str(uuid4()),reason='TEST ONLY request approval',scope_note='TEST ONLY selected source row, finite horizon, remaining rows excluded',profiles=[profile(row)])
    response=admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=command)
    assert response.status_code==201,response.text
    return admin,record,response.json(),command,worker_id

def approve(admin,proposal):
    response=admin.chief.post(PATH+proposal['proposal_id']+'/approve',json=dict(expected_digest=proposal['proposal_digest'],reason='TEST ONLY reviewed exact changes and execution procedure'))
    assert response.status_code==200,response.text
    return response.json()

def publishing(proposal):return dict(expected_digest=proposal['proposal_digest'],approval_token=proposal['approval_token'],idempotency_key=str(uuid4()))

def test_approved_finite_plan_publishes_once_into_real_calendar_and_worker_cabinet(managed):
    engine,app,admin,local_login,ids=managed
    with engine.connect() as c:before=c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),ids)
    admin,record,proposal,command,worker_id=prepared(managed)
    assert proposal['can_approve'] and proposal['summary']['added_tasks']==1 and proposal['summary']['unselected_rows']==216
    assert admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=command).json()['proposal_id']==proposal['proposal_id']
    assert admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=dict(command,reason='other')).status_code==409
    changes=admin.get(PATH+proposal['proposal_id']+'/changes').json()
    assert changes['total']==1 and changes['items'][0]['execution']['engineer_note']=='TEST ONLY note for technician'
    assert 'input_snapshot' not in admin.get(PATH+proposal['proposal_id']).json()
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),ids)==before
    assert admin.post(PATH+proposal['proposal_id']+'/publish',json=dict(expected_digest=proposal['proposal_digest'],approval_token=str(uuid4()),idempotency_key=str(uuid4()))).status_code==403
    generation_before=admin.chief.get('/api/v1/maintenance/ui/calendar/preview?year=2027&month=1').json()['generationToken']
    proposal=approve(admin,proposal);command=publishing(proposal)
    response=admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=command)
    assert response.status_code==200,response.text
    assert response.json()['state']=='published'
    assert admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=command).json()['publication_id']==response.json()['publication_id']
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),ids)==before+1
        task=c.execute(text('SELECT work_order_id,norm_hours_snapshot,operation_snapshot FROM work_orders WHERE site_id=:site'),ids).mappings().one()
        assert task['norm_hours_snapshot']==3 and task['operation_snapshot']['engineer_note']=='TEST ONLY note for technician'
        assert c.scalar(text('SELECT count(*) FROM maintenance_notifications WHERE site_id=:site'),ids)==1
    calendar=admin.chief.get('/api/v1/maintenance/ui/calendar?year=2027&month=1')
    assert calendar.status_code==200,calendar.text
    assert len(calendar.json())==1 and not calendar.json()[0]['requiresInput']
    preview=admin.chief.get('/api/v1/maintenance/ui/calendar/preview?year=2027&month=1')
    assert preview.status_code==200 and not preview.json()['items']
    assert preview.json()['generationToken']==generation_before
    assert admin.chief.get('/api/v1/maintenance/management/catalog').json()['operations']==[]
    with closing(local_login(worker_id+'@example.test')) as technician:
        response=technician.get('/api/v1/maintenance/ui/tasks/'+str(task['work_order_id']))
        assert response.status_code==200,response.text
        assert 'TEST ONLY safety' in response.json()['task']['instructions']
        assert technician.post('/api/v1/maintenance/tasks/'+str(task['work_order_id'])+'/start',json=dict(expected_revision=1)).status_code==409

@pytest.mark.parametrize('change',['availability','source','revision','expired'])
def test_stale_approved_proposal_never_partially_publishes(managed,change):
    engine,_,_,_,ids=managed;admin,record,proposal,_,worker_id=prepared(managed);proposal=approve(admin,proposal)
    with engine.begin() as c:
        if change=='availability':c.execute(text("UPDATE availability_slots SET ends_at=ends_at-interval '1 hour' WHERE user_id=:id"),dict(id=worker_id))
        elif change=='source':c.execute(text('UPDATE equipment SET revision=revision+1 WHERE site_id=:site'),ids)
        elif change=='expired':c.execute(text("UPDATE draft_publication_proposals SET created_at=now()-interval '1 hour',expires_at=now()-interval '1 minute' WHERE proposal_id=:id"),dict(id=proposal['proposal_id']))
    if change=='revision':
        from tests.backend.test_draft_plans import save as another
        root=admin.get(BASE+f"/{record['draft_id']}/occurrences").json()['items'][0]['occurrence_id']
        segments=admin.get(BASE+f"/{record['draft_id']}/occurrences/{root}/segments").json()['items']
        assert admin.post(BASE+f"/{record['draft_id']}/segments",json=dict(expected_revision=record['revision'],occurrence_id=root,segments=segments,reason='TEST ONLY new revision')).status_code==200
    response=admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal))
    assert response.status_code==409,response.text
    with engine.connect() as c:
        for table in ('draft_publications','published_catalog_tasks','published_catalog_obligations','work_orders','work_assignments','schedule_entries','schedule_plans'):
            assert c.scalar(text(f'SELECT count(*) FROM {table} WHERE site_id=:site'),ids)==0

def test_reject_wrong_digest_roles_csrf_and_cross_site(managed):
    _,app,_,_,_=managed;admin,record,proposal,_,_=prepared(managed)
    body=dict(expected_digest=proposal['proposal_digest'],reason='TEST ONLY reject')
    assert admin.post(PATH+proposal['proposal_id']+'/approve',json=body).status_code==403
    assert admin.chief.post(PATH+proposal['proposal_id']+'/approve',json=dict(body,expected_digest='a'*64)).status_code==409
    assert admin.chief.post(PATH+proposal['proposal_id']+'/approve',json=body,headers={'X-CSRF-Token':'bad'}).status_code==403
    with closing(login(app,'chief_engineer')) as other:
        assert other.get(PATH+proposal['proposal_id']).status_code==404
        assert other.post(PATH+proposal['proposal_id']+'/approve',json=body).status_code==404
    with closing(login(app,'executor')) as executor:assert executor.get(PATH+proposal['proposal_id']).status_code==403
    rejected=admin.chief.post(PATH+proposal['proposal_id']+'/reject',json=body)
    assert rejected.status_code==200 and rejected.json()['state']=='rejected'
    assert admin.chief.post(PATH+proposal['proposal_id']+'/approve',json=body).status_code==409
    assert admin.chief.post(PATH+proposal['proposal_id']+'/reject',json=body).status_code==200

def test_unplaced_work_is_visible_but_cannot_be_approved(managed):
    admin,_,proposal,_,_=prepared(managed,place=False)
    assert not proposal['can_approve'] and proposal['blocker_count']>0
    assert admin.chief.post(PATH+proposal['proposal_id']+'/approve',json=dict(expected_digest=proposal['proposal_digest'],reason='TEST ONLY invalid approval')).status_code==409

def test_concurrent_publication_and_duplicate_source_cannot_issue_work_twice(managed):
    engine,_,_,_,ids=managed;admin,record,proposal,body,_=prepared(managed);proposal=approve(admin,proposal);command=publishing(proposal)
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=command),range(2)))
    assert [r.status_code for r in responses]==[200,200],[r.text for r in responses]
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),ids)==1
    duplicate=admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=dict(body,idempotency_key=str(uuid4())))
    assert duplicate.status_code==201,duplicate.text
    assert not duplicate.json()['can_approve'] and any(b['code']=='ALREADY_PUBLISHED' for b in duplicate.json()['blockers'])


def test_failure_after_writing_tasks_rolls_back_all_live_rows(managed,monkeypatch):
    import app.integration.publication as module
    engine,_,_,_,ids=managed;admin,_,proposal,_,_=prepared(managed);proposal=approve(admin,proposal)
    original=module.materialize
    def failure(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('TEST ONLY forced failure after materialization')
    monkeypatch.setattr(module,'materialize',failure)
    response=admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal))
    assert response.status_code==500
    with engine.connect() as c:
        for table in ('draft_publications','published_catalog_tasks','published_catalog_obligations','work_orders','work_assignments','schedule_entries','schedule_plans','maintenance_rules','operation_templates','maintenance_notifications'):
            assert c.scalar(text(f'SELECT count(*) FROM {table} WHERE site_id=:site'),ids)==0
    assert admin.get(PATH+proposal['proposal_id']).json()['state']=='approved'


@pytest.mark.parametrize('continuous,task_count',[(True,1),(False,2)])
def test_segmentation_preserves_hours_and_continuous_task_is_one_reserved_block(managed,continuous,task_count):
    engine,_,_,_,ids=managed;admin,_,proposal,_,_=prepared(managed,continuous=continuous,split=not continuous)
    assert proposal['summary']['added_tasks']==task_count
    proposal=approve(admin,proposal);response=admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal))
    assert response.status_code==200,response.text
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),ids)==task_count
        assert c.scalar(text('SELECT sum(norm_hours_snapshot) FROM work_orders WHERE site_id=:site'),ids)==3
        assert c.scalar(text("SELECT sum(extract(epoch from (end_at-start_at)))/3600 FROM work_assignments WHERE site_id=:site"),ids)==3


def test_published_work_starts_only_with_current_resources_and_an_actual_checklist(managed,monkeypatch):
    import app.main as main_module
    import app.integration.published_execution as execution
    import app.integration.analyst as analyst
    from datetime import timedelta
    instant=[datetime(2027,1,2,4,tzinfo=timezone.utc)]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            return instant[0].astimezone(tz) if tz else instant[0].replace(tzinfo=None)
    engine,_,_,local_login,ids=managed;admin,_,proposal,_,worker_id=prepared(managed);proposal=approve(admin,proposal)
    assert admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal)).status_code==200
    with engine.connect() as c:task=str(c.scalar(text('SELECT work_order_id FROM work_orders WHERE site_id=:site'),ids))
    monkeypatch.setattr(execution,'datetime',Clock);monkeypatch.setattr(main_module,'datetime',Clock)
    monkeypatch.setattr(analyst,'datetime',Clock)
    with closing(local_login(worker_id+'@example.test')) as technician:
        response=technician.post('/api/v1/maintenance/tasks/'+task+'/start',json=dict(expected_revision=1))
        assert response.status_code==200,response.text
        result=response.json();assert result['task']['state']=='in_progress'
        assert result['execution']['checklist'][0]['text']=='TEST ONLY inspection confirmed'
        instant[0]+=timedelta(hours=3)
        saved=technician.put('/api/v1/maintenance/tasks/'+task+'/report',json=dict(expected_revision=result['task']['revision'],narrative='TEST ONLY factual execution',
            answers={result['execution']['checklist'][0]['id']:'done'},actual=dict(started_at='2027-01-02T04:00:00Z',performed_at='2027-01-02T07:00:00Z',person_hours='3'),readings=[]))
        assert saved.status_code==200,saved.text
        submitted=technician.post('/api/v1/maintenance/tasks/'+task+'/submit',json=dict(expected_revision=saved.json()['task']['revision']))
        assert submitted.status_code==200,submitted.text
        result=submitted.json()
    reviewed=admin.chief.post('/api/v1/maintenance/tasks/'+task+'/review',json=dict(expected_revision=result['task']['revision'],execution_id=result['execution']['id'],verdict='accepted',reason='TEST ONLY human acceptance'))
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()['task']['state']=='accepted'
    with engine.connect() as c:assert c.scalar(text('SELECT status FROM work_orders WHERE work_order_id=:id'),dict(id=task))=='completed'
    assert admin.chief.post('/api/v1/maintenance/tasks/'+task+'/cancel',json=dict(expected_revision=reviewed.json()['task']['revision'],reason='TEST ONLY forbidden mutation')).status_code==409


@pytest.mark.parametrize('change',['token','snapshot'])
def test_consent_cannot_be_reused_for_another_payload_or_token(managed,change):
    engine,_,_,_,ids=managed;admin,_,proposal,_,_=prepared(managed);proposal=approve(admin,proposal);body=publishing(proposal)
    if change=='token':body['approval_token']=str(uuid4())
    else:
        with engine.begin() as c:c.execute(text("UPDATE draft_publication_proposals SET items=jsonb_set(items,'{0,person_hours}','\"0.001\"') WHERE proposal_id=:id"),dict(id=proposal['proposal_id']))
    response=admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=body)
    assert response.status_code==409,response.text
    with engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),ids)==0


def test_numeric_checklist_requires_confirmed_units(managed):
    admin,record,_,command,_=prepared(managed)
    command['idempotency_key']=str(uuid4());command['profiles'][0]['checklist'][0]['answer_kind']='number'
    assert admin.post(BASE+f"/{record['draft_id']}/publication-proposals",json=command).status_code==422


def test_existing_approved_month_is_preserved_when_publication_adds_tasks(managed):
    engine,_,_,_,ids=managed;month=uuid4()
    with engine.begin() as c:
        c.execute(text('''INSERT INTO schedule_plans(schedule_plan_id,site_id,period_year,period_month,revision,status,created_by,approved_by,approved_at,source_snapshot)
            SELECT :id,site_id,2027,1,1,'approved',user_id,user_id,now(),'{"test":"legacy approval"}' FROM site_memberships WHERE site_id=:site AND role='chief_engineer' '''),dict(id=month,site=ids['site']))
        before=c.scalar(text('SELECT md5(to_jsonb(p)::text) FROM schedule_plans p WHERE schedule_plan_id=:id'),dict(id=month))
    admin,_,proposal,_,_=prepared(managed);proposal=approve(admin,proposal)
    response=admin.chief.post(PATH+proposal['proposal_id']+'/publish',json=publishing(proposal))
    assert response.status_code==200,response.text
    with engine.connect() as c:
        assert c.scalar(text('SELECT md5(to_jsonb(p)::text) FROM schedule_plans p WHERE schedule_plan_id=:id'),dict(id=month))==before
        assert c.scalar(text('SELECT count(*) FROM schedule_plans WHERE site_id=:site'),ids)==1


def test_included_operation_claim_collides_with_later_independent_issue():
    from app.scheduling.publication import additions
    from app.schemas.publication import ExecutionProfile
    from tests.backend.test_draft_plans import pure_case
    root,parts,_,_=pure_case();root=root.model_copy(update={'included_rows':[9]})
    items,claims=additions([root],parts,[ExecutionProfile.model_validate(profile(root.source_row))])
    child=root.model_copy(update={'occurrence_id':uuid4(),'source_row':9,'included_rows':[]})
    child_parts=[s.model_copy(update={'occurrence_id':child.occurrence_id}) for s in parts]
    _,independent=additions([child],child_parts,[ExecutionProfile.model_validate(profile(9))])
    assert sum(Decimal(i['person_hours']) for i in items)==48
    assert {k['key'] for k in claims}&{k['key'] for k in independent}
